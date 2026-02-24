"use client";

import { useState } from "react";
import { DailyAlertGroup, Alert, resolveAlert } from "@/lib/api";
import { format, parseISO } from "date-fns";

// ── Labels & styles ───────────────────────────────────────────────────────────

const METRIC_LABELS: Record<string, string> = {
  net_revenue_usd:        "Net Revenue",
  gross_revenue_usd:      "Gross Revenue",
  charge_count:           "Charges",
  avg_charge_value_usd:   "Avg Charge",
  fee_rate:               "Fee Rate",
  refund_amount_usd:      "Refunds",
  refund_rate:            "Refund Rate",
  dispute_amount_usd:     "Disputes",
  net_balance_change_usd: "Net Balance",
};

const SEVERITY_STYLE: Record<string, string> = {
  HIGH:   "bg-red-950 text-red-400 border-red-800",
  MEDIUM: "bg-orange-950 text-orange-400 border-orange-800",
  LOW:    "bg-green-950 text-green-400 border-green-800",
};

const METHOD_STYLE: Record<string, string> = {
  DUAL:   "bg-emerald-950 text-emerald-300 border-emerald-700",
  MAD:    "bg-indigo-950 text-indigo-300 border-indigo-800",
  ZSCORE: "bg-violet-950 text-violet-300 border-violet-800",
};

const METHOD_LABEL: Record<string, string> = {
  DUAL:   "MAD + Z-score",
  MAD:    "MAD",
  ZSCORE: "Z-score",
};

const DIRECTION_ICON: Record<string, string> = {
  spike: "▲",
  drop:  "▼",
};

const DIRECTION_COLOR: Record<string, string> = {
  spike: "text-red-400",
  drop:  "text-blue-400",
};

// ── Sub-component: single alert row inside expanded day ───────────────────────

function AlertRow({
  tenantId,
  alert,
  onRefresh,
  onAlertClick,
}: {
  tenantId: number;
  alert: Alert;
  onRefresh: () => void;
  onAlertClick: (metricName: string) => void;
}) {
  const [resolving, setResolving] = useState(false);
  const [expanded, setExpanded] = useState(false);

  async function handleResolve(e: React.MouseEvent) {
    e.stopPropagation();
    setResolving(true);
    try {
      await resolveAlert(tenantId, alert.id);
      onRefresh();
    } catch (err) {
      console.error(err);
    } finally {
      setResolving(false);
    }
  }

  return (
    <div>
      <div
        className="grid grid-cols-[1fr_80px_100px_120px_80px_100px] gap-3 px-6 py-2.5
                   hover:bg-gray-800/40 transition-colors items-center cursor-pointer
                   border-b border-gray-800/40 last:border-0"
        onClick={() => { setExpanded((v) => !v); onAlertClick(alert.metric_name); }}
      >
        {/* Metric */}
        <span className="text-sm text-white">
          {METRIC_LABELS[alert.metric_name] ?? alert.metric_name}
        </span>
        {/* Direction */}
        <span className={`text-sm ${DIRECTION_COLOR[alert.direction]}`}>
          {DIRECTION_ICON[alert.direction]} {alert.direction}
        </span>
        {/* Severity */}
        <span>
          <span className={`text-xs font-semibold px-2 py-0.5 rounded-full border ${SEVERITY_STYLE[alert.severity]}`}>
            {alert.severity}
          </span>
        </span>
        {/* Method */}
        <span>
          <span className={`text-xs font-semibold px-2 py-0.5 rounded-full border ${METHOD_STYLE[alert.detection_method] ?? ""}`}>
            {METHOD_LABEL[alert.detection_method] ?? alert.detection_method}
          </span>
        </span>
        {/* Deviation */}
        <span className="text-sm text-gray-400">
          {alert.pct_deviation != null ? `${alert.pct_deviation.toFixed(1)}%` : "—"}
        </span>
        {/* Action */}
        <span>
          {alert.is_resolved ? (
            <span className="text-xs text-gray-600">Resolved</span>
          ) : (
            <button
              onClick={handleResolve}
              disabled={resolving}
              className="text-xs px-3 py-1 rounded-lg bg-indigo-900 hover:bg-indigo-700
                         text-indigo-300 border border-indigo-700 transition-colors
                         disabled:opacity-50 disabled:cursor-not-allowed"
            >
              {resolving ? "…" : "✓ Resolve"}
            </button>
          )}
        </span>
      </div>

      {/* Per-metric hint */}
      {expanded && (
        <div className="px-6 py-2 bg-gray-800/20 border-b border-gray-800/40">
          <p className="text-xs text-gray-400 leading-relaxed">
            <span className="text-yellow-500 mr-1">→</span>
            {alert.hint}
          </p>
          <p className="text-xs text-gray-600 mt-1">
            Score: {alert.score.toFixed(3)} &nbsp;|&nbsp; Value: {alert.metric_value.toLocaleString(undefined, { maximumFractionDigits: 2 })}
          </p>
        </div>
      )}
    </div>
  );
}

// ── Sub-component: one day group row ─────────────────────────────────────────

function DayGroupRow({
  tenantId,
  group,
  onRefresh,
  onAlertClick,
}: {
  tenantId: number;
  group: DailyAlertGroup;
  onRefresh: () => void;
  onAlertClick: (metricName: string) => void;
}) {
  const [open, setOpen] = useState(false);

  const dirIcons = group.directions.map((d) => (
    <span key={d} className={`${DIRECTION_COLOR[d]} mr-1`}>
      {DIRECTION_ICON[d]}
    </span>
  ));

  const metricChips = group.metrics_affected.slice(0, 3).map((m) => (
    <span
      key={m}
      className="text-xs bg-gray-800 text-gray-400 px-1.5 py-0.5 rounded mr-1"
    >
      {METRIC_LABELS[m] ?? m}
    </span>
  ));
  const overflow = group.metrics_affected.length > 3
    ? <span className="text-xs text-gray-600">+{group.metrics_affected.length - 3}</span>
    : null;

  return (
    <div>
      {/* Day header row */}
      <div
        className="grid grid-cols-[130px_60px_110px_1fr_36px] gap-3 px-4 py-3.5
                   border-b border-gray-800/60 hover:bg-gray-800/25 transition-colors
                   items-center cursor-pointer"
        onClick={() => {
          setOpen((v) => !v);
          if (group.alerts[0]) onAlertClick(group.alerts[0].metric_name);
        }}
      >
        {/* Date */}
        <span className="text-sm font-semibold text-gray-200">
          {format(parseISO(group.snapshot_date), "MMM d, yyyy")}
        </span>

        {/* Count */}
        <span className="text-sm text-gray-400 text-center">
          <span className="font-semibold text-white">{group.total_alerts}</span>
          <span className="text-gray-600 ml-1">alert{group.total_alerts !== 1 ? "s" : ""}</span>
        </span>

        {/* Severity + directions */}
        <span className="flex items-center gap-2">
          <span className={`text-xs font-semibold px-2 py-0.5 rounded-full border ${SEVERITY_STYLE[group.highest_severity]}`}>
            {group.highest_severity}
          </span>
          <span className="text-sm">{dirIcons}</span>
        </span>

        {/* Affected metrics chips */}
        <span className="flex flex-wrap items-center gap-0.5">
          {metricChips}
          {overflow}
        </span>

        {/* Expand chevron */}
        <span className="text-gray-500 text-sm select-none">
          {open ? "▲" : "▼"}
        </span>
      </div>

      {/* Expanded: combo hint + individual alerts */}
      {open && (
        <div className="border-b border-gray-800">
          {/* Global combo hint */}
          <div className="mx-4 my-3 px-4 py-3 rounded-lg bg-yellow-950/40 border border-yellow-800/50">
            <p className="text-xs font-semibold text-yellow-400 mb-1 uppercase tracking-wide">
              💡 Daily Analysis
            </p>
            <p className="text-sm text-yellow-200/80 leading-relaxed">
              {group.combo_hint}
            </p>
            {group.dual_count > 0 && (
              <p className="text-xs text-emerald-400 mt-2">
                {group.dual_count} dual-confirmed (MAD + Z-score both fired)
              </p>
            )}
          </div>

          {/* Individual alerts sub-table */}
          <div className="mx-4 mb-3 rounded-lg overflow-hidden border border-gray-800">
            {/* Sub-header */}
            <div className="grid grid-cols-[1fr_80px_100px_120px_80px_100px] gap-3 px-6 py-2
                            bg-gray-800/50 text-xs font-medium text-gray-500 uppercase tracking-wide">
              <span>Metric</span>
              <span>Dir.</span>
              <span>Severity</span>
              <span>Method</span>
              <span>Deviation</span>
              <span>Action</span>
            </div>
            {group.alerts.map((a) => (
              <AlertRow
                key={a.id}
                tenantId={tenantId}
                alert={a}
                onRefresh={onRefresh}
                onAlertClick={onAlertClick}
              />
            ))}
          </div>
        </div>
      )}
    </div>
  );
}

// ── Main component ────────────────────────────────────────────────────────────

interface Props {
  tenantId: number;
  unresolved: DailyAlertGroup[];
  resolved: DailyAlertGroup[];
  onRefresh: () => void;
  onAlertClick: (metricName: string) => void;
}

export default function AlertsTable({
  tenantId,
  unresolved,
  resolved,
  onRefresh,
  onAlertClick,
}: Props) {
  const [showResolved, setShowResolved] = useState(false);
  const groups = showResolved ? resolved : unresolved;

  return (
    <div>
      <div className="flex items-center justify-between mb-4">
        <h2 className="text-lg font-semibold text-gray-200">Anomaly Alerts</h2>
        <button
          onClick={() => setShowResolved((v) => !v)}
          className={`text-sm px-3 py-1.5 rounded-lg border transition-colors ${
            showResolved
              ? "bg-gray-700 border-gray-600 text-white"
              : "bg-transparent border-gray-700 text-gray-400 hover:text-white"
          }`}
        >
          {showResolved ? "Showing Resolved" : "Show Resolved"}
        </button>
      </div>

      {groups.length === 0 ? (
        <div className="bg-gray-900 border border-gray-800 rounded-xl p-8 text-center">
          <p className="text-gray-400 text-sm">
            {showResolved ? "No resolved alerts in this range." : "No active alerts — all clear."}
          </p>
        </div>
      ) : (
        <div className="bg-gray-900 border border-gray-800 rounded-xl overflow-hidden">
          {/* Table header */}
          <div className="grid grid-cols-[130px_60px_110px_1fr_36px] gap-3 px-4 py-3
                          border-b border-gray-800 text-xs font-medium text-gray-500 uppercase tracking-wide">
            <span>Date</span>
            <span>Count</span>
            <span>Severity</span>
            <span>Metrics</span>
            <span></span>
          </div>

          {groups.map((g) => (
            <DayGroupRow
              key={g.snapshot_date}
              tenantId={tenantId}
              group={g}
              onRefresh={onRefresh}
              onAlertClick={onAlertClick}
            />
          ))}
        </div>
      )}
    </div>
  );
}

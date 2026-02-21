"use client";

import {
  LineChart,
  Line,
  XAxis,
  YAxis,
  Tooltip,
  ResponsiveContainer,
  ScatterChart,
  Scatter,
  CartesianGrid,
  ComposedChart,
} from "recharts";
import { Alert, Snapshot } from "@/lib/api";
import { format, parseISO } from "date-fns";

const METRICS = [
  { key: "net_revenue_usd",        label: "Net Revenue ($)" },
  { key: "gross_revenue_usd",      label: "Gross Revenue ($)" },
  { key: "charge_count",           label: "Charges" },
  { key: "avg_charge_value_usd",   label: "Avg Ticket ($)" },
  { key: "fee_rate",               label: "Fee Rate (%)" },
  { key: "refund_amount_usd",      label: "Refunds ($)" },
  { key: "refund_rate",            label: "Refund Rate (%)" },
  { key: "net_balance_change_usd", label: "Net Balance ($)" },
];

// Metrics whose raw value (0–1) should be scaled to % for display
const RATE_METRICS = new Set(["fee_rate", "refund_rate"]);

interface Props {
  snapshots: Snapshot[];
  alerts: Alert[];
  selectedMetric: string;
  onMetricChange: (metric: string) => void;
}

interface ChartPoint {
  date: string;
  value: number;
  anomaly?: number;
}

export default function KPIChart({ snapshots, alerts, selectedMetric, onMetricChange }: Props) {

  const metricLabel =
    METRICS.find((m) => m.key === selectedMetric)?.label ?? selectedMetric;

  const sorted = [...snapshots].sort((a, b) =>
    a.snapshot_date.localeCompare(b.snapshot_date)
  );

  const anomalyDates = new Set(
    alerts
      .filter((a) => a.metric_name === selectedMetric)
      .map((a) => a.snapshot_date)
  );

  const data: ChartPoint[] = sorted.map((s) => {
    let value = (s[selectedMetric as keyof Snapshot] ?? 0) as number;
    if (RATE_METRICS.has(selectedMetric)) value = value * 100;
    return {
      date: s.snapshot_date,
      value,
      anomaly: anomalyDates.has(s.snapshot_date) ? value : undefined,
    };
  });

  const formatDate = (d: string) => {
    try { return format(parseISO(d), "MMM d"); }
    catch { return d; }
  };

  const CustomDot = (props: { cx?: number; cy?: number; payload?: ChartPoint }) => {
    const { cx, cy, payload } = props;
    if (payload?.anomaly === undefined || cx === undefined || cy === undefined) return null;
    return (
      <g>
        <line x1={cx - 7} y1={cy - 7} x2={cx + 7} y2={cy + 7} stroke="#ef4444" strokeWidth={2.5} />
        <line x1={cx + 7} y1={cy - 7} x2={cx - 7} y2={cy + 7} stroke="#ef4444" strokeWidth={2.5} />
      </g>
    );
  };

  return (
    <div>
      <div className="flex items-center justify-between mb-4">
        <h2 className="text-lg font-semibold text-gray-200">Time Series</h2>
        <select
          value={selectedMetric}
          onChange={(e) => onMetricChange(e.target.value)}
          className="bg-gray-800 border border-gray-700 text-gray-200 text-sm rounded-lg
                     px-3 py-2 focus:outline-none focus:ring-2 focus:ring-indigo-500"
        >
          {METRICS.map((m) => (
            <option key={m.key} value={m.key}>
              {m.label}
            </option>
          ))}
        </select>
      </div>

      {data.length === 0 ? (
        <p className="text-gray-400 text-sm">No snapshot data for this range.</p>
      ) : (
        <div className="bg-gray-900 border border-gray-800 rounded-xl p-4">
          <ResponsiveContainer width="100%" height={340}>
            <ComposedChart data={data} margin={{ top: 8, right: 16, left: 0, bottom: 0 }}>
              <CartesianGrid strokeDasharray="3 3" stroke="rgba(255,255,255,0.06)" />
              <XAxis
                dataKey="date"
                tickFormatter={formatDate}
                tick={{ fill: "#9ca3af", fontSize: 11 }}
                axisLine={{ stroke: "#374151" }}
                tickLine={false}
                interval="preserveStartEnd"
              />
              <YAxis
                tick={{ fill: "#9ca3af", fontSize: 11 }}
                axisLine={false}
                tickLine={false}
                width={60}
              />
              <Tooltip
                contentStyle={{
                  backgroundColor: "#1f2937",
                  border: "1px solid #374151",
                  borderRadius: "8px",
                  color: "#f3f4f6",
                  fontSize: "12px",
                }}
                labelFormatter={(label: unknown) => formatDate(String(label))}
                formatter={(value: number | undefined) => [
                  value == null
                    ? "—"
                    : RATE_METRICS.has(selectedMetric)
                    ? `${value.toFixed(2)}%`
                    : value.toLocaleString("en-US", { maximumFractionDigits: 2 }),
                  metricLabel,
                ]}
              />
              <Line
                type="monotone"
                dataKey="value"
                stroke="#6366f1"
                strokeWidth={2}
                dot={<CustomDot />}
                activeDot={{ r: 4, fill: "#6366f1" }}
                name={metricLabel}
              />
            </ComposedChart>
          </ResponsiveContainer>
          {anomalyDates.size > 0 && (
            <p className="mt-2 text-xs text-gray-500 flex items-center gap-1">
              <span className="text-red-400 font-bold">✕</span>
              Red crosses mark detected anomalies
            </p>
          )}
        </div>
      )}
    </div>
  );
}

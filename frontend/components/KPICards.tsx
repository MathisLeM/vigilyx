"use client";

import { Snapshot } from "@/lib/api";

const METRICS: {
  key: keyof Snapshot;
  label: string;
  format: (v: number) => string;
  aggregate: "sum" | "avg";
}[] = [
  { key: "gross_revenue_usd",      label: "Gross Revenue", format: (v) => `$${v.toLocaleString("en-US", { maximumFractionDigits: 0 })}`,  aggregate: "sum" },
  { key: "charge_count",           label: "Charges",       format: (v) => v.toLocaleString("en-US"),                                              aggregate: "sum" },
  { key: "avg_charge_value_usd",   label: "Avg Ticket",    format: (v) => `$${v.toLocaleString("en-US", { maximumFractionDigits: 0 })}`,          aggregate: "avg" },
  { key: "fee_rate",               label: "Fee Rate",      format: (v) => `${(v * 100).toFixed(2)}%`,                                            aggregate: "avg" },
  { key: "refund_amount_usd",      label: "Refunds",       format: (v) => `$${v.toLocaleString("en-US", { maximumFractionDigits: 0 })}`,          aggregate: "sum" },
  { key: "refund_rate",            label: "Refund Rate",   format: (v) => `${(v * 100).toFixed(2)}%`,                                            aggregate: "avg" },
  { key: "net_balance_change_usd", label: "Net Balance",   format: (v) => `$${v.toLocaleString("en-US", { maximumFractionDigits: 0 })}`,          aggregate: "sum" },
];

const NEGATIVE_METRICS = new Set(["refund_amount_usd", "refund_rate"]);

interface Props {
  snapshots: Snapshot[];
  startLabel: string;
  endLabel: string;
}

export default function KPICards({ snapshots, startLabel, endLabel }: Props) {
  if (!snapshots.length) {
    return <p className="text-gray-400 text-sm">No KPI data found for the selected date range.</p>;
  }

  const sorted = [...snapshots].sort((a, b) => a.snapshot_date.localeCompare(b.snapshot_date));
  const latest = sorted[sorted.length - 1];
  const n = sorted.length;

  // Period aggregates
  const periodTotals: Partial<Record<keyof Snapshot, number>> = {};
  for (const { key, aggregate } of METRICS) {
    const vals = sorted.map((s) => (s[key] as number) ?? 0);
    periodTotals[key] = aggregate === "sum"
      ? vals.reduce((a, b) => a + b, 0)
      : vals.reduce((a, b) => a + b, 0) / n;
  }

  function Card({
    value,
    label,
    metricKey,
    delta,
  }: {
    value: number;
    label: string;
    metricKey: keyof Snapshot;
    delta?: number | null;
  }) {
    const metric = METRICS.find((m) => m.key === metricKey)!;
    const isNeg = NEGATIVE_METRICS.has(metricKey as string);
    const up = delta !== undefined && delta !== null && delta >= 0;

    return (
      <div className="bg-gray-900 border border-gray-800 rounded-xl p-4 flex flex-col gap-1">
        <p className="text-xs text-gray-500 font-medium uppercase tracking-wide">{label}</p>
        <p className="text-xl font-bold text-white">{metric.format(value)}</p>
        {delta !== undefined && delta !== null && (
          <p className={`text-xs font-medium ${(up && !isNeg) || (!up && isNeg) ? "text-emerald-400" : "text-red-400"}`}>
            {up ? "▲" : "▼"} {Math.abs(delta).toFixed(1)}%
          </p>
        )}
      </div>
    );
  }

  // Delta: latest day vs previous day (if available)
  const prev = sorted.length >= 2 ? sorted[sorted.length - 2] : null;

  return (
    <div className="space-y-6">
      {/* Row 1 — Latest day */}
      <div>
        <p className="text-xs font-semibold text-gray-500 uppercase tracking-widest mb-3">
          Latest snapshot —{" "}
          <span className="text-gray-400 normal-case font-normal">{endLabel}</span>
        </p>
        <div className="grid grid-cols-2 sm:grid-cols-4 lg:grid-cols-7 gap-3">
          {METRICS.map(({ key, label }) => {
            const val = (latest[key] as number) ?? 0;
            const prevVal = prev ? ((prev[key] as number) ?? 0) : null;
            const delta = prevVal !== null && prevVal !== 0
              ? ((val - prevVal) / Math.abs(prevVal)) * 100
              : null;
            return <Card key={key} value={val} label={label} metricKey={key} delta={delta} />;
          })}
        </div>
      </div>

      {/* Row 2 — Period totals */}
      <div>
        <p className="text-xs font-semibold text-gray-500 uppercase tracking-widest mb-3">
          Period total —{" "}
          <span className="text-gray-400 normal-case font-normal">{startLabel} → {endLabel}</span>
        </p>
        <div className="grid grid-cols-2 sm:grid-cols-4 lg:grid-cols-7 gap-3">
          {METRICS.map(({ key, label, aggregate }) => {
            const val = periodTotals[key] ?? 0;
            return (
              <Card
                key={key}
                value={val}
                label={aggregate === "avg" ? `${label} (avg)` : label}
                metricKey={key}
              />
            );
          })}
        </div>
      </div>
    </div>
  );
}

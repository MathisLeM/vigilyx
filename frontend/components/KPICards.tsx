"use client";

import { Snapshot } from "@/lib/api";

const METRICS: { key: keyof Snapshot; label: string; format: (v: number) => string }[] = [
  { key: "net_revenue_usd",        label: "Net Revenue",   format: (v) => `$${v.toLocaleString("en-US", { maximumFractionDigits: 0 })}` },
  { key: "gross_revenue_usd",      label: "Gross Revenue", format: (v) => `$${v.toLocaleString("en-US", { maximumFractionDigits: 0 })}` },
  { key: "charge_count",           label: "Charges",       format: (v) => v.toLocaleString("en-US") },
  { key: "avg_charge_value_usd",   label: "Avg Ticket",    format: (v) => `$${v.toLocaleString("en-US", { maximumFractionDigits: 0 })}` },
  { key: "fee_rate",               label: "Fee Rate",      format: (v) => `${(v * 100).toFixed(2)}%` },
  { key: "refund_amount_usd",      label: "Refunds",       format: (v) => `$${v.toLocaleString("en-US", { maximumFractionDigits: 0 })}` },
  { key: "refund_rate",            label: "Refund Rate",   format: (v) => `${(v * 100).toFixed(2)}%` },
  { key: "net_balance_change_usd", label: "Net Balance",   format: (v) => `$${v.toLocaleString("en-US", { maximumFractionDigits: 0 })}` },
];

interface Props {
  snapshots: Snapshot[];
  startLabel: string;
  endLabel: string;
}

export default function KPICards({ snapshots, startLabel, endLabel }: Props) {
  if (!snapshots.length) {
    return (
      <p className="text-gray-400 text-sm">No KPI data found for the selected date range.</p>
    );
  }

  const sorted = [...snapshots].sort((a, b) =>
    a.snapshot_date.localeCompare(b.snapshot_date)
  );
  const last = sorted[sorted.length - 1];
  const first = sorted[0];
  const sameDay = first.snapshot_date === last.snapshot_date;

  return (
    <div>
      <h2 className="text-lg font-semibold text-gray-200 mb-4">
        KPI Summary —{" "}
        <span className="text-gray-400 font-normal">
          {startLabel} → {endLabel}
        </span>
      </h2>
      <div className="grid grid-cols-2 sm:grid-cols-4 lg:grid-cols-7 gap-3">
        {METRICS.map(({ key, label, format }) => {
          const lastVal = last[key] as number;
          const firstVal = first[key] as number;
          let pctChange: number | null = null;
          if (!sameDay && firstVal !== 0) {
            pctChange = ((lastVal - firstVal) / Math.abs(firstVal)) * 100;
          }
          const up = pctChange !== null && pctChange >= 0;
          const isNegativeMetric = key === "refund_amount_usd" || key === "refund_rate" || key === "dispute_amount_usd";

          return (
            <div
              key={key}
              className="bg-gray-900 border border-gray-800 rounded-xl p-4 flex flex-col gap-1"
            >
              <p className="text-xs text-gray-500 font-medium uppercase tracking-wide">{label}</p>
              <p className="text-xl font-bold text-white">{format(lastVal)}</p>
              {pctChange !== null && (
                <p
                  className={`text-xs font-medium ${
                    (up && !isNegativeMetric) || (!up && isNegativeMetric)
                      ? "text-emerald-400"
                      : "text-red-400"
                  }`}
                >
                  {up ? "▲" : "▼"} {Math.abs(pctChange).toFixed(1)}%
                </p>
              )}
            </div>
          );
        })}
      </div>
    </div>
  );
}

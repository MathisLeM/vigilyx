"use client";

import { useCallback, useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { format, subDays } from "date-fns";
import { useAuth } from "@/lib/auth";
import { fetchSnapshots, fetchDailyAlerts, fetchTenants, runDetection, DailyAlertGroup, Alert, Snapshot, Tenant } from "@/lib/api";
import KPICards from "@/components/KPICards";
import KPIChart from "@/components/KPIChart";
import AlertsTable from "@/components/AlertsTable";
import NavSidebar from "@/components/NavSidebar";

function toDateStr(d: Date) {
  return format(d, "yyyy-MM-dd");
}

export default function DashboardPage() {
  const { isAuthenticated, tenantId: authTenantId, isAdmin } = useAuth();
  const router = useRouter();

  const [startDate, setStartDate] = useState(toDateStr(subDays(new Date(), 30)));
  const [endDate, setEndDate] = useState(toDateStr(new Date()));

  // Admin tenant selector
  const [tenants, setTenants] = useState<Tenant[]>([]);
  const [selectedTenantId, setSelectedTenantId] = useState<number | null>(authTenantId);

  const [snapshots, setSnapshots] = useState<Snapshot[]>([]);
  const [unresolved, setUnresolved] = useState<DailyAlertGroup[]>([]);
  const [resolved, setResolved] = useState<DailyAlertGroup[]>([]);
  const [selectedMetric, setSelectedMetric] = useState("net_revenue_usd");
  const [detecting, setDetecting] = useState(false);
  const [detectionMsg, setDetectionMsg] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  // Redirect to login if unauthenticated
  useEffect(() => {
    if (!isAuthenticated) router.replace("/login");
  }, [isAuthenticated, router]);

  // Admin: load tenant list and default to first
  useEffect(() => {
    if (isAdmin && isAuthenticated) {
      fetchTenants().then((list) => {
        setTenants(list);
        if (list.length > 0) setSelectedTenantId(list[0].id);
      });
    }
  }, [isAdmin, isAuthenticated]);

  const activeTenantId = isAdmin ? selectedTenantId : authTenantId;

  const loadData = useCallback(async () => {
    if (!activeTenantId) return;
    setLoading(true);
    try {
      const [snaps, unres, res] = await Promise.all([
        fetchSnapshots(activeTenantId, startDate, endDate),
        fetchDailyAlerts(activeTenantId, false, startDate, endDate),
        fetchDailyAlerts(activeTenantId, true, startDate, endDate),
      ]);
      setSnapshots(snaps);
      setUnresolved(unres);
      setResolved(res);
    } catch (e) {
      console.error(e);
    } finally {
      setLoading(false);
    }
  }, [activeTenantId, startDate, endDate]);

  useEffect(() => {
    if (isAuthenticated && activeTenantId) loadData();
  }, [isAuthenticated, loadData, activeTenantId]);

  async function handleDetect() {
    if (!activeTenantId) return;
    setDetecting(true);
    setDetectionMsg(null);
    try {
      const result = await runDetection(activeTenantId);
      setDetectionMsg(
        result.created > 0
          ? `${result.created} new alert(s) generated`
          : "No new anomalies detected"
      );
      await loadData();
    } catch (e) {
      setDetectionMsg("Detection failed");
    } finally {
      setDetecting(false);
    }
  }

  if (!isAuthenticated) return null;

  const flatUnresolved: Alert[] = unresolved.flatMap((g) => g.alerts);
  const flatResolved: Alert[] = resolved.flatMap((g) => g.alerts);
  const allAlerts: Alert[] = [...flatUnresolved, ...flatResolved];
  const highCount = flatUnresolved.filter((a) => a.severity === "HIGH").length;
  const mediumCount = flatUnresolved.filter((a) => a.severity === "MEDIUM").length;

  const startLabel = format(new Date(startDate + "T00:00:00"), "MMM d");
  const endLabel = format(new Date(endDate + "T00:00:00"), "MMM d");

  const activeTenantName = isAdmin
    ? tenants.find((t) => t.id === selectedTenantId)?.name ?? "…"
    : null;

  return (
    <div className="flex min-h-screen">
      <NavSidebar>
        {/* Admin tenant selector */}
        {isAdmin && tenants.length > 0 && (
          <div>
            <label className="block text-xs font-medium text-gray-500 uppercase tracking-wide mb-1.5">
              Company
            </label>
            <select
              value={selectedTenantId ?? ""}
              onChange={(e) => setSelectedTenantId(Number(e.target.value))}
              className="w-full bg-gray-800 border border-gray-700 text-gray-200 text-sm
                         rounded-lg px-3 py-2 focus:outline-none focus:ring-2 focus:ring-indigo-500"
            >
              {tenants.map((t) => (
                <option key={t.id} value={t.id}>
                  {t.name}
                </option>
              ))}
            </select>
          </div>
        )}

        <div>
          <label className="block text-xs font-medium text-gray-500 uppercase tracking-wide mb-1.5">
            From
          </label>
          <input
            type="date"
            value={startDate}
            max={endDate}
            onChange={(e) => setStartDate(e.target.value)}
            className="w-full bg-gray-800 border border-gray-700 text-gray-200 text-sm
                       rounded-lg px-3 py-2 focus:outline-none focus:ring-2 focus:ring-indigo-500"
          />
        </div>
        <div>
          <label className="block text-xs font-medium text-gray-500 uppercase tracking-wide mb-1.5">
            To
          </label>
          <input
            type="date"
            value={endDate}
            min={startDate}
            onChange={(e) => setEndDate(e.target.value)}
            className="w-full bg-gray-800 border border-gray-700 text-gray-200 text-sm
                       rounded-lg px-3 py-2 focus:outline-none focus:ring-2 focus:ring-indigo-500"
          />
        </div>

        <div className="pt-2">
          <button
            onClick={handleDetect}
            disabled={detecting}
            className="w-full bg-indigo-600 hover:bg-indigo-500 disabled:opacity-50
                       disabled:cursor-not-allowed text-white text-sm font-semibold
                       rounded-lg px-4 py-2.5 transition-colors"
          >
            {detecting ? "Running…" : "⚡ Run Detection"}
          </button>
          {detectionMsg && (
            <p className="mt-2 text-xs text-center text-gray-400">{detectionMsg}</p>
          )}
        </div>
      </NavSidebar>

      {/* ── Main content ── */}
      <main className="flex-1 overflow-auto p-8 space-y-8">
        {/* Admin context header */}
        {isAdmin && activeTenantName && (
          <div className="flex items-center gap-2">
            <p className="text-gray-400 text-sm">Viewing:</p>
            <p className="text-white font-semibold">{activeTenantName}</p>
          </div>
        )}

        {/* Stats banner */}
        <div className="grid grid-cols-4 gap-4">
          {[
            { label: "Total Alerts", value: allAlerts.length },
            { label: "Unresolved",   value: flatUnresolved.length },
            { label: "🔴 High",      value: highCount },
            { label: "🟠 Medium",    value: mediumCount },
          ].map(({ label, value }) => (
            <div
              key={label}
              className="bg-gray-900 border border-gray-800 rounded-xl p-5"
            >
              <p className="text-xs text-gray-500 font-medium uppercase tracking-wide">{label}</p>
              <p className="text-3xl font-bold text-white mt-1">{value}</p>
            </div>
          ))}
        </div>

        {loading ? (
          <div className="flex items-center justify-center py-24">
            <div className="w-8 h-8 border-2 border-indigo-500 border-t-transparent rounded-full animate-spin" />
          </div>
        ) : (
          <>
            <KPICards snapshots={snapshots} startLabel={startLabel} endLabel={endLabel} />
            <div className="border-t border-gray-800" />
            <KPIChart
              snapshots={snapshots}
              alerts={allAlerts}
              selectedMetric={selectedMetric}
              onMetricChange={setSelectedMetric}
            />
            <div className="border-t border-gray-800" />
            <AlertsTable
              tenantId={activeTenantId!}
              unresolved={unresolved}
              resolved={resolved}
              onRefresh={loadData}
              onAlertClick={setSelectedMetric}
            />
          </>
        )}
      </main>
    </div>
  );
}

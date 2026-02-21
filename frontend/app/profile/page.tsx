"use client";

import { useEffect, useState, FormEvent } from "react";
import { useRouter } from "next/navigation";
import { format, parseISO } from "date-fns";
import { useAuth } from "@/lib/auth";
import {
  fetchConfig,
  saveStripeKey,
  deleteStripeKey,
  testStripeConnection,
  fetchIngestionStatus,
  runIngestion,
  TenantConfig,
  IngestionStatus,
  IngestionResult,
} from "@/lib/api";
import NavSidebar from "@/components/NavSidebar";

type TestStatus = "idle" | "loading" | "success" | "error";

export default function ProfilePage() {
  const { isAuthenticated, tenantId, email, isAdmin } = useAuth();
  const router = useRouter();

  const [config, setConfig] = useState<TenantConfig | null>(null);
  const [keyInput, setKeyInput] = useState("");
  const [showKey, setShowKey] = useState(false);
  const [saving, setSaving] = useState(false);
  const [saveError, setSaveError] = useState<string | null>(null);
  const [deleting, setDeleting] = useState(false);
  const [testStatus, setTestStatus] = useState<TestStatus>("idle");
  const [testMessage, setTestMessage] = useState<string | null>(null);
  const [testAccountName, setTestAccountName] = useState<string | null>(null);

  // Ingestion
  const [ingestionStatus, setIngestionStatus] = useState<IngestionStatus | null>(null);
  const [ingesting, setIngesting] = useState(false);
  const [ingestionResult, setIngestionResult] = useState<IngestionResult | null>(null);
  const [ingestionError, setIngestionError] = useState<string | null>(null);

  useEffect(() => {
    if (!isAuthenticated) { router.replace("/login"); return; }
  }, [isAuthenticated, router]);

  useEffect(() => {
    if (isAuthenticated && tenantId) {
      fetchConfig(tenantId).then(setConfig).catch(console.error);
      fetchIngestionStatus(tenantId).then(setIngestionStatus).catch(console.error);
    }
  }, [isAuthenticated, tenantId]);

  async function handleSave(e: FormEvent) {
    e.preventDefault();
    if (!tenantId || !keyInput.trim()) return;
    setSaving(true);
    setSaveError(null);
    setTestStatus("idle");
    try {
      const updated = await saveStripeKey(tenantId, keyInput.trim());
      setConfig(updated);
      setKeyInput("");
    } catch (err: unknown) {
      setSaveError(err instanceof Error ? err.message : "Save failed");
    } finally {
      setSaving(false);
    }
  }

  async function handleDelete() {
    if (!tenantId) return;
    setDeleting(true);
    setTestStatus("idle");
    try {
      const updated = await deleteStripeKey(tenantId);
      setConfig(updated);
    } catch (e) {
      console.error(e);
    } finally {
      setDeleting(false);
    }
  }

  async function handleTest() {
    if (!tenantId) return;
    setTestStatus("loading");
    setTestMessage(null);
    setTestAccountName(null);
    try {
      const result = await testStripeConnection(tenantId);
      setTestStatus(result.success ? "success" : "error");
      setTestMessage(result.message);
      setTestAccountName(result.account_name);
    } catch (e) {
      setTestStatus("error");
      setTestMessage("Request failed");
    }
  }

  async function handleIngest(forceFull: boolean) {
    if (!tenantId) return;
    setIngesting(true);
    setIngestionResult(null);
    setIngestionError(null);
    try {
      const result = await runIngestion(tenantId, forceFull);
      setIngestionResult(result);
      const status = await fetchIngestionStatus(tenantId);
      setIngestionStatus(status);
    } catch (err: unknown) {
      setIngestionError(err instanceof Error ? err.message : "Ingestion failed");
    } finally {
      setIngesting(false);
    }
  }

  if (!isAuthenticated) return null;

  return (
    <div className="flex min-h-screen">
      <NavSidebar />

      <main className="flex-1 overflow-auto p-8 max-w-2xl space-y-8">
        <h1 className="text-2xl font-bold text-white">Profile & Settings</h1>

        {/* ── Section 1: Account Info ── */}
        <section className="bg-gray-900 border border-gray-800 rounded-2xl p-6 space-y-4">
          <h2 className="text-base font-semibold text-gray-200">Account</h2>
          <div className="grid grid-cols-[140px_1fr] gap-y-3 text-sm">
            <span className="text-gray-500">Email</span>
            <span className="text-white">{email}</span>

            <span className="text-gray-500">Role</span>
            <span className="text-white">
              {isAdmin ? (
                <span className="inline-flex items-center gap-1.5">
                  Admin
                  <span className="text-xs px-2 py-0.5 rounded-full bg-indigo-950 text-indigo-400 border border-indigo-800">
                    all companies
                  </span>
                </span>
              ) : (
                "Member"
              )}
            </span>

            <span className="text-gray-500">Tenant ID</span>
            <span className="text-white font-mono text-xs">
              {tenantId ?? <span className="text-gray-500">N/A (admin)</span>}
            </span>
          </div>
        </section>

        {/* ── Section 2: Stripe Configuration — hidden for admin (no tenant) ── */}
        {isAdmin && (
          <section className="bg-gray-900 border border-gray-800 rounded-2xl p-6">
            <p className="text-sm text-gray-500">
              Stripe configuration is managed per company. Sign in as a company account to configure its API key.
            </p>
          </section>
        )}
        {!isAdmin && <section className="bg-gray-900 border border-gray-800 rounded-2xl p-6 space-y-5">
          <div className="flex items-center justify-between">
            <h2 className="text-base font-semibold text-gray-200">Stripe Configuration</h2>

            {/* Connection status badge */}
            {config && (
              <span className={`text-xs font-semibold px-3 py-1 rounded-full border ${
                config.has_stripe_key
                  ? "bg-emerald-950 text-emerald-400 border-emerald-800"
                  : "bg-gray-800 text-gray-500 border-gray-700"
              }`}>
                {config.has_stripe_key ? "● Connected" : "○ Not connected"}
              </span>
            )}
          </div>

          {/* Current key display */}
          {config?.has_stripe_key && (
            <div className="bg-gray-800 border border-gray-700 rounded-xl p-4 space-y-3">
              <div className="flex items-center justify-between">
                <div>
                  <p className="text-xs text-gray-500 mb-1">Current API key</p>
                  <p className="font-mono text-sm text-gray-200">{config.stripe_key_masked}</p>
                  {config.updated_at && (
                    <p className="text-xs text-gray-600 mt-1">
                      Last updated {format(parseISO(config.updated_at), "MMM d, yyyy 'at' HH:mm")}
                    </p>
                  )}
                </div>
                <button
                  onClick={handleDelete}
                  disabled={deleting}
                  className="text-xs text-red-400 hover:text-red-300 border border-red-800
                             hover:bg-red-950 px-3 py-1.5 rounded-lg transition-colors disabled:opacity-50"
                >
                  {deleting ? "Removing…" : "Remove"}
                </button>
              </div>

              {/* Test connection */}
              <div className="border-t border-gray-700 pt-3 flex items-center gap-3">
                <button
                  onClick={handleTest}
                  disabled={testStatus === "loading"}
                  className="text-sm px-4 py-2 rounded-lg bg-gray-700 hover:bg-gray-600
                             text-gray-200 transition-colors disabled:opacity-50"
                >
                  {testStatus === "loading" ? "Testing…" : "Test connection"}
                </button>

                {testStatus === "success" && (
                  <div className="text-sm text-emerald-400">
                    ✓ {testMessage}
                    {testAccountName && (
                      <span className="text-gray-400"> — {testAccountName}</span>
                    )}
                  </div>
                )}
                {testStatus === "error" && (
                  <p className="text-sm text-red-400">✕ {testMessage}</p>
                )}
              </div>
            </div>
          )}

          {/* Add / update key form */}
          <form onSubmit={handleSave} className="space-y-3">
            <div>
              <label className="block text-xs font-medium text-gray-500 uppercase tracking-wide mb-1.5">
                {config?.has_stripe_key ? "Replace API key" : "Add API key"}
              </label>
              <div className="relative">
                <input
                  type={showKey ? "text" : "password"}
                  value={keyInput}
                  onChange={(e) => setKeyInput(e.target.value)}
                  placeholder="sk_test_••••••••••••••••••••••••"
                  className="w-full bg-gray-800 border border-gray-700 text-gray-200 text-sm
                             font-mono rounded-lg px-4 py-2.5 pr-20
                             focus:outline-none focus:ring-2 focus:ring-indigo-500"
                />
                <button
                  type="button"
                  onClick={() => setShowKey((v) => !v)}
                  className="absolute right-3 top-1/2 -translate-y-1/2 text-xs text-gray-500
                             hover:text-gray-300 transition-colors"
                >
                  {showKey ? "Hide" : "Show"}
                </button>
              </div>
              <p className="mt-1.5 text-xs text-gray-600">
                Use a secret key starting with <span className="text-gray-400 font-mono">sk_test_</span> or{" "}
                <span className="text-gray-400 font-mono">sk_live_</span>. Never share this key.
              </p>
            </div>

            {saveError && (
              <p className="text-sm text-red-400 bg-red-950 border border-red-800 rounded-lg px-4 py-2">
                {saveError}
              </p>
            )}

            <button
              type="submit"
              disabled={saving || !keyInput.trim()}
              className="w-full bg-indigo-600 hover:bg-indigo-500 disabled:opacity-50
                         disabled:cursor-not-allowed text-white text-sm font-semibold
                         rounded-lg px-4 py-2.5 transition-colors"
            >
              {saving ? "Saving…" : "Save API key"}
            </button>
          </form>

          <p className="text-xs text-gray-600">
            Your key is stored server-side and never exposed in full after saving.
            It is used to pull data from Stripe for anomaly detection.
          </p>
        </section>}

        {/* ── Section 3: Data Ingestion ── */}
        {!isAdmin && (
          <section className="bg-gray-900 border border-gray-800 rounded-2xl p-6 space-y-5">
            <div className="flex items-center justify-between">
              <h2 className="text-base font-semibold text-gray-200">Data Ingestion</h2>
              {ingestionStatus && (
                <span className={`text-xs font-semibold px-3 py-1 rounded-full border ${
                  ingestionStatus.last_ingested_at
                    ? "bg-emerald-950 text-emerald-400 border-emerald-800"
                    : "bg-gray-800 text-gray-500 border-gray-700"
                }`}>
                  {ingestionStatus.last_ingested_at ? "● Synced" : "○ Never synced"}
                </span>
              )}
            </div>

            {/* Status info */}
            {ingestionStatus && (
              <div className="grid grid-cols-[160px_1fr] gap-y-2 text-sm">
                <span className="text-gray-500">Last synced</span>
                <span className="text-gray-200">
                  {ingestionStatus.last_ingested_at
                    ? format(new Date(ingestionStatus.last_ingested_at), "MMM d, yyyy 'at' HH:mm")
                    : <span className="text-gray-600">Never</span>}
                </span>
                <span className="text-gray-500">Raw rows in DB</span>
                <span className="text-gray-200 font-mono">{ingestionStatus.total_raw_rows.toLocaleString()}</span>
                <span className="text-gray-500">Stripe key</span>
                <span className={ingestionStatus.has_stripe_key ? "text-emerald-400" : "text-red-400"}>
                  {ingestionStatus.has_stripe_key ? "Configured" : "Missing — add key above first"}
                </span>
              </div>
            )}

            {/* Action buttons */}
            <div className="flex gap-3">
              <button
                onClick={() => handleIngest(false)}
                disabled={ingesting || !ingestionStatus?.has_stripe_key}
                className="flex-1 bg-indigo-600 hover:bg-indigo-500 disabled:opacity-50
                           disabled:cursor-not-allowed text-white text-sm font-semibold
                           rounded-lg px-4 py-2.5 transition-colors"
              >
                {ingesting ? "Syncing…" : "⚡ Sync (incremental)"}
              </button>
              <button
                onClick={() => handleIngest(true)}
                disabled={ingesting || !ingestionStatus?.has_stripe_key}
                className="px-4 py-2.5 rounded-lg border border-gray-700 text-gray-400
                           hover:text-white hover:bg-gray-800 disabled:opacity-50
                           disabled:cursor-not-allowed text-sm transition-colors"
              >
                Full re-pull
              </button>
            </div>

            {/* Result */}
            {ingestionResult && (
              <div className="bg-gray-800 border border-gray-700 rounded-xl p-4 space-y-1 text-sm">
                <p className="text-emerald-400 font-semibold mb-2">Sync complete</p>
                <div className="grid grid-cols-2 gap-x-6 gap-y-1 text-xs">
                  <span className="text-gray-500">Raw rows inserted</span>
                  <span className="text-gray-200">{ingestionResult.raw_inserted}</span>
                  <span className="text-gray-500">Raw rows skipped</span>
                  <span className="text-gray-200">{ingestionResult.raw_skipped}</span>
                  <span className="text-gray-500">Feature rows written</span>
                  <span className="text-gray-200">{ingestionResult.features_written}</span>
                  <span className="text-gray-500">Feature rows skipped</span>
                  <span className="text-gray-200">{ingestionResult.features_skipped}</span>
                  {ingestionResult.date_range && (
                    <>
                      <span className="text-gray-500">Date range</span>
                      <span className="text-gray-200 font-mono">
                        {ingestionResult.date_range[0]} → {ingestionResult.date_range[1]}
                      </span>
                    </>
                  )}
                  {ingestionResult.duration_seconds != null && (
                    <>
                      <span className="text-gray-500">Duration</span>
                      <span className="text-gray-200">{ingestionResult.duration_seconds.toFixed(1)}s</span>
                    </>
                  )}
                </div>
              </div>
            )}

            {ingestionError && (
              <p className="text-sm text-red-400 bg-red-950 border border-red-800 rounded-lg px-4 py-2">
                {ingestionError}
              </p>
            )}

            <p className="text-xs text-gray-600">
              Incremental sync pulls only new transactions since the last run. Full re-pull
              fetches the entire lookback window (up to 90 days).
            </p>
          </section>
        )}
      </main>
    </div>
  );
}

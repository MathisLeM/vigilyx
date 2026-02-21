"use client";

import { useEffect, useState, FormEvent } from "react";
import { useRouter } from "next/navigation";
import { format, parseISO } from "date-fns";
import { useAuth } from "@/lib/auth";
import {
  listStripeConnections,
  addStripeConnection,
  deleteStripeConnection,
  testStripeConnection,
  fetchIngestionStatus,
  runIngestion,
  fetchSlackConfig,
  saveSlackConfig,
  deleteSlackConfig,
  testSlackWebhook,
  listInvitations,
  createInvitation,
  revokeInvitation,
  StripeConnection,
  IngestionStatus,
  IngestionResult,
  TestResult,
  SlackConfig,
  SlackAlertLevel,
  Invitation,
} from "@/lib/api";
import NavSidebar from "@/components/NavSidebar";

type TestStatus = "idle" | "loading" | "success" | "error";

const ALERT_LEVELS: { value: SlackAlertLevel; label: string; description: string }[] = [
  { value: "HIGH",            label: "HIGH only",     description: "Critical alerts" },
  { value: "MEDIUM_AND_HIGH", label: "Med & High",    description: "Most alerts"     },
  { value: "ALL",             label: "All",           description: "Every alert"     },
];

const LEVEL_LABELS: Record<string, string> = {
  HIGH:            "HIGH only",
  MEDIUM_AND_HIGH: "Medium & High",
  ALL:             "All alerts",
};

const MAX_CONNECTIONS = 5;

export default function ProfilePage() {
  const { isAuthenticated, tenantId, email, isAdmin } = useAuth();
  const router = useRouter();

  // ── Stripe connections ─────────────────────────────────────────────────────
  const [connections, setConnections] = useState<StripeConnection[]>([]);
  const [addName, setAddName] = useState("");
  const [addKey, setAddKey] = useState("");
  const [showAddKey, setShowAddKey] = useState(false);
  const [addSaving, setAddSaving] = useState(false);
  const [addError, setAddError] = useState<string | null>(null);
  const [deletingId, setDeletingId] = useState<number | null>(null);
  const [testingId, setTestingId] = useState<number | null>(null);
  const [testResults, setTestResults] = useState<Record<number, TestResult>>({});

  // ── Ingestion ──────────────────────────────────────────────────────────────
  const [ingestionStatuses, setIngestionStatuses] = useState<IngestionStatus[]>([]);
  const [ingestingId, setIngestingId] = useState<number | null>(null);
  const [ingestResults, setIngestResults] = useState<Record<number, IngestionResult>>({});
  const [ingestErrors, setIngestErrors] = useState<Record<number, string>>({});

  // ── Slack ──────────────────────────────────────────────────────────────────
  const [slackConfig, setSlackConfig] = useState<SlackConfig | null>(null);
  const [webhookInput, setWebhookInput] = useState("");
  const [alertLevel, setAlertLevel] = useState<SlackAlertLevel>("HIGH");
  const [savingSlack, setSavingSlack] = useState(false);
  const [slackSaveError, setSlackSaveError] = useState<string | null>(null);
  const [deletingSlack, setDeletingSlack] = useState(false);
  const [slackTestStatus, setSlackTestStatus] = useState<TestStatus>("idle");
  const [slackTestMessage, setSlackTestMessage] = useState<string | null>(null);

  // ── Team / invitations ─────────────────────────────────────────────────────
  const [invitations, setInvitations] = useState<Invitation[]>([]);
  const [inviteEmail, setInviteEmail] = useState("");
  const [sendingInvite, setSendingInvite] = useState(false);
  const [inviteError, setInviteError] = useState<string | null>(null);
  const [lastInviteToken, setLastInviteToken] = useState<string | null>(null);
  const [revokingId, setRevokingId] = useState<number | null>(null);

  useEffect(() => {
    if (!isAuthenticated) { router.replace("/login"); return; }
  }, [isAuthenticated, router]);

  useEffect(() => {
    if (!isAuthenticated || !tenantId) return;
    listStripeConnections(tenantId).then(setConnections).catch(console.error);
    fetchIngestionStatus(tenantId).then(setIngestionStatuses).catch(console.error);
    fetchSlackConfig(tenantId).then((sc) => {
      setSlackConfig(sc);
      if (sc.slack_alert_level) setAlertLevel(sc.slack_alert_level);
    }).catch(console.error);
    listInvitations(tenantId).then(setInvitations).catch(console.error);
  }, [isAuthenticated, tenantId]);

  // ── Stripe connection handlers ─────────────────────────────────────────────

  async function handleAddConnection(e: FormEvent) {
    e.preventDefault();
    if (!tenantId || !addName.trim() || !addKey.trim()) return;
    setAddSaving(true);
    setAddError(null);
    try {
      const conn = await addStripeConnection(tenantId, addName.trim(), addKey.trim());
      setConnections((prev) => [...prev, conn]);
      setAddName("");
      setAddKey("");
    } catch (err: unknown) {
      setAddError(err instanceof Error ? err.message : "Failed to add connection");
    } finally {
      setAddSaving(false);
    }
  }

  async function handleDelete(connId: number) {
    if (!tenantId) return;
    setDeletingId(connId);
    try {
      await deleteStripeConnection(tenantId, connId);
      setConnections((prev) => prev.filter((c) => c.id !== connId));
      setTestResults((prev) => { const r = { ...prev }; delete r[connId]; return r; });
      setIngestResults((prev) => { const r = { ...prev }; delete r[connId]; return r; });
    } catch (e) { console.error(e); }
    finally { setDeletingId(null); }
  }

  async function handleTest(connId: number) {
    if (!tenantId) return;
    setTestingId(connId);
    try {
      const result = await testStripeConnection(tenantId, connId);
      setTestResults((prev) => ({ ...prev, [connId]: result }));
      if (result.success) {
        // Refresh connections to get updated stripe_account_id
        const updated = await listStripeConnections(tenantId);
        setConnections(updated);
      }
    } catch {
      setTestResults((prev) => ({
        ...prev,
        [connId]: { success: false, message: "Request failed", account_name: null, stripe_account_id: null },
      }));
    } finally {
      setTestingId(null);
    }
  }

  // ── Ingestion handlers ─────────────────────────────────────────────────────

  async function handleIngest(connId: number, forceFull: boolean) {
    if (!tenantId) return;
    setIngestingId(connId);
    setIngestErrors((prev) => { const r = { ...prev }; delete r[connId]; return r; });
    try {
      const result = await runIngestion(tenantId, connId, forceFull);
      setIngestResults((prev) => ({ ...prev, [connId]: result }));
      const statuses = await fetchIngestionStatus(tenantId);
      setIngestionStatuses(statuses);
    } catch (err: unknown) {
      setIngestErrors((prev) => ({
        ...prev,
        [connId]: err instanceof Error ? err.message : "Ingestion failed",
      }));
    } finally {
      setIngestingId(null);
    }
  }

  // ── Slack handlers ─────────────────────────────────────────────────────────

  async function handleSaveSlack(e: FormEvent) {
    e.preventDefault();
    if (!tenantId || !webhookInput.trim()) return;
    setSavingSlack(true);
    setSlackSaveError(null);
    setSlackTestStatus("idle");
    try {
      const updated = await saveSlackConfig(tenantId, webhookInput.trim(), alertLevel);
      setSlackConfig(updated);
      setWebhookInput("");
    } catch (err: unknown) {
      setSlackSaveError(err instanceof Error ? err.message : "Save failed");
    } finally {
      setSavingSlack(false);
    }
  }

  async function handleDeleteSlack() {
    if (!tenantId) return;
    setDeletingSlack(true);
    setSlackTestStatus("idle");
    try {
      const updated = await deleteSlackConfig(tenantId);
      setSlackConfig(updated);
      setAlertLevel("HIGH");
    } catch (e) { console.error(e); }
    finally { setDeletingSlack(false); }
  }

  async function handleTestSlack() {
    if (!tenantId) return;
    setSlackTestStatus("loading");
    setSlackTestMessage(null);
    try {
      const result = await testSlackWebhook(tenantId);
      setSlackTestStatus(result.success ? "success" : "error");
      setSlackTestMessage(result.message);
    } catch {
      setSlackTestStatus("error");
      setSlackTestMessage("Request failed");
    }
  }

  // ── Team / invitation handlers ─────────────────────────────────────────────

  async function handleSendInvite(e: FormEvent) {
    e.preventDefault();
    if (!tenantId || !inviteEmail.trim()) return;
    setSendingInvite(true);
    setInviteError(null);
    setLastInviteToken(null);
    try {
      const inv = await createInvitation(tenantId, inviteEmail.trim());
      setLastInviteToken(inv.token);
      setInviteEmail("");
      const updated = await listInvitations(tenantId);
      setInvitations(updated);
    } catch (err: unknown) {
      setInviteError(err instanceof Error ? err.message : "Failed to send invitation");
    } finally {
      setSendingInvite(false);
    }
  }

  async function handleRevoke(invitationId: number) {
    if (!tenantId) return;
    setRevokingId(invitationId);
    try {
      await revokeInvitation(tenantId, invitationId);
      setInvitations((prev) => prev.filter((i) => i.id !== invitationId));
      if (lastInviteToken) {
        const revokedInv = invitations.find((i) => i.id === invitationId);
        if (revokedInv?.token === lastInviteToken) setLastInviteToken(null);
      }
    } catch (e) { console.error(e); }
    finally { setRevokingId(null); }
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

        {/* ── Section 2: Stripe Connections ── */}
        {isAdmin && (
          <section className="bg-gray-900 border border-gray-800 rounded-2xl p-6">
            <p className="text-sm text-gray-500">
              Stripe configuration is managed per company. Sign in as a company account to configure its connections.
            </p>
          </section>
        )}
        {!isAdmin && (
          <section className="bg-gray-900 border border-gray-800 rounded-2xl p-6 space-y-5">
            <div className="flex items-center justify-between">
              <div>
                <h2 className="text-base font-semibold text-gray-200">Stripe Connections</h2>
                <p className="text-xs text-gray-500 mt-0.5">
                  Up to {MAX_CONNECTIONS} Stripe accounts. Test each connection to enable ingestion.
                </p>
              </div>
              <span className="text-xs font-semibold px-3 py-1 rounded-full border border-gray-700 text-gray-400">
                {connections.length} / {MAX_CONNECTIONS}
              </span>
            </div>

            {/* Connection cards */}
            {connections.length > 0 && (
              <div className="space-y-3">
                {connections.map((conn) => {
                  const tr = testResults[conn.id];
                  const isTesting = testingId === conn.id;
                  const isDeleting = deletingId === conn.id;
                  const statusLabel = conn.stripe_account_id
                    ? "● Connected"
                    : conn.has_key
                    ? "○ Not tested"
                    : "○ No key";
                  const statusColor = conn.stripe_account_id
                    ? "text-emerald-400 border-emerald-800 bg-emerald-950"
                    : "text-gray-500 border-gray-700 bg-gray-800";

                  return (
                    <div
                      key={conn.id}
                      className="bg-gray-800 border border-gray-700 rounded-xl p-4 space-y-3"
                    >
                      <div className="flex items-center justify-between gap-3">
                        <div className="min-w-0">
                          <div className="flex items-center gap-2 flex-wrap">
                            <span className="text-sm font-semibold text-white">{conn.name}</span>
                            <span className={`text-xs px-2 py-0.5 rounded-full border font-medium ${statusColor}`}>
                              {statusLabel}
                            </span>
                          </div>
                          {conn.stripe_account_id && (
                            <p className="text-xs font-mono text-gray-500 mt-0.5">{conn.stripe_account_id}</p>
                          )}
                          {conn.updated_at && (
                            <p className="text-xs text-gray-600 mt-0.5">
                              Updated {format(parseISO(conn.updated_at), "MMM d, yyyy 'at' HH:mm")}
                            </p>
                          )}
                        </div>
                        <button
                          onClick={() => handleDelete(conn.id)}
                          disabled={isDeleting}
                          className="shrink-0 text-xs text-red-400 hover:text-red-300 border border-red-800
                                     hover:bg-red-950 px-3 py-1.5 rounded-lg transition-colors disabled:opacity-50"
                        >
                          {isDeleting ? "Removing…" : "Remove"}
                        </button>
                      </div>

                      {conn.has_key && (
                        <div className="border-t border-gray-700 pt-3 flex items-center gap-3 flex-wrap">
                          <button
                            onClick={() => handleTest(conn.id)}
                            disabled={isTesting}
                            className="text-sm px-4 py-1.5 rounded-lg bg-gray-700 hover:bg-gray-600
                                       text-gray-200 transition-colors disabled:opacity-50"
                          >
                            {isTesting ? "Testing…" : "Test connection"}
                          </button>
                          {tr && (
                            tr.success ? (
                              <span className="text-sm text-emerald-400">
                                ✓ {tr.message}
                                {tr.account_name && <span className="text-gray-400"> — {tr.account_name}</span>}
                              </span>
                            ) : (
                              <span className="text-sm text-red-400">✕ {tr.message}</span>
                            )
                          )}
                        </div>
                      )}
                    </div>
                  );
                })}
              </div>
            )}

            {/* Add connection form */}
            {connections.length < MAX_CONNECTIONS && (
              <form onSubmit={handleAddConnection} className="space-y-3 pt-1">
                <p className="text-xs font-medium text-gray-500 uppercase tracking-wide">
                  Add connection
                </p>
                <input
                  type="text"
                  value={addName}
                  onChange={(e) => setAddName(e.target.value)}
                  placeholder="Connection name (e.g. Main account, EU store)"
                  className="w-full bg-gray-800 border border-gray-700 text-gray-200 text-sm
                             rounded-lg px-4 py-2.5 focus:outline-none focus:ring-2 focus:ring-indigo-500"
                />
                <div className="relative">
                  <input
                    type={showAddKey ? "text" : "password"}
                    value={addKey}
                    onChange={(e) => setAddKey(e.target.value)}
                    placeholder="sk_test_••••••••••••••••••••••••"
                    className="w-full bg-gray-800 border border-gray-700 text-gray-200 text-sm
                               font-mono rounded-lg px-4 py-2.5 pr-20
                               focus:outline-none focus:ring-2 focus:ring-indigo-500"
                  />
                  <button
                    type="button"
                    onClick={() => setShowAddKey((v) => !v)}
                    className="absolute right-3 top-1/2 -translate-y-1/2 text-xs text-gray-500
                               hover:text-gray-300 transition-colors"
                  >
                    {showAddKey ? "Hide" : "Show"}
                  </button>
                </div>
                <p className="text-xs text-gray-600">
                  Secret key starting with <span className="font-mono text-gray-400">sk_test_</span> or{" "}
                  <span className="font-mono text-gray-400">sk_live_</span>. Never share this key.
                </p>

                {addError && (
                  <p className="text-sm text-red-400 bg-red-950 border border-red-800 rounded-lg px-4 py-2">
                    {addError}
                  </p>
                )}

                <button
                  type="submit"
                  disabled={addSaving || !addName.trim() || !addKey.trim()}
                  className="w-full bg-indigo-600 hover:bg-indigo-500 disabled:opacity-50
                             disabled:cursor-not-allowed text-white text-sm font-semibold
                             rounded-lg px-4 py-2.5 transition-colors"
                >
                  {addSaving ? "Saving…" : "Add connection"}
                </button>
              </form>
            )}

            <p className="text-xs text-gray-600">
              Keys are stored encrypted server-side. Test each connection to discover its Stripe account ID
              and enable scheduled ingestion.
            </p>
          </section>
        )}

        {/* ── Section 3: Data Ingestion ── */}
        {!isAdmin && (
          <section className="bg-gray-900 border border-gray-800 rounded-2xl p-6 space-y-5">
            <h2 className="text-base font-semibold text-gray-200">Data Ingestion</h2>
            <p className="text-xs text-gray-500">
              Sync Stripe transactions per connection. Incremental pulls new data only; Full re-pull fetches up to 90 days.
            </p>

            {connections.length === 0 && (
              <p className="text-sm text-gray-600">
                Add and test a Stripe connection above to enable data ingestion.
              </p>
            )}

            {connections.map((conn) => {
              const status = ingestionStatuses.find((s) => s.connection_id === conn.id);
              const result = ingestResults[conn.id];
              const error = ingestErrors[conn.id];
              const isIngesting = ingestingId === conn.id;
              const canIngest = conn.has_key;

              return (
                <div key={conn.id} className="bg-gray-800 border border-gray-700 rounded-xl p-4 space-y-3">
                  <div className="flex items-center justify-between">
                    <div>
                      <p className="text-sm font-semibold text-white">{conn.name}</p>
                      {conn.stripe_account_id && (
                        <p className="text-xs font-mono text-gray-500">{conn.stripe_account_id}</p>
                      )}
                    </div>
                    {status && (
                      <span className={`text-xs font-semibold px-2 py-0.5 rounded-full border ${
                        status.last_ingested_at
                          ? "bg-emerald-950 text-emerald-400 border-emerald-800"
                          : "bg-gray-700 text-gray-500 border-gray-600"
                      }`}>
                        {status.last_ingested_at ? "● Synced" : "○ Never synced"}
                      </span>
                    )}
                  </div>

                  {status && (
                    <div className="grid grid-cols-[140px_1fr] gap-y-1 text-xs">
                      <span className="text-gray-500">Last synced</span>
                      <span className="text-gray-300">
                        {status.last_ingested_at
                          ? format(new Date(status.last_ingested_at), "MMM d, yyyy 'at' HH:mm")
                          : <span className="text-gray-600">Never</span>}
                      </span>
                      <span className="text-gray-500">Raw rows in DB</span>
                      <span className="text-gray-300 font-mono">{status.total_raw_rows.toLocaleString()}</span>
                    </div>
                  )}

                  <div className="flex gap-2">
                    <button
                      onClick={() => handleIngest(conn.id, false)}
                      disabled={isIngesting || !canIngest}
                      className="flex-1 bg-indigo-600 hover:bg-indigo-500 disabled:opacity-50
                                 disabled:cursor-not-allowed text-white text-xs font-semibold
                                 rounded-lg px-3 py-2 transition-colors"
                    >
                      {isIngesting ? "Syncing…" : "⚡ Sync"}
                    </button>
                    <button
                      onClick={() => handleIngest(conn.id, true)}
                      disabled={isIngesting || !canIngest}
                      className="px-3 py-2 rounded-lg border border-gray-600 text-gray-400
                                 hover:text-white hover:bg-gray-700 disabled:opacity-50
                                 disabled:cursor-not-allowed text-xs transition-colors"
                    >
                      Full re-pull
                    </button>
                  </div>

                  {result && (
                    <div className="bg-gray-900 rounded-lg px-3 py-2 space-y-1 text-xs">
                      <p className="text-emerald-400 font-semibold">Sync complete</p>
                      <div className="grid grid-cols-2 gap-x-4 gap-y-0.5 text-xs mt-1">
                        <span className="text-gray-500">Raw inserted</span>
                        <span className="text-gray-300">{result.raw_inserted}</span>
                        <span className="text-gray-500">Raw skipped</span>
                        <span className="text-gray-300">{result.raw_skipped}</span>
                        <span className="text-gray-500">Features written</span>
                        <span className="text-gray-300">{result.features_written}</span>
                        {result.date_range && (
                          <>
                            <span className="text-gray-500">Date range</span>
                            <span className="text-gray-300 font-mono">
                              {result.date_range[0]} → {result.date_range[1]}
                            </span>
                          </>
                        )}
                        {result.duration_seconds != null && (
                          <>
                            <span className="text-gray-500">Duration</span>
                            <span className="text-gray-300">{result.duration_seconds.toFixed(1)}s</span>
                          </>
                        )}
                      </div>
                    </div>
                  )}

                  {error && (
                    <p className="text-xs text-red-400 bg-red-950 border border-red-800 rounded-lg px-3 py-2">
                      {error}
                    </p>
                  )}
                </div>
              );
            })}
          </section>
        )}

        {/* ── Section 4: Slack Alerts ── */}
        {!isAdmin && (
          <section className="bg-gray-900 border border-gray-800 rounded-2xl p-6 space-y-5">
            <div className="flex items-center justify-between">
              <div>
                <h2 className="text-base font-semibold text-gray-200">Slack Alerts</h2>
                <p className="text-xs text-gray-500 mt-0.5">
                  Get notified in Slack when anomalies are detected.
                </p>
              </div>
              {slackConfig && (
                <span className={`text-xs font-semibold px-3 py-1 rounded-full border ${
                  slackConfig.has_slack_webhook
                    ? "bg-emerald-950 text-emerald-400 border-emerald-800"
                    : "bg-gray-800 text-gray-500 border-gray-700"
                }`}>
                  {slackConfig.has_slack_webhook ? "● Connected" : "○ Not connected"}
                </span>
              )}
            </div>

            {slackConfig?.has_slack_webhook && (
              <div className="bg-gray-800 border border-gray-700 rounded-xl p-4 space-y-3">
                <div className="flex items-center justify-between">
                  <div>
                    <p className="text-xs text-gray-500 mb-1">Webhook</p>
                    <p className="font-mono text-sm text-gray-200">{slackConfig.slack_webhook_masked}</p>
                    <p className="text-xs text-gray-500 mt-1">
                      Alert level:{" "}
                      <span className="text-gray-300">
                        {LEVEL_LABELS[slackConfig.slack_alert_level ?? "HIGH"]}
                      </span>
                    </p>
                    {slackConfig.updated_at && (
                      <p className="text-xs text-gray-600 mt-0.5">
                        Last updated {format(parseISO(slackConfig.updated_at), "MMM d, yyyy 'at' HH:mm")}
                      </p>
                    )}
                  </div>
                  <button
                    onClick={handleDeleteSlack}
                    disabled={deletingSlack}
                    className="text-xs text-red-400 hover:text-red-300 border border-red-800
                               hover:bg-red-950 px-3 py-1.5 rounded-lg transition-colors disabled:opacity-50"
                  >
                    {deletingSlack ? "Removing…" : "Disconnect"}
                  </button>
                </div>

                <div className="border-t border-gray-700 pt-3 flex items-center gap-3">
                  <button
                    onClick={handleTestSlack}
                    disabled={slackTestStatus === "loading"}
                    className="text-sm px-4 py-2 rounded-lg bg-gray-700 hover:bg-gray-600
                               text-gray-200 transition-colors disabled:opacity-50"
                  >
                    {slackTestStatus === "loading" ? "Sending…" : "Send test message"}
                  </button>
                  {slackTestStatus === "success" && (
                    <p className="text-sm text-emerald-400">✓ {slackTestMessage}</p>
                  )}
                  {slackTestStatus === "error" && (
                    <p className="text-sm text-red-400">✕ {slackTestMessage}</p>
                  )}
                </div>
              </div>
            )}

            <form onSubmit={handleSaveSlack} className="space-y-4">
              <div>
                <label className="block text-xs font-medium text-gray-500 uppercase tracking-wide mb-1.5">
                  {slackConfig?.has_slack_webhook ? "Update webhook URL" : "Incoming webhook URL"}
                </label>
                <input
                  type="text"
                  value={webhookInput}
                  onChange={(e) => setWebhookInput(e.target.value)}
                  placeholder="https://hooks.slack.com/services/T.../B.../..."
                  className="w-full bg-gray-800 border border-gray-700 text-gray-200 text-sm
                             font-mono rounded-lg px-4 py-2.5
                             focus:outline-none focus:ring-2 focus:ring-indigo-500"
                />
                <p className="mt-1.5 text-xs text-gray-600">
                  In Slack: <span className="text-gray-400">Apps → Incoming Webhooks → Add New Webhook to Workspace</span>
                </p>
              </div>

              <div>
                <label className="block text-xs font-medium text-gray-500 uppercase tracking-wide mb-2">
                  Alert level
                </label>
                <div className="grid grid-cols-3 gap-2">
                  {ALERT_LEVELS.map(({ value, label, description }) => (
                    <button
                      key={value}
                      type="button"
                      onClick={() => setAlertLevel(value)}
                      className={`text-center px-3 py-3 rounded-xl border text-sm transition-colors ${
                        alertLevel === value
                          ? "bg-indigo-900 border-indigo-600 text-indigo-200"
                          : "bg-gray-800 border-gray-700 text-gray-400 hover:border-gray-600 hover:text-gray-300"
                      }`}
                    >
                      <div className="font-semibold">{label}</div>
                      <div className="text-xs mt-0.5 opacity-60">{description}</div>
                    </button>
                  ))}
                </div>
              </div>

              {slackSaveError && (
                <p className="text-sm text-red-400 bg-red-950 border border-red-800 rounded-lg px-4 py-2">
                  {slackSaveError}
                </p>
              )}

              <button
                type="submit"
                disabled={savingSlack || !webhookInput.trim()}
                className="w-full bg-indigo-600 hover:bg-indigo-500 disabled:opacity-50
                           disabled:cursor-not-allowed text-white text-sm font-semibold
                           rounded-lg px-4 py-2.5 transition-colors"
              >
                {savingSlack
                  ? "Saving…"
                  : slackConfig?.has_slack_webhook
                  ? "Update webhook"
                  : "Connect Slack"}
              </button>
            </form>

            <p className="text-xs text-gray-600">
              Alerts fire automatically after each detection run. The webhook URL is stored encrypted.
            </p>
          </section>
        )}

        {/* ── Section 5: Team ── */}
        {!isAdmin && (
          <section className="bg-gray-900 border border-gray-800 rounded-2xl p-6 space-y-5">
            <h2 className="text-base font-semibold text-gray-200">Team</h2>
            <p className="text-sm text-gray-500">
              Invite coworkers to join your company account. They will receive a one-time link to set a password.
            </p>

            <form onSubmit={handleSendInvite} className="flex gap-3">
              <input
                type="email"
                placeholder="colleague@company.com"
                value={inviteEmail}
                onChange={(e) => setInviteEmail(e.target.value)}
                required
                className="flex-1 bg-gray-800 border border-gray-700 rounded-lg px-4 py-2.5
                           text-sm text-white placeholder-gray-500
                           focus:outline-none focus:ring-2 focus:ring-indigo-500 focus:border-transparent"
              />
              <button
                type="submit"
                disabled={sendingInvite || !inviteEmail.trim()}
                className="bg-indigo-600 hover:bg-indigo-500 disabled:opacity-50
                           disabled:cursor-not-allowed text-white text-sm font-semibold
                           rounded-lg px-4 py-2.5 transition-colors whitespace-nowrap"
              >
                {sendingInvite ? "Sending…" : "Send invite"}
              </button>
            </form>

            {inviteError && (
              <p className="text-sm text-red-400 bg-red-950 border border-red-800 rounded-lg px-4 py-2">
                {inviteError}
              </p>
            )}

            {lastInviteToken && (
              <div className="bg-gray-800 border border-gray-700 rounded-lg px-4 py-3 space-y-2">
                <p className="text-xs text-gray-400 font-medium">Invite link (valid 7 days)</p>
                <div className="flex items-center gap-2">
                  <code className="flex-1 text-xs text-indigo-300 break-all font-mono">
                    {typeof window !== "undefined"
                      ? `${window.location.origin}/invite/accept?token=${lastInviteToken}`
                      : `/invite/accept?token=${lastInviteToken}`}
                  </code>
                  <button
                    onClick={() => {
                      const url = `${window.location.origin}/invite/accept?token=${lastInviteToken}`;
                      navigator.clipboard.writeText(url);
                    }}
                    className="shrink-0 text-xs text-gray-400 hover:text-white border border-gray-700
                               hover:border-gray-500 rounded px-2 py-1 transition-colors"
                  >
                    Copy
                  </button>
                </div>
              </div>
            )}

            {invitations.length > 0 && (
              <div className="space-y-2">
                <p className="text-xs font-medium text-gray-500 uppercase tracking-wide">Pending invitations</p>
                {invitations.map((inv) => (
                  <div
                    key={inv.id}
                    className="flex items-center justify-between bg-gray-800 border border-gray-700
                               rounded-lg px-4 py-3"
                  >
                    <div className="min-w-0">
                      <p className="text-sm text-white truncate">{inv.email}</p>
                      <p className="text-xs text-gray-500">
                        Expires {format(parseISO(inv.expires_at), "MMM d, yyyy")}
                      </p>
                    </div>
                    <button
                      onClick={() => handleRevoke(inv.id)}
                      disabled={revokingId === inv.id}
                      className="shrink-0 ml-4 text-xs text-red-400 hover:text-red-300
                                 disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
                    >
                      {revokingId === inv.id ? "Revoking…" : "Revoke"}
                    </button>
                  </div>
                ))}
              </div>
            )}

            {invitations.length === 0 && (
              <p className="text-xs text-gray-600">No pending invitations.</p>
            )}
          </section>
        )}
      </main>
    </div>
  );
}

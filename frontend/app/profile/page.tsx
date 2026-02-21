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
  fetchSlackConfig,
  saveSlackConfig,
  deleteSlackConfig,
  testSlackWebhook,
  listInvitations,
  createInvitation,
  revokeInvitation,
  TenantConfig,
  IngestionStatus,
  IngestionResult,
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

export default function ProfilePage() {
  const { isAuthenticated, tenantId, email, isAdmin } = useAuth();
  const router = useRouter();

  // Stripe
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

  // Slack
  const [slackConfig, setSlackConfig] = useState<SlackConfig | null>(null);
  const [webhookInput, setWebhookInput] = useState("");
  const [alertLevel, setAlertLevel] = useState<SlackAlertLevel>("HIGH");
  const [savingSlack, setSavingSlack] = useState(false);
  const [slackSaveError, setSlackSaveError] = useState<string | null>(null);
  const [deletingSlack, setDeletingSlack] = useState(false);
  const [slackTestStatus, setSlackTestStatus] = useState<TestStatus>("idle");
  const [slackTestMessage, setSlackTestMessage] = useState<string | null>(null);

  // Team / invitations
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
    if (isAuthenticated && tenantId) {
      fetchConfig(tenantId).then(setConfig).catch(console.error);
      fetchIngestionStatus(tenantId).then(setIngestionStatus).catch(console.error);
      fetchSlackConfig(tenantId).then((sc) => {
        setSlackConfig(sc);
        if (sc.slack_alert_level) setAlertLevel(sc.slack_alert_level);
      }).catch(console.error);
      listInvitations(tenantId).then(setInvitations).catch(console.error);
    }
  }, [isAuthenticated, tenantId]);

  // ---- Stripe handlers ----

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
    } catch {
      setTestStatus("error");
      setTestMessage("Request failed");
    }
  }

  // ---- Ingestion handlers ----

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

  // ---- Slack handlers ----

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
    } catch (e) {
      console.error(e);
    } finally {
      setDeletingSlack(false);
    }
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

  // ---- Team / Invitation handlers ----

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
    } catch (e) {
      console.error(e);
    } finally {
      setRevokingId(null);
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

        {/* ── Section 2: Stripe Configuration ── */}
        {isAdmin && (
          <section className="bg-gray-900 border border-gray-800 rounded-2xl p-6">
            <p className="text-sm text-gray-500">
              Stripe configuration is managed per company. Sign in as a company account to configure its API key.
            </p>
          </section>
        )}
        {!isAdmin && (
          <section className="bg-gray-900 border border-gray-800 rounded-2xl p-6 space-y-5">
            <div className="flex items-center justify-between">
              <h2 className="text-base font-semibold text-gray-200">Stripe Configuration</h2>
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
                      {testAccountName && <span className="text-gray-400"> — {testAccountName}</span>}
                    </div>
                  )}
                  {testStatus === "error" && (
                    <p className="text-sm text-red-400">✕ {testMessage}</p>
                  )}
                </div>
              </div>
            )}

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
                  Use a secret key starting with{" "}
                  <span className="text-gray-400 font-mono">sk_test_</span> or{" "}
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
          </section>
        )}

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

            {/* Current webhook display */}
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

                {/* Test button */}
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

            {/* Connect / update form */}
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

              {/* Alert level selector */}
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

            {/* Invite form */}
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

            {/* Copyable link for the last invite */}
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

            {/* Pending invitations list */}
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

"use client";

export const dynamic = "force-dynamic";

import { useEffect, useState, FormEvent, Suspense } from "react";
import { useRouter } from "next/navigation";
import { useSearchParams } from "next/navigation";
import { format, parseISO } from "date-fns";
import { useAuth } from "@/lib/auth";
import {
  listStripeConnections,
  addStripeConnection,
  deleteStripeConnection,
  testStripeConnection,
  fetchIngestionStatus,
  runIngestion,
  fetchModelStatus,
  trainAccountModel,
  fetchEmailConfig,
  saveEmailConfig,
  deleteEmailConfig,
  resendEmailVerification,
  verifyEmailToken,
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
  ModelStatus,
  TrainResult,
  TestResult,
  EmailConfig,
  EmailAlertLevel,
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

// Isolated component so useSearchParams is inside a Suspense boundary
function EmailTokenVerifier({
  onVerified,
  tenantId,
  setEmailConfig,
}: {
  onVerified: (r: { success: boolean; message: string }) => void;
  tenantId: number | null;
  setEmailConfig: (c: import("@/lib/api").EmailConfig | null) => void;
}) {
  const searchParams = useSearchParams();
  const router = useRouter();
  useEffect(() => {
    const token = searchParams?.get("email_token");
    if (!token) return;
    router.replace("/profile", { scroll: false });
    verifyEmailToken(token).then((res) => {
      onVerified(res);
      if (tenantId) fetchEmailConfig(tenantId).then(setEmailConfig).catch(console.error);
    });
  }, [searchParams, router, onVerified, tenantId, setEmailConfig]);
  return null;
}

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
  const [showAlphaModal, setShowAlphaModal] = useState(false);
  const [alphaCopied, setAlphaCopied] = useState(false);
  const [deletingId, setDeletingId] = useState<number | null>(null);
  const [testingId, setTestingId] = useState<number | null>(null);
  const [testResults, setTestResults] = useState<Record<number, TestResult>>({});

  // ── Ingestion ──────────────────────────────────────────────────────────────
  const [ingestionStatuses, setIngestionStatuses] = useState<IngestionStatus[]>([]);
  const [ingestingId, setIngestingId] = useState<number | null>(null);
  const [ingestResults, setIngestResults] = useState<Record<number, IngestionResult>>({});
  const [ingestErrors, setIngestErrors] = useState<Record<number, string>>({});

  // ── AI Model ──────────────────────────────────────────────────────────────
  const [modelStatuses, setModelStatuses] = useState<ModelStatus[]>([]);
  const [trainingId, setTrainingId] = useState<number | null>(null);
  const [trainResults, setTrainResults] = useState<Record<number, TrainResult>>({});
  const [trainErrors, setTrainErrors] = useState<Record<number, string>>({});

  // ── Email alerts ───────────────────────────────────────────────────────────
  const [emailConfig, setEmailConfig] = useState<EmailConfig | null | undefined>(undefined);
  const [emailInput, setEmailInput] = useState("");
  const [emailLevel, setEmailLevel] = useState<EmailAlertLevel>("HIGH");
  const [savingEmail, setSavingEmail] = useState(false);
  const [emailSaveError, setEmailSaveError] = useState<string | null>(null);
  const [deletingEmail, setDeletingEmail] = useState(false);
  const [resendingVerification, setResendingVerification] = useState(false);
  const [emailVerifyBanner, setEmailVerifyBanner] = useState<{ success: boolean; message: string } | null>(null);

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
    fetchModelStatus(tenantId).then(setModelStatuses).catch(console.error);
    fetchEmailConfig(tenantId).then((cfg) => {
      setEmailConfig(cfg);
      if (cfg?.alert_level) setEmailLevel(cfg.alert_level as EmailAlertLevel);
    }).catch(console.error);
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

  // ── AI Model handlers ──────────────────────────────────────────────────────

  async function handleTrain(connId: number) {
    if (!tenantId) return;
    setTrainingId(connId);
    setTrainErrors((prev) => { const r = { ...prev }; delete r[connId]; return r; });
    try {
      const result = await trainAccountModel(tenantId, connId);
      setTrainResults((prev) => ({ ...prev, [connId]: result }));
      // Refresh model statuses to reflect new trained_at / has_model
      const updated = await fetchModelStatus(tenantId);
      setModelStatuses(updated);
    } catch (err: unknown) {
      setTrainErrors((prev) => ({
        ...prev,
        [connId]: err instanceof Error ? err.message : "Training failed",
      }));
    } finally {
      setTrainingId(null);
    }
  }

  // ── Email alert handlers ───────────────────────────────────────────────────

  async function handleSaveEmail(e: FormEvent) {
    e.preventDefault();
    if (!tenantId || !emailInput.trim()) return;
    setSavingEmail(true);
    setEmailSaveError(null);
    setEmailVerifyBanner(null);
    try {
      const updated = await saveEmailConfig(tenantId, emailInput.trim(), emailLevel);
      setEmailConfig(updated);
      setEmailInput("");
      setEmailVerifyBanner({ success: true, message: `Verification email sent to ${updated.alert_email}` });
    } catch (err: unknown) {
      setEmailSaveError(err instanceof Error ? err.message : "Save failed");
    } finally {
      setSavingEmail(false);
    }
  }

  async function handleDeleteEmail() {
    if (!tenantId) return;
    setDeletingEmail(true);
    try {
      await deleteEmailConfig(tenantId);
      setEmailConfig(null);
      setEmailInput("");
      setEmailVerifyBanner(null);
    } catch (e) { console.error(e); }
    finally { setDeletingEmail(false); }
  }

  async function handleResendVerification() {
    if (!tenantId) return;
    setResendingVerification(true);
    setEmailVerifyBanner(null);
    try {
      const res = await resendEmailVerification(tenantId);
      setEmailVerifyBanner(res);
    } catch {
      setEmailVerifyBanner({ success: false, message: "Failed to send verification email" });
    } finally {
      setResendingVerification(false);
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
      <Suspense fallback={null}>
        <EmailTokenVerifier
          onVerified={setEmailVerifyBanner}
          tenantId={tenantId}
          setEmailConfig={setEmailConfig}
        />
      </Suspense>
      <NavSidebar />

      <main className="flex-1 overflow-auto p-8 space-y-8">
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
          </div>
        </section>

        {/* ── Section 2: Team ── */}
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

        {/* ── Section 3: Stripe Connections ── */}
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

            {/* Alpha gate — add connection locked */}
            {connections.length < MAX_CONNECTIONS && (
              <div className="pt-1 space-y-3">
                <p className="text-xs font-medium text-gray-500 uppercase tracking-wide">
                  Add connection
                </p>
                <div className="flex items-start gap-3 bg-amber-950/40 border border-amber-800/50
                                rounded-xl px-4 py-3.5">
                  <span className="text-amber-400 text-lg mt-0.5">🔒</span>
                  <div className="space-y-1">
                    <p className="text-sm font-medium text-amber-300">Closed alpha</p>
                    <p className="text-xs text-amber-200/70 leading-relaxed">
                      Connecting a real Stripe account is currently invite-only.
                      Request access and we&apos;ll unlock it for you.
                    </p>
                  </div>
                </div>
                <button
                  type="button"
                  onClick={() => setShowAlphaModal(true)}
                  className="w-full bg-gray-800 hover:bg-gray-700 border border-gray-700
                             text-white text-sm font-semibold rounded-lg px-4 py-2.5
                             transition-colors flex items-center justify-center gap-2"
                >
                  <span>Request Stripe access</span>
                  <span className="text-gray-400">→</span>
                </button>
              </div>
            )}

            <p className="text-xs text-gray-600">
              Keys are stored encrypted server-side. Test each connection to discover its Stripe account ID
              and enable scheduled ingestion.
            </p>
          </section>
        )}

        {/* ── Section 4: Data Ingestion ── */}
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

        {/* ── Section 5: AI Model ── */}
        {!isAdmin && (
          <section className="bg-gray-900 border border-gray-800 rounded-2xl p-6 space-y-5">
            <div>
              <h2 className="text-base font-semibold text-gray-200">AI Model</h2>
              <p className="text-xs text-gray-500 mt-0.5">
                Train a personalized Isolation Forest per Stripe account. Requires 30+ days of ingested data.
                The scheduler retrains automatically every night at 03:00 UTC.
              </p>
            </div>

            {connections.length === 0 && (
              <p className="text-sm text-gray-600">
                Add and test a Stripe connection to enable AI model training.
              </p>
            )}

            {modelStatuses.map((ms) => {
              const isTraining = trainingId === ms.connection_id;
              const result = trainResults[ms.connection_id];
              const error = trainErrors[ms.connection_id];
              const canTrain = ms.has_enough_data && !!ms.stripe_account_id;

              return (
                <div
                  key={ms.connection_id}
                  className="bg-gray-800 border border-gray-700 rounded-xl p-4 space-y-4"
                >
                  {/* Header */}
                  <div className="flex items-start justify-between gap-3">
                    <div>
                      <p className="text-sm font-semibold text-white">{ms.connection_name}</p>
                      {ms.stripe_account_id && (
                        <p className="text-xs font-mono text-gray-500">{ms.stripe_account_id}</p>
                      )}
                    </div>
                    <span className={`shrink-0 text-xs font-semibold px-2 py-0.5 rounded-full border ${
                      ms.has_model
                        ? "bg-indigo-950 text-indigo-300 border-indigo-700"
                        : "bg-gray-700 text-gray-400 border-gray-600"
                    }`}>
                      {ms.has_model ? "Custom model" : "Base model"}
                    </span>
                  </div>

                  {ms.stripe_account_id ? (
                    <div className="space-y-1">
                      <p className="text-xs font-medium text-gray-500 uppercase tracking-wide">
                        Data available
                      </p>
                      <div className="grid grid-cols-[140px_1fr] gap-y-1 text-xs">
                        <span className="text-gray-500">Daily snapshots</span>
                        <span className="text-gray-300 font-mono">{ms.days_available}</span>
                        <span className="text-gray-500">Date range</span>
                        <span className="text-gray-300">
                          {ms.first_date && ms.last_date
                            ? `${ms.first_date} → ${ms.last_date}`
                            : <span className="text-gray-600">No data yet</span>}
                        </span>
                        <span className="text-gray-500">Threshold</span>
                        <span className={ms.has_enough_data ? "text-emerald-400" : "text-amber-400"}>
                          {ms.has_enough_data
                            ? `✓ Ready (${ms.days_available}/30 days)`
                            : `✗ Need more data (${ms.days_available}/30 days)`}
                        </span>
                      </div>
                    </div>
                  ) : (
                    <p className="text-xs text-gray-600">
                      Test this connection first to discover the Stripe account ID.
                    </p>
                  )}

                  {ms.has_model && ms.trained_at && (
                    <div className="space-y-1">
                      <p className="text-xs font-medium text-gray-500 uppercase tracking-wide">Model</p>
                      <p className="text-xs text-gray-400">
                        Trained {format(parseISO(ms.trained_at), "MMM d, yyyy 'at' HH:mm")}
                      </p>
                    </div>
                  )}

                  {result && (
                    <div className={`rounded-lg px-3 py-2 text-xs space-y-1 ${
                      result.status === "trained"
                        ? "bg-indigo-950 border border-indigo-800"
                        : "bg-amber-950 border border-amber-800"
                    }`}>
                      {result.status === "trained" ? (
                        <>
                          <p className="text-indigo-300 font-semibold">Model trained successfully</p>
                          {result.trained_at && (
                            <p className="text-gray-400">
                              {format(parseISO(result.trained_at), "MMM d, yyyy 'at' HH:mm")}
                              {" · "}{result.days_available} day{result.days_available !== 1 ? "s" : ""} of data
                            </p>
                          )}
                        </>
                      ) : (
                        <p className="text-amber-300">
                          Not enough data — {result.days_available}/30 days available
                        </p>
                      )}
                    </div>
                  )}

                  {error && (
                    <p className="text-xs text-red-400 bg-red-950 border border-red-800 rounded-lg px-3 py-2">
                      {error}
                    </p>
                  )}

                  <button
                    onClick={() => handleTrain(ms.connection_id)}
                    disabled={isTraining || !canTrain}
                    title={!ms.stripe_account_id
                      ? "Test connection first"
                      : !ms.has_enough_data
                      ? `Need ${30 - ms.days_available} more days of data`
                      : undefined}
                    className="w-full bg-indigo-600 hover:bg-indigo-500 disabled:opacity-40
                               disabled:cursor-not-allowed text-white text-sm font-semibold
                               rounded-lg px-4 py-2.5 transition-colors"
                  >
                    {isTraining ? "Training…" : ms.has_model ? "Retrain model" : "Train model"}
                  </button>
                </div>
              );
            })}

            <p className="text-xs text-gray-600">
              The custom model learns your account's specific patterns (seasonality, volume, fee profile)
              and replaces the generic base model for anomaly detection on this account.
            </p>
          </section>
        )}

        {/* ── Section 6: Slack Alerts ── */}
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

        {/* ── Section 7: Email Alerts ── */}
        {!isAdmin && (
          <section className="bg-gray-900 border border-gray-800 rounded-2xl p-6 space-y-5">
            <div className="flex items-center justify-between">
              <div>
                <h2 className="text-base font-semibold text-gray-200">Email Alerts</h2>
                <p className="text-xs text-gray-500 mt-0.5">
                  Receive an email whenever anomalies are detected.
                </p>
              </div>
              {emailConfig !== undefined && (
                <span className={`text-xs font-semibold px-3 py-1 rounded-full border ${
                  emailConfig?.is_verified
                    ? "bg-emerald-950 text-emerald-400 border-emerald-800"
                    : emailConfig
                    ? "bg-amber-950 text-amber-400 border-amber-800"
                    : "bg-gray-800 text-gray-500 border-gray-700"
                }`}>
                  {emailConfig?.is_verified
                    ? "● Verified"
                    : emailConfig
                    ? "○ Pending verification"
                    : "○ Not configured"}
                </span>
              )}
            </div>

            {emailVerifyBanner && (
              <div className={`rounded-lg px-4 py-3 text-sm flex items-start justify-between gap-3 ${
                emailVerifyBanner.success
                  ? "bg-emerald-950 border border-emerald-800 text-emerald-300"
                  : "bg-red-950 border border-red-800 text-red-400"
              }`}>
                <span>{emailVerifyBanner.success ? "✓ " : "✕ "}{emailVerifyBanner.message}</span>
                <button
                  onClick={() => setEmailVerifyBanner(null)}
                  className="shrink-0 text-xs opacity-60 hover:opacity-100"
                >
                  ✕
                </button>
              </div>
            )}

            {emailConfig && (
              <div className="bg-gray-800 border border-gray-700 rounded-xl p-4 space-y-3">
                <div className="flex items-start justify-between gap-3">
                  <div>
                    <p className="text-sm font-semibold text-white">{emailConfig.alert_email}</p>
                    <p className="text-xs text-gray-500 mt-0.5">
                      Alert level:{" "}
                      <span className="text-gray-300">
                        {LEVEL_LABELS[emailConfig.alert_level] ?? emailConfig.alert_level}
                      </span>
                    </p>
                    {emailConfig.is_verified && emailConfig.verified_at && (
                      <p className="text-xs text-gray-600 mt-0.5">
                        Verified {format(parseISO(emailConfig.verified_at), "MMM d, yyyy 'at' HH:mm")}
                      </p>
                    )}
                  </div>
                  <button
                    onClick={handleDeleteEmail}
                    disabled={deletingEmail}
                    className="shrink-0 text-xs text-red-400 hover:text-red-300 border border-red-800
                               hover:bg-red-950 px-3 py-1.5 rounded-lg transition-colors disabled:opacity-50"
                  >
                    {deletingEmail ? "Removing…" : "Remove"}
                  </button>
                </div>
                {!emailConfig.is_verified && (
                  <div className="border-t border-gray-700 pt-3 flex items-center gap-3">
                    <p className="text-xs text-amber-400 flex-1">
                      Check your inbox for a confirmation link.
                    </p>
                    <button
                      onClick={handleResendVerification}
                      disabled={resendingVerification}
                      className="text-xs px-3 py-1.5 rounded-lg bg-gray-700 hover:bg-gray-600
                                 text-gray-200 transition-colors disabled:opacity-50"
                    >
                      {resendingVerification ? "Sending…" : "Resend"}
                    </button>
                  </div>
                )}
              </div>
            )}

            <form onSubmit={handleSaveEmail} className="space-y-4">
              <div>
                <label className="block text-xs font-medium text-gray-500 uppercase tracking-wide mb-1.5">
                  {emailConfig ? "Update email address" : "Email address"}
                </label>
                <input
                  type="email"
                  value={emailInput}
                  onChange={(e) => setEmailInput(e.target.value)}
                  placeholder="alerts@yourcompany.com"
                  className="w-full bg-gray-800 border border-gray-700 text-gray-200 text-sm
                             rounded-lg px-4 py-2.5
                             focus:outline-none focus:ring-2 focus:ring-indigo-500"
                />
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
                      onClick={() => setEmailLevel(value as EmailAlertLevel)}
                      className={`text-center px-3 py-3 rounded-xl border text-sm transition-colors ${
                        emailLevel === value
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

              {emailSaveError && (
                <p className="text-sm text-red-400 bg-red-950 border border-red-800 rounded-lg px-4 py-2">
                  {emailSaveError}
                </p>
              )}

              <button
                type="submit"
                disabled={savingEmail || !emailInput.trim()}
                className="w-full bg-indigo-600 hover:bg-indigo-500 disabled:opacity-50
                           disabled:cursor-not-allowed text-white text-sm font-semibold
                           rounded-lg px-4 py-2.5 transition-colors"
              >
                {savingEmail ? "Saving…" : emailConfig ? "Update email" : "Save email address"}
              </button>
            </form>

            <p className="text-xs text-gray-600">
              A confirmation link will be sent to the address. Alerts fire automatically
              after each detection run once the address is verified.
            </p>
          </section>
        )}
      </main>

      {/* Alpha gate modal */}
      {showAlphaModal && (
        <div
          className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 backdrop-blur-sm px-4"
          onClick={() => setShowAlphaModal(false)}
        >
          <div
            className="bg-gray-900 border border-gray-700 rounded-2xl p-8 max-w-sm w-full space-y-5 shadow-2xl"
            onClick={(e) => e.stopPropagation()}
          >
            <div className="text-center space-y-2">
              <div className="text-4xl">🔒</div>
              <h2 className="text-lg font-bold text-white">Closed alpha</h2>
              <p className="text-sm text-gray-400 leading-relaxed">
                Real Stripe connections are invite-only during the alpha.
                Request an access by mail.
              </p>
            </div>

            <button
              type="button"
              onClick={() => {
                navigator.clipboard.writeText("mathis.le-mouel@orange.fr");
                setAlphaCopied(true);
                setTimeout(() => setAlphaCopied(false), 2000);
              }}
              className="flex items-center justify-center gap-2 w-full bg-indigo-600
                         hover:bg-indigo-500 text-white text-sm font-semibold rounded-xl
                         px-4 py-3 transition-colors"
            >
              <span>{alphaCopied ? "✓" : "✉️"}</span>
              <span>{alphaCopied ? "Copied!" : "Copy email — mathis.le-mouel@orange.fr"}</span>
            </button>

            <button
              type="button"
              onClick={() => setShowAlphaModal(false)}
              className="w-full text-sm text-gray-500 hover:text-gray-300 transition-colors"
            >
              Close
            </button>
          </div>
        </div>
      )}
    </div>
  );
}

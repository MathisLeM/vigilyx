const API = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

function getToken(): string | null {
  if (typeof window === "undefined") return null;
  return localStorage.getItem("token");
}

async function request<T>(
  path: string,
  options: RequestInit = {}
): Promise<T> {
  const token = getToken();
  const headers: Record<string, string> = {
    "Content-Type": "application/json",
    ...(options.headers as Record<string, string>),
  };
  if (token) headers["Authorization"] = `Bearer ${token}`;

  const res = await fetch(`${API}${path}`, { ...options, headers });
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: res.statusText }));
    throw new Error(err.detail ?? "API error");
  }
  // 204 No Content — no body
  if (res.status === 204) return undefined as unknown as T;
  return res.json();
}

// ── Auth ──────────────────────────────────────────────────────────────────

export interface LoginResponse {
  access_token: string;
  token_type: string;
  tenant_id: number | null;
  email: string;
  is_admin: boolean;
}

export async function login(email: string, password: string): Promise<LoginResponse> {
  const body = new URLSearchParams({ username: email, password });
  const res = await fetch(`${API}/auth/login`, {
    method: "POST",
    headers: { "Content-Type": "application/x-www-form-urlencoded" },
    body: body.toString(),
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: "Login failed" }));
    throw new Error(err.detail ?? "Login failed");
  }
  return res.json();
}

// ── Tenants ───────────────────────────────────────────────────────────────

export interface Tenant {
  id: number;
  name: string;
  slug: string;
}

export function fetchTenants(): Promise<Tenant[]> {
  return request<Tenant[]>("/tenants/");
}

// ── Daily Metric Snapshots (Phase 1+) ─────────────────────────────────────
// Served from /metrics/ — reads from daily_revenue_metrics (Stripe-aligned).
// All monetary values are in DOLLARS (float).

export interface Snapshot {
  id: number;
  tenant_id: number;
  stripe_account_id: string;
  currency: string;
  snapshot_date: string;

  // Revenue
  gross_revenue_usd: number;
  net_revenue_usd: number;
  charge_count: number;
  avg_charge_value_usd: number | null;
  fee_rate: number | null;        // 0.0 – 1.0

  // Refunds
  refund_amount_usd: number;
  refund_rate: number | null;     // 0.0 – 1.0

  // Disputes
  dispute_amount_usd: number;

  // Composite
  net_balance_change_usd: number | null;
}

export function fetchSnapshots(
  tenantId: number,
  startDate: string,
  endDate: string,
  stripeAccountId?: string
): Promise<Snapshot[]> {
  const params = new URLSearchParams({
    start_date: startDate,
    end_date: endDate,
  });
  if (stripeAccountId) params.set("stripe_account_id", stripeAccountId);
  return request<Snapshot[]>(`/metrics/${tenantId}/snapshots?${params}`);
}

// ── Alerts ────────────────────────────────────────────────────────────────

export interface Alert {
  id: number;
  tenant_id: number;
  stripe_account_id: string | null;
  snapshot_date: string;
  metric_name: string;
  metric_value: number;
  detection_method: "MAD" | "ZSCORE" | "DUAL";
  score: number;
  threshold: number;
  direction: "spike" | "drop";
  pct_deviation: number | null;
  is_dual_confirmed: boolean;
  hint: string;
  severity: "LOW" | "MEDIUM" | "HIGH";
  is_resolved: boolean;
  resolved_at: string | null;
  created_at: string;
}

export function fetchAlerts(
  tenantId: number,
  resolved: boolean,
  startDate: string,
  endDate: string,
  stripeAccountId?: string
): Promise<Alert[]> {
  const params = new URLSearchParams({
    resolved: String(resolved),
    start_date: startDate,
    end_date: endDate,
  });
  if (stripeAccountId) params.set("stripe_account_id", stripeAccountId);
  return request<Alert[]>(`/alerts/${tenantId}/?${params}`);
}

export function resolveAlert(tenantId: number, alertId: number): Promise<Alert> {
  return request<Alert>(`/alerts/${tenantId}/${alertId}/resolve`, { method: "PATCH" });
}

export interface DailyAlertGroup {
  snapshot_date: string;
  total_alerts: number;
  dual_count: number;
  highest_severity: "LOW" | "MEDIUM" | "HIGH";
  directions: string[];
  metrics_affected: string[];
  combo_hint: string;
  alerts: Alert[];
}

export function fetchDailyAlerts(
  tenantId: number,
  resolved: boolean,
  startDate: string,
  endDate: string,
  stripeAccountId?: string
): Promise<DailyAlertGroup[]> {
  const params = new URLSearchParams({
    resolved: String(resolved),
    start_date: startDate,
    end_date: endDate,
  });
  if (stripeAccountId) params.set("stripe_account_id", stripeAccountId);
  return request<DailyAlertGroup[]>(`/alerts/${tenantId}/daily?${params}`);
}

export function runDetection(
  tenantId: number,
  stripeAccountId?: string
): Promise<{ created: number }> {
  return request<{ created: number }>(`/alerts/${tenantId}/run-detection`, {
    method: "POST",
    body: JSON.stringify({
      detection_days: 7,
      stripe_account_id: stripeAccountId ?? null,
    }),
  });
}

// ── Stripe Connections ────────────────────────────────────────────────────

export interface StripeConnection {
  id: number;
  tenant_id: number;
  name: string;
  has_key: boolean;
  stripe_account_id: string | null;
  created_at: string | null;
  updated_at: string | null;
}

export interface TestResult {
  success: boolean;
  message: string;
  account_name: string | null;
  stripe_account_id: string | null;
}

export function listStripeConnections(tenantId: number): Promise<StripeConnection[]> {
  return request<StripeConnection[]>(`/config/${tenantId}/stripe-connections`);
}

export function addStripeConnection(
  tenantId: number,
  name: string,
  stripeApiKey: string
): Promise<StripeConnection> {
  return request<StripeConnection>(`/config/${tenantId}/stripe-connections`, {
    method: "POST",
    body: JSON.stringify({ name, stripe_api_key: stripeApiKey }),
  });
}

export function updateStripeConnection(
  tenantId: number,
  connId: number,
  patch: { name?: string; stripe_api_key?: string }
): Promise<StripeConnection> {
  return request<StripeConnection>(
    `/config/${tenantId}/stripe-connections/${connId}`,
    { method: "PUT", body: JSON.stringify(patch) }
  );
}

export function deleteStripeConnection(
  tenantId: number,
  connId: number
): Promise<void> {
  return request<void>(`/config/${tenantId}/stripe-connections/${connId}`, {
    method: "DELETE",
  });
}

export function testStripeConnection(
  tenantId: number,
  connId: number
): Promise<TestResult> {
  return request<TestResult>(
    `/config/${tenantId}/stripe-connections/${connId}/test`,
    { method: "POST" }
  );
}

// ── Ingestion (Phase 2/3) ──────────────────────────────────────────────────

export interface IngestionResult {
  tenant_id: number;
  stripe_account_id: string;
  connection_id: number;
  connection_name: string;
  raw_inserted: number;
  raw_skipped: number;
  features_written: number;
  features_skipped: number;
  date_range: [string, string] | null;
  duration_seconds: number | null;
  error: string | null;
}

export interface IngestionStatus {
  tenant_id: number;
  connection_id: number;
  connection_name: string;
  stripe_account_id: string | null;
  last_ingested_at: string | null;
  total_raw_rows: number;
  has_key: boolean;
}

export function runIngestion(
  tenantId: number,
  connectionId: number,
  forceFull = false
): Promise<IngestionResult> {
  return request<IngestionResult>(
    `/ingestion/${tenantId}/run?connection_id=${connectionId}&force_full=${forceFull}`,
    { method: "POST" }
  );
}

export function fetchIngestionStatus(tenantId: number): Promise<IngestionStatus[]> {
  return request<IngestionStatus[]>(`/ingestion/${tenantId}/status`);
}

// ── AI Model ───────────────────────────────────────────────────────────────────

export interface ModelStatus {
  connection_id: number;
  connection_name: string;
  stripe_account_id: string | null;
  days_available: number;
  first_date: string | null;
  last_date: string | null;
  has_enough_data: boolean;
  has_model: boolean;
  trained_at: string | null;
  model_type: "custom" | "base";
}

export interface TrainResult {
  status: "trained" | "not_enough_data";
  days_available: number;
  first_date: string | null;
  last_date: string | null;
  trained_at: string | null;
  model_path: string | null;
}

export function fetchModelStatus(tenantId: number): Promise<ModelStatus[]> {
  return request<ModelStatus[]>(`/ingestion/${tenantId}/model-status`);
}

export function trainAccountModel(
  tenantId: number,
  connectionId: number
): Promise<TrainResult> {
  return request<TrainResult>(
    `/ingestion/${tenantId}/train?connection_id=${connectionId}`,
    { method: "POST" }
  );
}

// -- Slack Webhooks --------------------------------------------------------

export type SlackAlertLevel = "HIGH" | "MEDIUM_AND_HIGH" | "ALL";

export interface SlackConfig {
  tenant_id: number;
  has_slack_webhook: boolean;
  slack_webhook_masked: string | null;
  slack_alert_level: SlackAlertLevel | null;
  updated_at: string | null;
}

export function fetchSlackConfig(tenantId: number): Promise<SlackConfig> {
  return request<SlackConfig>(`/config/${tenantId}/slack`);
}

export function saveSlackConfig(
  tenantId: number,
  webhookUrl: string,
  alertLevel: SlackAlertLevel
): Promise<SlackConfig> {
  return request<SlackConfig>(`/config/${tenantId}/slack`, {
    method: "PUT",
    body: JSON.stringify({ webhook_url: webhookUrl, alert_level: alertLevel }),
  });
}

export function deleteSlackConfig(tenantId: number): Promise<SlackConfig> {
  return request<SlackConfig>(`/config/${tenantId}/slack`, { method: "DELETE" });
}

export function testSlackWebhook(tenantId: number): Promise<TestResult> {
  return request<TestResult>(`/config/${tenantId}/test-slack`, { method: "POST" });
}

// -- Invitations -----------------------------------------------------------

export interface Invitation {
  id: number;
  tenant_id: number;
  email: string;
  role: string;
  token: string;
  created_at: string;
  expires_at: string;
  accepted_at: string | null;
}

export interface AcceptTokenInfo {
  valid: boolean;
  email: string;
  tenant_name: string;
  expired: boolean;
  already_accepted: boolean;
}

export interface AcceptOut {
  access_token: string;
  token_type: string;
  tenant_id: number;
  email: string;
  is_admin: boolean;
}

export function listInvitations(tenantId: number): Promise<Invitation[]> {
  return request<Invitation[]>(`/invitations/${tenantId}`);
}

export function createInvitation(tenantId: number, email: string): Promise<Invitation> {
  return request<Invitation>(`/invitations/${tenantId}`, {
    method: "POST",
    body: JSON.stringify({ email }),
  });
}

export function revokeInvitation(tenantId: number, invitationId: number): Promise<void> {
  return request<void>(`/invitations/${tenantId}/${invitationId}`, { method: "DELETE" });
}

export function validateInviteToken(token: string): Promise<AcceptTokenInfo> {
  const BASE = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";
  return fetch(`${BASE}/invitations/accept?token=${encodeURIComponent(token)}`)
    .then((r) => {
      if (!r.ok) throw new Error("Invalid invitation");
      return r.json();
    });
}

export function acceptInvitation(token: string, password: string): Promise<AcceptOut> {
  const BASE = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";
  return fetch(`${BASE}/invitations/accept`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ token, password }),
  }).then(async (r) => {
    if (!r.ok) {
      const err = await r.json().catch(() => ({ detail: r.statusText }));
      throw new Error(err.detail ?? "Registration failed");
    }
    return r.json();
  });
}

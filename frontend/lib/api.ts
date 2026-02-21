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
  endDate: string
): Promise<Snapshot[]> {
  return request<Snapshot[]>(
    `/metrics/${tenantId}/snapshots?start_date=${startDate}&end_date=${endDate}`
  );
}

// ── Alerts ────────────────────────────────────────────────────────────────

export interface Alert {
  id: number;
  tenant_id: number;
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
  endDate: string
): Promise<Alert[]> {
  return request<Alert[]>(
    `/alerts/${tenantId}/?resolved=${resolved}&start_date=${startDate}&end_date=${endDate}`
  );
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
  endDate: string
): Promise<DailyAlertGroup[]> {
  return request<DailyAlertGroup[]>(
    `/alerts/${tenantId}/daily?resolved=${resolved}&start_date=${startDate}&end_date=${endDate}`
  );
}

export function runDetection(tenantId: number): Promise<{ created: number }> {
  return request<{ created: number }>(`/alerts/${tenantId}/run-detection`, {
    method: "POST",
    body: JSON.stringify({ detection_days: 7 }),
  });
}

// ── Config ────────────────────────────────────────────────────────────────

export interface TenantConfig {
  tenant_id: number;
  has_stripe_key: boolean;
  stripe_key_masked: string | null;
  updated_at: string | null;
}

export interface TestResult {
  success: boolean;
  message: string;
  account_name: string | null;
}

export function fetchConfig(tenantId: number): Promise<TenantConfig> {
  return request<TenantConfig>(`/config/${tenantId}`);
}

export function saveStripeKey(tenantId: number, key: string): Promise<TenantConfig> {
  return request<TenantConfig>(`/config/${tenantId}`, {
    method: "PUT",
    body: JSON.stringify({ stripe_api_key: key }),
  });
}

export function deleteStripeKey(tenantId: number): Promise<TenantConfig> {
  return request<TenantConfig>(`/config/${tenantId}/stripe-key`, { method: "DELETE" });
}

export function testStripeConnection(tenantId: number): Promise<TestResult> {
  return request<TestResult>(`/config/${tenantId}/test-stripe`, { method: "POST" });
}

// ── Ingestion (Phase 2) ────────────────────────────────────────────────────

export interface IngestionResult {
  tenant_id: number;
  stripe_account_id: string;
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
  stripe_account_id: string;
  last_ingested_at: string | null;
  total_raw_rows: number;
  has_stripe_key: boolean;
}

export function runIngestion(
  tenantId: number,
  forceFull = false
): Promise<IngestionResult> {
  return request<IngestionResult>(
    `/ingestion/${tenantId}/run?force_full=${forceFull}`,
    { method: "POST" }
  );
}

export function fetchIngestionStatus(tenantId: number): Promise<IngestionStatus> {
  return request<IngestionStatus>(`/ingestion/${tenantId}/status`);
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

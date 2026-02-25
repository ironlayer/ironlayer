/* ------------------------------------------------------------------ */
/* Typed API client for the IronLayer control-plane backend            */
/* ------------------------------------------------------------------ */

import type {
  ApiError,
  ModelFilters,
  ModelInfo,
  ModelLineage,
  Plan,
  PlanListItem,
  PlanWithAdvisory,
  RunFilters,
  RunRecord,
  RunTelemetry,
} from './types';

// VITE_API_URL is the API *origin* only (e.g. "http://localhost:8000").
// When unset, requests use the same origin (works behind a proxy or same-domain deploy).
const BASE_URL = (import.meta.env.VITE_API_URL ?? '') + '/api/v1';

/* ------------------------------------------------------------------ */
/* Transport                                                           */
/* ------------------------------------------------------------------ */

class IronLayerApiError extends Error {
  status: number;
  detail: string;

  constructor(status: number, detail: string) {
    super(`[${status}] ${detail}`);
    this.name = 'IronLayerApiError';
    this.status = status;
    this.detail = detail;
  }
}

/**
 * In-memory access token.  Set by the AuthContext after login, signup,
 * session restore, or successful token refresh.
 *
 * SECURITY: This is intentionally stored in a module-scoped variable
 * (memory only) rather than localStorage to prevent XSS token theft.
 */
let _authToken: string | null = null;

export function setAuthToken(token: string | null): void {
  _authToken = token;
}

/* ------------------------------------------------------------------ */
/* CSRF helper                                                         */
/* ------------------------------------------------------------------ */

/**
 * Read the CSRF token from the non-HttpOnly ``csrf_token`` cookie.
 * The backend's CSRFMiddleware sets this cookie on safe requests.
 */
function getCsrfToken(): string {
  const match = document.cookie.match(/csrf_token=([^;]+)/);
  return match ? match[1] : '';
}

/* ------------------------------------------------------------------ */
/* Token refresh with deduplication (Phase 1.13)                       */
/* ------------------------------------------------------------------ */

/**
 * Prevents concurrent refresh attempts.  When multiple 401 responses
 * arrive simultaneously, only one refresh request is issued.
 */
let _isRefreshing = false;
let _refreshPromise: Promise<string | null> | null = null;

interface QueueEntry {
  resolve: (token: string | null) => void;
  reject: (error: unknown) => void;
}

let _failedQueue: QueueEntry[] = [];

function processQueue(error: unknown, token: string | null): void {
  _failedQueue.forEach(({ resolve, reject }) => {
    if (error) reject(error);
    else resolve(token);
  });
  _failedQueue = [];
}

/**
 * Perform the actual token refresh via the cookie-based endpoint.
 * Returns the new access token on success, or ``null`` on failure.
 */
async function doRefresh(): Promise<string | null> {
  try {
    const resp = await fetch(`${BASE_URL}/auth/refresh`, {
      method: 'POST',
      credentials: 'include',
      headers: {
        'Content-Type': 'application/json',
        'X-CSRF-Token': getCsrfToken(),
      },
    });
    if (!resp.ok) {
      return null;
    }
    const body = (await resp.json()) as { access_token: string };
    return body.access_token;
  } catch {
    return null;
  }
}

/**
 * Attempt to refresh the access token, deduplicating concurrent calls.
 * Called by the 401 interceptor.
 */
function refreshAccessToken(): Promise<string | null> {
  if (_refreshPromise) return _refreshPromise;

  _isRefreshing = true;
  _refreshPromise = doRefresh()
    .then((token) => {
      if (token) {
        _authToken = token;
      }
      processQueue(null, token);
      return token;
    })
    .catch((err: unknown) => {
      processQueue(err, null);
      return null;
    })
    .finally(() => {
      _isRefreshing = false;
      _refreshPromise = null;
    });

  return _refreshPromise;
}

/**
 * Callback to clear auth state and redirect to login.
 * Set by the AuthContext via ``setLogoutHandler``.
 */
let _logoutHandler: (() => void) | null = null;

export function setLogoutHandler(handler: (() => void) | null): void {
  _logoutHandler = handler;
}

function triggerLogout(): void {
  _authToken = null;
  if (_logoutHandler) _logoutHandler();
}

/* ------------------------------------------------------------------ */
/* Core request function with 401 retry                                */
/* ------------------------------------------------------------------ */

async function request<T>(
  path: string,
  options: RequestInit = {},
  _isRetry = false,
): Promise<T> {
  const url = `${BASE_URL}${path}`;
  const headers: HeadersInit = {
    'Content-Type': 'application/json',
    'X-CSRF-Token': getCsrfToken(),
    ...(_authToken ? { Authorization: `Bearer ${_authToken}` } : {}),
    ...(options.headers as Record<string, string> | undefined),
  };

  const response = await fetch(url, {
    ...options,
    headers,
    credentials: 'include', // Send cookies (refresh_token, csrf_token).
    signal: options.signal,
  });

  // Handle 401: attempt token refresh (unless this IS a retry or a refresh request).
  if (response.status === 401 && !_isRetry) {
    // CRITICAL: Never retry a request to the refresh endpoint itself.
    // This prevents infinite loops when the refresh token is expired.
    if (path.includes('/auth/refresh') || path.includes('/auth/session')) {
      triggerLogout();
      throw new IronLayerApiError(401, 'Session expired');
    }

    // If a refresh is already in progress, queue this request.
    if (_isRefreshing) {
      return new Promise<string | null>((resolve, reject) => {
        _failedQueue.push({ resolve, reject });
      }).then((token) => {
        if (!token) {
          throw new IronLayerApiError(401, 'Session expired');
        }
        // Retry the original request with the new token.
        return request<T>(path, options, true);
      });
    }

    // Initiate a refresh.
    const newToken = await refreshAccessToken();
    if (newToken) {
      // Retry the original request with the new token.
      return request<T>(path, options, true);
    }

    // Refresh failed — force logout.
    triggerLogout();
    throw new IronLayerApiError(401, 'Session expired');
  }

  if (!response.ok) {
    let detail = response.statusText;
    try {
      const body = (await response.json()) as ApiError;
      detail = body.detail ?? detail;
    } catch {
      /* body was not JSON -- use statusText */
    }
    throw new IronLayerApiError(response.status, detail);
  }

  return response.json() as Promise<T>;
}

function qs(params: Record<string, string | number | boolean | undefined>): string {
  const parts: string[] = [];
  for (const [key, value] of Object.entries(params)) {
    if (value !== undefined && value !== '') {
      parts.push(`${encodeURIComponent(key)}=${encodeURIComponent(String(value))}`);
    }
  }
  return parts.length > 0 ? `?${parts.join('&')}` : '';
}

/* ------------------------------------------------------------------ */
/* Plans                                                               */
/* ------------------------------------------------------------------ */

export async function fetchPlans(
  limit = 20,
  offset = 0,
  signal?: AbortSignal,
): Promise<PlanListItem[]> {
  return request<PlanListItem[]>(`/plans${qs({ limit, offset })}`, { signal });
}

export async function fetchPlan(planId: string, signal?: AbortSignal): Promise<Plan> {
  return request<Plan>(`/plans/${encodeURIComponent(planId)}`, { signal });
}

export async function generatePlan(
  repoPath: string,
  baseSha: string,
  targetSha: string,
): Promise<Plan> {
  return request<Plan>('/plans/generate', {
    method: 'POST',
    body: JSON.stringify({
      repo_path: repoPath,
      base_sha: baseSha,
      target_sha: targetSha,
    }),
  });
}

export async function augmentPlan(planId: string): Promise<PlanWithAdvisory> {
  return request<PlanWithAdvisory>(
    `/plans/${encodeURIComponent(planId)}/augment`,
    { method: 'POST' },
  );
}

export async function approvePlan(
  planId: string,
  displayName?: string,
  comment?: string,
): Promise<Plan> {
  return request<Plan>(
    `/plans/${encodeURIComponent(planId)}/approve`,
    {
      method: 'POST',
      body: JSON.stringify({
        display_name: displayName ?? null,
        comment: comment ?? '',
      }),
    },
  );
}

export async function rejectPlan(
  planId: string,
  reason: string,
  displayName?: string,
): Promise<Plan> {
  return request<Plan>(
    `/plans/${encodeURIComponent(planId)}/reject`,
    {
      method: 'POST',
      body: JSON.stringify({
        display_name: displayName ?? null,
        reason,
      }),
    },
  );
}

export async function applyPlan(
  planId: string,
  approvedBy?: string,
  clusterOverride?: string,
): Promise<RunRecord[]> {
  return request<RunRecord[]>(
    `/plans/${encodeURIComponent(planId)}/apply`,
    {
      method: 'POST',
      body: JSON.stringify({
        approved_by: approvedBy,
        cluster_override: clusterOverride,
      }),
    },
  );
}

/* ------------------------------------------------------------------ */
/* Models                                                              */
/* ------------------------------------------------------------------ */

export async function fetchModels(
  filters?: ModelFilters,
  signal?: AbortSignal,
): Promise<ModelInfo[]> {
  const params: Record<string, string | undefined> = {
    kind: filters?.kind,
    owner: filters?.owner,
    tag: filters?.tag,
    search: filters?.search,
  };
  return request<ModelInfo[]>(`/models${qs(params)}`, { signal });
}

export async function fetchModel(modelName: string, signal?: AbortSignal): Promise<ModelInfo> {
  return request<ModelInfo>(`/models/${encodeURIComponent(modelName)}`, { signal });
}

export async function fetchModelLineage(
  modelName: string,
  signal?: AbortSignal,
): Promise<ModelLineage> {
  return request<ModelLineage>(
    `/models/${encodeURIComponent(modelName)}/lineage`,
    { signal },
  );
}

/* ------------------------------------------------------------------ */
/* Runs                                                                */
/* ------------------------------------------------------------------ */

export async function fetchRuns(filters?: RunFilters, signal?: AbortSignal): Promise<RunRecord[]> {
  const params: Record<string, string | number | undefined> = {
    plan_id: filters?.plan_id,
    model_name: filters?.model_name,
    status: filters?.status,
    limit: filters?.limit,
    offset: filters?.offset,
  };
  return request<RunRecord[]>(`/runs${qs(params)}`, { signal });
}

export async function fetchRun(runId: string, signal?: AbortSignal): Promise<RunRecord> {
  return request<RunRecord>(`/runs/${encodeURIComponent(runId)}`, { signal });
}

export async function fetchRunTelemetry(
  runId: string,
): Promise<RunTelemetry | null> {
  return request<RunTelemetry>(
    `/runs/${encodeURIComponent(runId)}/telemetry`,
  );
}

/* ------------------------------------------------------------------ */
/* Backfills                                                           */
/* ------------------------------------------------------------------ */

export async function createBackfill(
  modelName: string,
  startDate: string,
  endDate: string,
  clusterSize?: string,
): Promise<Plan> {
  return request<Plan>('/backfills', {
    method: 'POST',
    body: JSON.stringify({
      model_name: modelName,
      start_date: startDate,
      end_date: endDate,
      cluster_size: clusterSize,
    }),
  });
}

/* ------------------------------------------------------------------ */
/* Usage                                                               */
/* ------------------------------------------------------------------ */

export async function fetchUsageSummary(
  days = 30,
  signal?: AbortSignal,
): Promise<import('./types').UsageSummary> {
  return request<import('./types').UsageSummary>(
    `/usage/summary${qs({ days })}`,
    { signal },
  );
}

export async function fetchUsageEvents(
  eventType?: string,
  limit = 50,
  offset = 0,
  signal?: AbortSignal,
): Promise<import('./types').UsageEventsResponse> {
  return request<import('./types').UsageEventsResponse>(
    `/usage/events${qs({ event_type: eventType, limit, offset })}`,
    { signal },
  );
}

/* ------------------------------------------------------------------ */
/* Billing                                                             */
/* ------------------------------------------------------------------ */

export async function fetchBillingPlans(signal?: AbortSignal): Promise<import('./types').BillingPlansResponse> {
  return request<import('./types').BillingPlansResponse>('/billing/plans', { signal });
}

export async function fetchSubscription(signal?: AbortSignal): Promise<import('./types').SubscriptionInfo> {
  return request<import('./types').SubscriptionInfo>('/billing/subscription', { signal });
}

export async function createPortalSession(
  returnUrl: string,
): Promise<import('./types').PortalSession> {
  return request<import('./types').PortalSession>('/billing/portal', {
    method: 'POST',
    body: JSON.stringify({ return_url: returnUrl }),
  });
}

export async function createCheckoutSession(
  priceId: string,
  successUrl: string,
  cancelUrl: string,
): Promise<{ checkout_url: string }> {
  return request<{ checkout_url: string }>('/billing/checkout', {
    method: 'POST',
    body: JSON.stringify({
      price_id: priceId,
      success_url: successUrl,
      cancel_url: cancelUrl,
    }),
  });
}

/* ------------------------------------------------------------------ */
/* Environments                                                        */
/* ------------------------------------------------------------------ */

export async function fetchEnvironments(): Promise<import('./types').Environment[]> {
  return request<import('./types').Environment[]>('/environments');
}

export async function fetchEnvironmentPromotions(
  limit = 10,
): Promise<import('./types').EnvironmentPromotion[]> {
  return request<import('./types').EnvironmentPromotion[]>(
    `/environments/promotions${qs({ limit })}`,
  );
}

export async function createEnvironment(body: {
  name: string;
  catalog: string;
  schema_prefix: string;
  is_ephemeral?: boolean;
  pr_number?: number;
  branch_name?: string;
  expires_at?: string;
  created_by: string;
}): Promise<import('./types').Environment> {
  return request<import('./types').Environment>('/environments', {
    method: 'POST',
    body: JSON.stringify(body),
  });
}

export async function deleteEnvironment(name: string): Promise<void> {
  await request<unknown>(`/environments/${encodeURIComponent(name)}`, {
    method: 'DELETE',
  });
}

export async function cleanupExpiredEnvironments(): Promise<{ deleted_count: number }> {
  return request<{ deleted_count: number }>('/environments/cleanup', {
    method: 'POST',
  });
}

export async function promoteEnvironment(
  sourceName: string,
  body: {
    target_environment: string;
    snapshot_id: string;
    promoted_by: string;
  },
): Promise<import('./types').EnvironmentPromotion> {
  return request<import('./types').EnvironmentPromotion>(
    `/environments/${encodeURIComponent(sourceName)}/promote`,
    {
      method: 'POST',
      body: JSON.stringify(body),
    },
  );
}

/* ------------------------------------------------------------------ */
/* Simulation                                                          */
/* ------------------------------------------------------------------ */

export async function simulateColumnChange(
  sourceModel: string,
  changes: import('./types').ColumnChange[],
): Promise<import('./types').ImpactReport> {
  return request<import('./types').ImpactReport>('/simulation/column-change', {
    method: 'POST',
    body: JSON.stringify({ source_model: sourceModel, changes }),
  });
}

export async function simulatePlan(
  planId: string,
): Promise<Record<string, unknown>> {
  return request<Record<string, unknown>>(
    `/plans/${encodeURIComponent(planId)}/simulate`,
    { method: 'POST' },
  );
}

/* ------------------------------------------------------------------ */
/* Auth                                                                */
/* ------------------------------------------------------------------ */

export interface AuthTokens {
  access_token: string;
  tenant_id: string;
  user: {
    id: string;
    email: string;
    display_name: string;
    role: string;
    tenant_id: string;
  };
}

export interface UserProfile {
  id: string;
  email: string;
  display_name: string;
  role: string;
  tenant_id: string;
  is_active: boolean;
  email_verified: boolean;
  created_at: string | null;
  last_login_at: string | null;
}

export interface ApiKeyInfo {
  id: string;
  name: string;
  key_prefix: string;
  scopes: string[] | null;
  created_at: string | null;
  last_used_at: string | null;
  expires_at: string | null;
}

export interface ApiKeyCreated extends ApiKeyInfo {
  plaintext_key: string;
}

export async function loginApi(
  email: string,
  password: string,
): Promise<AuthTokens> {
  return request<AuthTokens>('/auth/login', {
    method: 'POST',
    body: JSON.stringify({ email, password }),
  });
}

export async function signupApi(
  email: string,
  password: string,
  displayName: string,
): Promise<AuthTokens> {
  return request<AuthTokens>('/auth/signup', {
    method: 'POST',
    body: JSON.stringify({ email, password, display_name: displayName }),
  });
}

export async function refreshApi(): Promise<{ access_token: string }> {
  return request<{ access_token: string }>('/auth/refresh', {
    method: 'POST',
  });
}

export async function restoreSession(): Promise<AuthTokens> {
  return request<AuthTokens>('/auth/session');
}

export async function logoutApi(): Promise<void> {
  await request<unknown>('/auth/logout', { method: 'POST' });
}

export async function fetchMe(): Promise<UserProfile> {
  return request<UserProfile>('/auth/me');
}

export async function createApiKey(
  name: string,
  scopes?: string[],
): Promise<ApiKeyCreated> {
  return request<ApiKeyCreated>('/auth/api-keys', {
    method: 'POST',
    body: JSON.stringify({ name, scopes }),
  });
}

export async function listApiKeys(): Promise<ApiKeyInfo[]> {
  return request<ApiKeyInfo[]>('/auth/api-keys');
}

export async function revokeApiKey(keyId: string): Promise<void> {
  await request<unknown>(`/auth/api-keys/${encodeURIComponent(keyId)}`, {
    method: 'DELETE',
  });
}

/* ------------------------------------------------------------------ */
/* Settings                                                            */
/* ------------------------------------------------------------------ */

export interface LLMKeyStatus {
  has_key: boolean;
  key_prefix: string | null;
  stored_at: string | null;
}

export interface TenantSettings {
  llm_enabled: boolean;
  llm_key: LLMKeyStatus;
  databricks_workspace_url: string | null;
  default_cluster_size: string;
  auto_approve: boolean;
  max_concurrent_runs: number;
}

export async function fetchSettings(): Promise<TenantSettings> {
  return request<TenantSettings>('/settings');
}

export async function setLLMKey(apiKey: string): Promise<{ status: string; key_prefix: string }> {
  return request<{ status: string; key_prefix: string }>('/settings/llm-key', {
    method: 'PUT',
    body: JSON.stringify({ api_key: apiKey }),
  });
}

export async function deleteLLMKey(): Promise<{ status: string }> {
  return request<{ status: string }>('/settings/llm-key', {
    method: 'DELETE',
  });
}

export async function testLLMKey(): Promise<{ valid: boolean; model: string | null; error: string | null }> {
  return request<{ valid: boolean; model: string | null; error: string | null }>(
    '/settings/llm-key/test',
    { method: 'POST' },
  );
}

// ---------------------------------------------------------------------------
// Admin analytics
// ---------------------------------------------------------------------------

export async function fetchAnalyticsOverview(days = 30, signal?: AbortSignal) {
  return request<import('./types').AnalyticsOverview>(`/admin/analytics/overview?days=${days}`, { signal });
}

export async function fetchAnalyticsTenants(days = 30, limit = 50, offset = 0, signal?: AbortSignal) {
  return request<import('./types').TenantBreakdown>(
    `/admin/analytics/tenants${qs({ days, limit, offset })}`,
    { signal },
  );
}

export async function fetchAnalyticsRevenue(signal?: AbortSignal) {
  return request<import('./types').RevenueMetrics>('/admin/analytics/revenue', { signal });
}

export async function fetchAnalyticsCostBreakdown(days = 30, group_by = 'model', signal?: AbortSignal) {
  return request<import('./types').CostBreakdown>(
    `/admin/analytics/cost-breakdown${qs({ days, group_by })}`,
    { signal },
  );
}

export async function fetchAnalyticsHealth(days = 30, signal?: AbortSignal) {
  return request<import('./types').HealthMetrics>(`/admin/analytics/health?days=${days}`, { signal });
}

// ---------------------------------------------------------------------------
// Reports
// ---------------------------------------------------------------------------

export async function fetchCostReport(since?: string, until?: string, group_by = 'model', signal?: AbortSignal) {
  return request<import('./types').CostReport>(
    `/admin/reports/cost${qs({ since, until, group_by })}`,
    { signal },
  );
}

export async function fetchUsageReport(since?: string, until?: string, group_by = 'actor', signal?: AbortSignal) {
  return request<import('./types').UsageReport>(
    `/admin/reports/usage${qs({ since, until, group_by })}`,
    { signal },
  );
}

export async function fetchLLMReport(since?: string, until?: string, signal?: AbortSignal) {
  return request<import('./types').LLMReport>(
    `/admin/reports/llm${qs({ since, until })}`,
    { signal },
  );
}

export async function downloadReportExport(
  report_type: string,
  since?: string,
  until?: string,
  format = 'csv',
) {
  const url = `${BASE_URL}/admin/reports/export${qs({ report_type, since, until, format })}`;
  window.open(url, '_blank');
}

// ---------------------------------------------------------------------------
// Customer health
// ---------------------------------------------------------------------------

export async function fetchCustomerHealthList(
  status?: string,
  sort_by = 'health_score',
  limit = 50,
  offset = 0,
  signal?: AbortSignal,
) {
  return request<import('./types').CustomerHealthList>(
    `/admin/health/tenants${qs({ status, sort_by, limit, offset })}`,
    { signal },
  );
}

export async function fetchCustomerHealthDetail(tenantId: string, signal?: AbortSignal) {
  return request<import('./types').CustomerHealth>(`/admin/health/tenants/${tenantId}`, { signal });
}

export async function triggerHealthCompute() {
  return request<{ computed_count: number; duration_ms: number }>('/admin/health/compute', {
    method: 'POST',
  });
}

// ---------------------------------------------------------------------------
// Team Management
// ---------------------------------------------------------------------------

export async function fetchTeamMembers(signal?: AbortSignal): Promise<import('./types').TeamMembersInfo> {
  return request<import('./types').TeamMembersInfo>('/team/members', { signal });
}

export async function inviteTeamMember(
  email: string,
  role: string,
): Promise<import('./types').TeamMember> {
  return request<import('./types').TeamMember>('/team/invite', {
    method: 'POST',
    body: JSON.stringify({ email, role }),
  });
}

export async function removeTeamMember(userId: string): Promise<import('./types').TeamMember> {
  return request<import('./types').TeamMember>(`/team/members/${encodeURIComponent(userId)}`, {
    method: 'DELETE',
  });
}

export async function updateTeamMemberRole(
  userId: string,
  role: string,
): Promise<import('./types').TeamMember> {
  return request<import('./types').TeamMember>(`/team/members/${encodeURIComponent(userId)}`, {
    method: 'PATCH',
    body: JSON.stringify({ role }),
  });
}

// ---------------------------------------------------------------------------
// Quotas
// ---------------------------------------------------------------------------

export async function fetchQuotas(signal?: AbortSignal) {
  return request<import('./types').QuotaInfo>('/billing/quotas', { signal });
}

// ---------------------------------------------------------------------------
// Invoices
// ---------------------------------------------------------------------------

export async function fetchInvoices(limit = 20, offset = 0, signal?: AbortSignal) {
  return request<import('./types').InvoiceList>(
    `/billing/invoices${qs({ limit, offset })}`,
    { signal },
  );
}

export async function fetchInvoice(invoiceId: string, signal?: AbortSignal) {
  return request<import('./types').Invoice>(`/billing/invoices/${invoiceId}`, { signal });
}

export function downloadInvoicePdf(invoiceId: string) {
  window.open(`${BASE_URL}/billing/invoices/${invoiceId}/download`, '_blank');
}

export { IronLayerApiError };

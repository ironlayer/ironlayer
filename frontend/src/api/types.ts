/* ------------------------------------------------------------------ */
/* IronLayer API type definitions                                      */
/* Aligned with core_engine and ai_engine Pydantic models              */
/* ------------------------------------------------------------------ */

export interface DateRange {
  start: string; // ISO date "YYYY-MM-DD"
  end: string;
}

export type RunType = 'FULL_REFRESH' | 'INCREMENTAL';

export type ViolationSeverity = 'BREAKING' | 'WARNING' | 'INFO';

export interface ContractViolation {
  column_name: string;
  violation_type: string;
  severity: ViolationSeverity;
  expected: string;
  actual: string;
  message: string;
}

export interface PlanStep {
  step_id: string;
  model: string;
  run_type: RunType;
  input_range: DateRange | null;
  depends_on: string[];
  parallel_group: number;
  reason: string;
  estimated_compute_seconds: number;
  estimated_cost_usd: number;
  contract_violations: ContractViolation[];
}

export interface PlanSummary {
  total_steps: number;
  estimated_cost_usd: number;
  models_changed: string[];
  contract_violations_count: number;
  breaking_contract_violations: number;
}

export interface Approval {
  user: string;
  action: 'approved' | 'rejected';
  comment: string;
  timestamp: string;
}

export interface Plan {
  plan_id: string;
  base: string;
  target: string;
  summary: PlanSummary;
  steps: PlanStep[];
  approvals: Approval[];
  auto_approved: boolean;
  created_at: string | null;
}

export type ChangeType =
  | 'non_breaking'
  | 'breaking'
  | 'metric_semantic'
  | 'rename_only'
  | 'partition_shift'
  | 'cosmetic';

export interface SemanticClassification {
  change_type: ChangeType;
  confidence: number;
  requires_full_rebuild: boolean;
  impact_scope: string;
}

export interface CostPrediction {
  estimated_runtime_minutes: number;
  estimated_cost_usd: number;
  confidence: number;
}

export interface RiskScore {
  risk_score: number;
  business_critical: boolean;
  approval_required: boolean;
  risk_factors: string[];
}

export interface SQLSuggestion {
  suggestion_type: string;
  description: string;
  rewritten_sql: string | null;
  confidence: number;
}

export interface ModelAdvisory {
  semantic_classification?: SemanticClassification;
  cost_prediction?: CostPrediction;
  risk_score?: RiskScore;
  suggestions?: SQLSuggestion[];
}

export interface PlanWithAdvisory extends Plan {
  advisory: Record<string, ModelAdvisory> | null;
}

export type RunStatus = 'PENDING' | 'RUNNING' | 'SUCCESS' | 'FAIL' | 'CANCELLED';

export interface RunRecord {
  run_id: string;
  plan_id: string;
  step_id: string;
  model_name: string;
  status: RunStatus;
  started_at: string | null;
  finished_at: string | null;
  input_range: DateRange | null;
  error_message: string | null;
  logs_uri: string | null;
  cluster_used: string | null;
  executor_version: string;
  retry_count: number;
}

export interface RunTelemetry {
  run_id: string;
  model_name: string;
  runtime_seconds: number;
  shuffle_bytes: number;
  input_rows: number;
  output_rows: number;
  partition_count: number;
  cluster_id: string | null;
}

export type ModelKind =
  | 'FULL_REFRESH'
  | 'INCREMENTAL_BY_TIME_RANGE'
  | 'APPEND_ONLY'
  | 'MERGE_BY_KEY';

export type Materialization = 'TABLE' | 'VIEW' | 'MERGE' | 'INSERT_OVERWRITE';

export interface ModelInfo {
  model_name: string;
  kind: ModelKind;
  materialization: Materialization;
  owner: string | null;
  tags: string[];
  time_column: string | null;
  unique_key: string | null;
  current_version: string;
  created_at: string;
  last_modified_at: string;
  last_run_status: RunStatus | null;
  watermark_range: DateRange | null;
}

export interface ModelLineage {
  model_name: string;
  upstream: string[];
  downstream: string[];
  nodes: ModelLineageNode[];
  edges: ModelLineageEdge[];
}

export interface ModelLineageNode {
  id: string;
  name: string;
  kind: ModelKind | 'external';
  is_target: boolean;
}

export interface ModelLineageEdge {
  source: string;
  target: string;
}

export interface PlanListItem {
  plan_id: string;
  base_sha: string;
  target_sha: string;
  total_steps: number;
  estimated_cost_usd: number;
  models_changed: string[];
  created_at: string | null;
}

export interface RunFilters {
  plan_id?: string;
  model_name?: string;
  status?: RunStatus;
  limit?: number;
  offset?: number;
}

export interface ModelFilters {
  kind?: ModelKind;
  owner?: string;
  tag?: string;
  search?: string;
}

export interface ApiError {
  detail: string;
  status_code: number;
}

/* ------------------------------------------------------------------ */
/* Usage & Billing types                                               */
/* ------------------------------------------------------------------ */

export interface UsageSummary {
  tenant_id: string;
  period_start: string;
  period_end: string;
  events_by_type: Record<string, number>;
  total_events: number;
}

export interface UsageEvent {
  event_id: string;
  tenant_id: string;
  event_type: string;
  quantity: number;
  metadata: Record<string, unknown>;
  created_at: string;
}

export interface UsageEventsResponse {
  events: UsageEvent[];
  total: number;
  limit: number;
  offset: number;
}

export interface SubscriptionInfo {
  plan_tier: string;
  status: string;
  subscription_id: string | null;
  period_start: string | null;
  period_end: string | null;
  cancel_at_period_end?: boolean;
  current_period_end?: number;
  billing_enabled: boolean;
}

export interface PortalSession {
  url: string;
}

/* ------------------------------------------------------------------ */
/* Schema Drift types                                                  */
/* ------------------------------------------------------------------ */

export interface SchemaDriftDetail {
  column_name: string;
  expected: string;
  actual: string;
  message: string;
}

export interface SchemaDrift {
  id: number;
  model_name: string;
  drift_type: string;
  drift_details: SchemaDriftDetail[];
  resolved: boolean;
  checked_at: string;
}

export interface ReconciliationSchedule {
  id: number;
  schedule_type: string;
  cron_expression: string;
  enabled: boolean;
  last_run_at: string | null;
  next_run_at: string | null;
}

/* ------------------------------------------------------------------ */
/* Environment types                                                   */
/* ------------------------------------------------------------------ */

export interface Environment {
  id: number;
  name: string;
  catalog: string;
  schema_prefix: string;
  is_default: boolean;
  is_production: boolean;
  is_ephemeral: boolean;
  pr_number: number | null;
  branch_name: string | null;
  expires_at: string | null;
  created_by: string;
  deleted_at: string | null;
  created_at: string;
  updated_at: string;
}

export interface EnvironmentPromotion {
  id: number;
  source_environment: string;
  target_environment: string;
  source_snapshot_id: string;
  target_snapshot_id: string;
  promoted_by: string;
  promoted_at: string;
  metadata: Record<string, unknown> | null;
}

/* ------------------------------------------------------------------ */
/* Model Testing types                                                 */
/* ------------------------------------------------------------------ */

export type TestType = 'NOT_NULL' | 'UNIQUE' | 'ROW_COUNT_MIN' | 'ROW_COUNT_MAX' | 'ACCEPTED_VALUES' | 'CUSTOM_SQL';
export type TestSeverity = 'BLOCK' | 'WARN';

export interface TestResult {
  test_id: string;
  plan_id: string | null;
  model_name: string;
  test_type: TestType;
  passed: boolean;
  failure_message: string | null;
  execution_mode: string;
  duration_ms: number;
  executed_at: string;
}

export interface TestSummary {
  total: number;
  passed: number;
  failed: number;
  blocked: number;
  results: TestResult[];
}

/* ------------------------------------------------------------------ */
/* Event Subscription types                                            */
/* ------------------------------------------------------------------ */

export interface EventSubscription {
  id: number;
  tenant_id: string;
  name: string;
  url: string;
  event_types: string[] | null;
  active: boolean;
  description: string | null;
  created_at: string;
  updated_at: string;
}

export interface EventSubscriptionCreate {
  name: string;
  url: string;
  secret?: string;
  event_types?: string[];
  description?: string;
}

/* ------------------------------------------------------------------ */
/* Fragility Score types                                                */
/* ------------------------------------------------------------------ */

export interface FragilityScore {
  model_name: string;
  own_risk: number;
  upstream_risk: number;
  cascade_risk: number;
  fragility_score: number;
  critical_path: boolean;
  risk_factors: string[];
}

/* ------------------------------------------------------------------ */
/* Cost Intelligence types                                             */
/* ------------------------------------------------------------------ */

export interface CostAnomaly {
  model_name: string;
  is_anomaly: boolean;
  anomaly_type: 'spike' | 'drop' | 'none';
  severity: 'none' | 'minor' | 'major' | 'critical';
  z_score: number;
  percentile: number;
  suggested_investigation: string;
}

export interface CostForecast {
  model_name: string;
  projected_7d_total: number;
  projected_30d_total: number;
  trend_direction: 'increasing' | 'decreasing' | 'stable';
  confidence_interval: [number, number];
  smoothing_factor: number;
}

/* ------------------------------------------------------------------ */
/* What-If Impact Simulation types                                     */
/* ------------------------------------------------------------------ */

export interface ColumnChange {
  action: 'ADD' | 'REMOVE' | 'RENAME' | 'TYPE_CHANGE';
  column_name: string;
  new_name?: string;
  old_type?: string;
  new_type?: string;
}

export interface SimulationContractViolation {
  model_name: string;
  column_name: string;
  violation_type: string;
  severity: 'BREAKING' | 'WARNING' | 'INFO';
  message: string;
}

export interface AffectedModel {
  model_name: string;
  reference_type: 'direct' | 'transitive';
  columns_affected: string[];
  contract_violations: SimulationContractViolation[];
  severity: 'BREAKING' | 'WARNING' | 'INFO';
}

export interface ImpactReport {
  source_model: string;
  column_changes: ColumnChange[];
  directly_affected: AffectedModel[];
  transitively_affected: AffectedModel[];
  contract_violations: SimulationContractViolation[];
  breaking_count: number;
  warning_count: number;
  orphaned_models: string[];
  summary: string;
}

// ---------------------------------------------------------------------------
// Admin analytics
// ---------------------------------------------------------------------------

export interface AnalyticsOverview {
  total_tenants: number;
  active_tenants: number;
  total_events: number;
  total_runs: number;
  total_cost_usd: number;
}

export interface TenantAnalytics {
  tenant_id: string;
  plan_tier: string;
  plan_runs: number;
  ai_calls: number;
  api_requests: number;
  run_cost_usd: number;
  llm_cost_usd: number;
  total_cost_usd: number;
  llm_enabled: boolean;
  created_at: string | null;
}

export interface TenantBreakdown {
  tenants: TenantAnalytics[];
  total: number;
}

export interface RevenueMetrics {
  mrr_usd: number;
  tiers: Record<string, { count: number; mrr: number }>;
}

export interface CostItem {
  group: string;
  cost_usd: number;
  run_count: number;
}

export interface CostBreakdown {
  items: CostItem[];
  total_cost_usd: number;
}

export interface HealthMetrics {
  error_rate: number | null;
  p95_runtime_seconds: number | null;
  total_runs: number;
  failed_runs: number;
  ai_acceptance_rate: number | null;
  ai_avg_accuracy: number | null;
}

// ---------------------------------------------------------------------------
// Reports
// ---------------------------------------------------------------------------

export interface ReportItem {
  [key: string]: string | number;
}

export interface CostReport {
  items: ReportItem[];
  total_cost_usd: number;
  period: { since: string; until: string };
  group_by: string;
}

export interface UsageReport {
  items: ReportItem[];
  period: { since: string; until: string };
  group_by: string;
}

export interface LLMReport {
  by_call_type: ReportItem[];
  by_time: ReportItem[];
  total_cost_usd: number;
  period: { since: string; until: string };
}

// ---------------------------------------------------------------------------
// Customer health
// ---------------------------------------------------------------------------

export interface CustomerHealth {
  tenant_id: string;
  health_score: number;
  health_status: 'active' | 'at_risk' | 'churning';
  trend_direction: string | null;
  previous_score: number | null;
  engagement_metrics: Record<string, number> | null;
  last_login_at: string | null;
  last_plan_run_at: string | null;
  last_ai_call_at: string | null;
  computed_at: string | null;
  updated_at: string | null;
}

export interface HealthSummary {
  active: number;
  at_risk: number;
  churning: number;
}

export interface CustomerHealthList {
  tenants: CustomerHealth[];
  total: number;
  summary: HealthSummary;
}

// ---------------------------------------------------------------------------
// Invoices
// ---------------------------------------------------------------------------

export interface InvoiceLineItem {
  description: string;
  quantity: number;
  unit_price: number;
  amount: number;
}

export interface Invoice {
  invoice_id: string;
  invoice_number: string;
  stripe_invoice_id?: string | null;
  period_start: string | null;
  period_end: string | null;
  subtotal_usd: number;
  tax_usd: number;
  total_usd: number;
  line_items?: InvoiceLineItem[];
  status: string;
  created_at: string | null;
}

export interface InvoiceList {
  invoices: Invoice[];
  total: number;
}

// ---------------------------------------------------------------------------
// Billing Plans
// ---------------------------------------------------------------------------

export interface BillingPlanTier {
  tier: string;
  label: string;
  price_label: string;
  features: string[];
  price_id: string | null;
}

export interface BillingPlansResponse {
  plans: BillingPlanTier[];
}

// ---------------------------------------------------------------------------
// Team Management
// ---------------------------------------------------------------------------

export interface TeamMember {
  id: string;
  email: string;
  display_name: string;
  role: string;
  is_active: boolean;
  created_at: string | null;
  last_login_at: string | null;
}

export interface TeamMembersInfo {
  members: TeamMember[];
  total: number;
  seat_limit: number | null;
  seats_used: number;
}

// ---------------------------------------------------------------------------
// Quotas
// ---------------------------------------------------------------------------

export interface SeatInfo {
  used: number;
  limit: number | null;
  percentage: number | null;
}

export interface QuotaItem {
  name: string;
  event_type: string;
  used: number;
  limit: number | null;
  percentage: number | null;
}

export interface LLMBudgetInfo {
  daily_used_usd: number;
  daily_limit_usd: number | null;
  monthly_used_usd: number;
  monthly_limit_usd: number | null;
}

export interface QuotaInfo {
  quotas: QuotaItem[];
  llm_budget: LLMBudgetInfo;
  seats?: SeatInfo;
}

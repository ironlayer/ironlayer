# Architecture

## Dual-Engine Design

IronLayer separates concerns into two independent engines:

### Layer A -- Deterministic Core (`core_engine/`)

The core engine is purely deterministic. Given the same inputs (git refs, model files, watermarks), it always produces byte-for-byte identical plan JSON. This is enforced through:

- **Content-based IDs** -- Plan and step IDs are SHA-256 hashes of their content
- **Sorted keys** -- All JSON output uses sorted keys
- **No timestamps in plans** -- Created-at metadata is stored separately in the state store
- **Versioned canonicalization** -- SQL is normalized through a fixed v1 pipeline (whitespace, case, alias stripping) before hashing

The core engine handles:
- **Model loading** -- Parse `.sql` files with YAML-style comment headers
- **Reference resolution** -- Resolve `{{ ref('model.name') }}` to fully qualified table names
- **SQL parsing** -- SQLGlot-based AST parsing with Databricks dialect support
- **DAG construction** -- NetworkX directed graph from model dependencies
- **Structural diff** -- Compare content hashes between two git commits
- **Interval planning** -- Generate execution steps with date range partitioning
- **Plan serialization** -- Deterministic JSON output with content-based IDs

### Layer B -- AI Advisory (`ai_engine/`)

The AI engine provides non-mutating advisory analysis. It never changes plans -- it annotates them with:

- **Semantic classification** -- Categorize SQL changes (schema evolution, logic change, new model, etc.)
- **Cost prediction** -- Estimate compute cost in USD based on historical telemetry
- **Risk scoring** -- Assess deployment risk based on downstream impact, data volume, and change complexity
- **SQL optimization** -- Suggest query improvements (pushed through a three-gate validation pipeline)

The three-gate validation for AI suggestions:
1. **Syntax gate** -- Parse the suggested SQL through SQLGlot
2. **Explainable diff gate** -- Diff original and suggested SQL, reject if changes are unexplainable
3. **DuckDB test-run gate** -- Execute against a local DuckDB instance to verify correctness

### Separation Boundary

Layer A and Layer B communicate through the API layer. The AI engine is an optional separate FastAPI service (port 8001). Disabling AI (`--no-ai`) has zero impact on plan generation, execution, or state management.

## Multi-Tenant Model

IronLayer is multi-tenant from day 1. Every table has a `tenant_id` column, enforced through:

- **Row-Level Security (RLS)** -- PostgreSQL policies filter rows by `app.tenant_id` session variable
- **Session-level binding** -- `SET LOCAL app.tenant_id = :tid` scopes every transaction
- **Middleware enforcement** -- JWT/OIDC authentication extracts `tenant_id` before any query

In local dev mode (`ironlayer dev`), tenant isolation is skipped (single-tenant, SQLite-backed).

## Data Flow

```
Developer
    |
    v
[Git Repository] ── git diff ──> [Model Loader] ──> [SQL Parser] ──> [DAG Builder]
                                                                          |
                                                                          v
[State Store] <── watermarks ──── [Interval Planner] <── structural diff
    |                                    |
    v                                    v
[Execution Records]              [Plan JSON] ──> [API] ──> [Executor] ──> [Databricks]
                                      |
                                      v (optional)
                                 [AI Engine] ──> [Advisory JSON]
```

1. **Diff** -- Compare SQL content hashes between two git commits
2. **Plan** -- Generate execution steps in topological order with date range partitioning
3. **Approve** -- Manual or auto-approval gate (environment-dependent)
4. **Execute** -- Run SQL against Databricks (production) or DuckDB (local)
5. **Record** -- Persist run results, update watermarks, capture telemetry

## State Store

Production uses PostgreSQL 16 with async SQLAlchemy 2.0:

| Table | Purpose |
|-------|---------|
| `models` | Model registry with current version tracking |
| `model_versions` | Immutable version records with canonical SQL hashes |
| `snapshots` | Point-in-time environment snapshots |
| `watermarks` | Partition watermarks for incremental progress |
| `plans` | Persisted plans with approval tracking (JSONB) |
| `runs` | Step execution records with cost tracking |
| `locks` | Partition-range advisory locks with TTL |
| `telemetry` | Per-run compute metrics |
| `credentials` | Fernet-encrypted tenant secrets |
| `audit_log` | Hash-chained tamper-evident audit trail |
| `token_revocations` | JWT replay protection |
| `tenant_config` | Per-tenant feature flags and LLM budget limits |
| `reconciliation_checks` | Control-plane vs warehouse state reconciliation |
| `ai_feedback` | AI prediction accuracy tracking |
| `llm_usage_log` | Per-call LLM usage for budget enforcement |

Local dev mode uses SQLite via `aiosqlite`. Same ORM table definitions, same code paths -- only the engine URL differs.

## Security Model

### Authentication

Three modes, selected by `API_AUTH_MODE`:
- **`dev`** -- No authentication (local development only)
- **`jwt`** -- HMAC-signed JWT tokens with configurable secret
- **`oidc`** -- OpenID Connect with external identity provider

### Authorization

Role-based access control (RBAC) with three roles:
- **VIEWER** -- Read-only access to plans, runs, and models
- **OPERATOR** -- Can approve and execute plans
- **ADMIN** -- Full access including tenant configuration and audit log

### Data Protection

- **Credential encryption** -- Fernet symmetric encryption for stored secrets
- **PII scrubbing** -- Applied to telemetry before persistence
- **Audit trail** -- SHA-256 hash-chained entries per tenant
- **Token revocation** -- JTI-based replay protection
- **Short-lived tokens** -- No long-lived personal access tokens stored

## Local Development Stack

`ironlayer dev` runs the full stack with zero external dependencies:

| Component | Production | Local Dev |
|-----------|-----------|-----------|
| Metadata store | PostgreSQL 16 | SQLite (aiosqlite) |
| SQL execution | Databricks | DuckDB |
| Authentication | JWT/OIDC | Dev mode (no auth) |
| AI engine | Separate service | Disabled or optional |
| Tenant model | Multi-tenant RLS | Single-tenant no-op |

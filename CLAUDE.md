# IronLayer - Claude Code Project Guide

## Project Overview

IronLayer is an AI-native transformation control plane for Databricks. It sits between SQL models and a Databricks warehouse, generating deterministic execution plans from git diffs and managing incremental state with AI-powered advisory analysis.

## Architecture

### Dual-Engine Design

- **Layer A (Deterministic Core)** — `core_engine/`: Purely deterministic SQL transformation planning. Content-based IDs (SHA-256), sorted JSON keys, no timestamps in plans. Handles model loading, reference resolution, DAG construction, and interval planning.
- **Layer B (AI Advisory)** — `ai_engine/`: Non-mutating advisory intelligence. Semantic classification, cost prediction, risk scoring, SQL optimization with three-gate validation. Never mutates state.

### Monorepo Structure

```
core_engine/   — Deterministic SQL planning engine (Python, SQLGlot, NetworkX)
ai_engine/     — AI advisory service (scikit-learn, Anthropic SDK)
api/           — FastAPI control plane (port 8000)
cli/           — Typer CLI application
frontend/      — React 18 + TypeScript SPA
infra/         — Docker, Helm, Terraform, Grafana, Prometheus
examples/      — Demo projects
docs/          — Architecture, quickstart, CLI ref, API ref
```

### Tech Stack

- Python 3.11+, uv workspace management
- SQLGlot (Databricks dialect), NetworkX (DAG), DuckDB (local), SQLAlchemy 2.0 async
- FastAPI + Uvicorn, React 18 + TypeScript + Tailwind + Vite
- PostgreSQL 16 (prod) / SQLite (dev), Alembic migrations
- Ruff (lint/format), MyPy (strict), pytest (unit/integration/e2e/benchmark)

## Development Commands

```bash
# Install
uv sync --all-extras

# Test
make test                    # All unit tests
make test-integration        # Integration tests
make test-e2e                # End-to-end tests
make test-benchmark          # Performance benchmarks

# Lint & Format
make lint                    # Ruff check + MyPy
make format                  # Ruff format

# Run locally
make docker-up               # Full stack via Docker
ironlayer dev                # Local dev server (SQLite + DuckDB)

# Database
make migrate                 # Run Alembic migrations
```

## Code Conventions

- **Determinism invariant**: All collections sorted deterministically (by name, then type). No randomness in core_engine outputs.
- **Content-based IDs**: Use `compute_deterministic_id()` for generating SHA-256 based identifiers.
- **Pydantic models**: All data structures use Pydantic v2 `BaseModel` with `Field()` descriptions.
- **Async-first**: All database operations and service methods are `async`.
- **Multi-tenant RLS**: Use `SessionDep` (tenant-scoped) for all authenticated endpoints. `PublicSessionDep` only for pre-auth (signup/login/health).
- **RBAC**: Endpoints protected with `require_permission(Permission.XXX)`.
- **Feature gating**: Billing-tier features gated with `require_feature(Feature.XXX)`.
- **SQL safety**: All SQL identifiers validated against `_SAFE_IDENTIFIER_RE` allowlist before interpolation.
- **Line length**: 120 characters (Ruff config).
- **Test file naming**: `test_<module_name>.py` in `tests/unit/`.

## Key Patterns

### Adding a new Core Engine module

1. Create module directory under `core_engine/core_engine/<module>/`
2. Add `__init__.py` with public API exports
3. Follow existing patterns: Pydantic models, deterministic sorting, async methods
4. Add unit tests in `core_engine/tests/unit/test_<module>.py`

### Adding a new API router

1. Create `api/api/routers/<name>.py` with `router = APIRouter(prefix="/<name>", tags=["<name>"])`
2. Add Pydantic request/response models in the router file
3. Create `api/api/services/<name>_service.py` for business logic
4. Register in `api/api/routers/__init__.py`
5. Add RBAC permissions to `api/api/middleware/rbac.py` if needed
6. Add feature gate to `core_engine/core_engine/license/feature_flags.py` if needed

### Adding a new CLI command

1. Create `cli/cli/commands/<name>.py` with Typer command function
2. Register in `cli/cli/app.py` via `app.command()` or `app.add_typer()`
3. Use Rich console for human output to stderr, JSON for machine output
4. Follow existing patterns in `cli/cli/commands/dev.py`

---

# Check Engine Solution

## Overview

The Check Engine is a unified quality and validation framework that consolidates IronLayer's existing check infrastructure (model tests, schema contracts, schema drift, reconciliation) into a single orchestratable engine with extensible check types.

## Existing Infrastructure (Pre-Check Engine)

The following components already exist and will be **integrated into** the Check Engine as built-in check types:

| Component | Location | What it does |
|-----------|----------|-------------|
| **Model Tests** | `core_engine/testing/test_runner.py` | NOT_NULL, UNIQUE, ROW_COUNT, ACCEPTED_VALUES, CUSTOM_SQL assertions |
| **Schema Contracts** | `core_engine/contracts/schema_validator.py` | Column presence, type, nullability validation against declared contracts |
| **Schema Drift** | `core_engine/executor/schema_introspector.py` | Compare expected vs actual warehouse schemas |
| **Reconciliation** | `api/services/reconciliation_service.py` | Control-plane vs warehouse status verification |

## Check Engine Design

### Core Concepts

- **Check**: A single validation rule with a category, severity, and execution logic.
- **CheckType**: Enum categorizing checks — `MODEL_TEST`, `SCHEMA_CONTRACT`, `SCHEMA_DRIFT`, `RECONCILIATION`, `DATA_FRESHNESS`, `CUSTOM`.
- **CheckResult**: Standardized outcome with status (`PASS`, `FAIL`, `WARN`, `ERROR`, `SKIP`), severity, timing, and context.
- **CheckSuite**: An ordered collection of checks to run together against one or more models.
- **CheckEngine**: The orchestrator that discovers, registers, and executes checks through a unified interface.

### Check Result Statuses

- `PASS` — Check assertion satisfied.
- `FAIL` — Check assertion violated (severity determines if blocking).
- `WARN` — Non-blocking violation, logged for awareness.
- `ERROR` — Check could not execute (infrastructure issue).
- `SKIP` — Check not applicable (e.g., no contract defined).

### Check Severities

- `CRITICAL` — Blocks plan apply, requires immediate attention.
- `HIGH` — Blocks plan apply by default, can be overridden.
- `MEDIUM` — Warning, does not block.
- `LOW` — Informational.

## Phased Build Plan

### Phase 1: Core Framework (Current)

**Goal**: Create the unified check engine framework with common models, registry, and orchestrator. Integrate existing check types. Add CLI command and API endpoints.

**Deliverables:**
1. `core_engine/core_engine/checks/` — New module
   - `models.py` — CheckType, CheckStatus, CheckSeverity, CheckResult, CheckSummary enums and models
   - `base.py` — `BaseCheck` abstract class defining the check protocol
   - `registry.py` — `CheckRegistry` for registering and discovering check types
   - `engine.py` — `CheckEngine` orchestrator that runs checks and aggregates results
   - `builtin/` — Built-in check implementations wrapping existing infrastructure
     - `model_tests.py` — Wraps `ModelTestRunner`
     - `schema_contracts.py` — Wraps `validate_schema_contract()`
   - `__init__.py` — Public API exports
2. `cli/cli/commands/check.py` — `ironlayer check` CLI command
3. `api/api/routers/checks.py` — `/checks/` API endpoints
4. `api/api/services/check_service.py` — Check service layer
5. `core_engine/tests/unit/test_check_engine.py` — Unit tests

### Phase 2: Extended Check Types

**Goal**: Add new check types beyond the existing infrastructure.

**Deliverables:**
- `DATA_FRESHNESS` checks — Track last update timestamps, alert on stale data
- `CROSS_MODEL` checks — Validate referential integrity between models
- `VOLUME_ANOMALY` checks — Statistical deviation detection on row counts
- `CUSTOM` checks — User-defined SQL-based checks via model headers

### Phase 3: Observability & Management

**Goal**: Dashboard, alerting, and operational tooling.

**Deliverables:**
- Frontend check dashboard page
- Check result history and trend visualization
- Alerting/notification integration (webhooks)
- Check templates and reusable patterns
- Scheduled background check execution

## Integration Points

- **Plan workflow**: Checks run as a quality gate before `plan apply`
- **CLI**: `ironlayer check` command for local validation
- **API**: `/checks/` endpoints for programmatic access
- **CI/CD**: Check results in GitHub Action PR comments
- **Feature gating**: `Feature.CHECK_ENGINE` for billing tier control
- **RBAC**: `Permission.RUN_CHECKS` and `Permission.READ_CHECK_RESULTS`

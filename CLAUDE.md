# CLAUDE.md — ironlayer_oss

> IronLayer open-source SQL control plane for Databricks (Apache 2.0). Deterministic execution plans from git diffs, with AI-powered cost modeling, risk scoring, and SQL optimization. Framework-agnostic — works with dbt Core, SQLMesh, and raw SQL.

> **Note:** This repo is currently named `ironlayer_oss`. A future rename to `ironlayer` is tracked in I-38.

---

## Package Map

```
ironlayer_oss/
├── core_engine/          # ironlayer-core v0.2.0 — deterministic SQL plan engine, lineage, schema diff
│   └── core_engine/      #   SQLGlot parsing, NetworkX DAG, SQLAlchemy 2.0 async state, DuckDB local
├── ai_engine/            # ai-engine v0.1.0 — cost modeling, risk scoring, SQL optimization
│   └── ai_engine/        #   scikit-learn models, optional Anthropic LLM, DuckDB analytics
├── api/                  # ironlayer-api v0.1.0 — FastAPI control-plane REST API
│   └── api/              #   JWT auth, Stripe billing, Prometheus metrics, Redis caching
├── cli/                  # ironlayer v0.2.0 — Typer CLI (`ironlayer plan`, `ironlayer diff`)
│   └── cli/              #   Rich output, keyring credential storage, optional MCP server
├── check_engine/         # ironlayer-check-engine v0.3.0 — Rust/PyO3 validation (90 rules, 12 categories)
│   └── src/              #   Rayon parallel, regex, TOML config, benchmarks via Criterion
├── frontend/             # React 18 + TypeScript + Tailwind dashboard
│   └── src/              #   Vite build, ReactFlow lineage graph, Recharts, Playwright e2e
├── infra/                # Docker, Terraform, Helm, Prometheus, Grafana
├── tests/                # Cross-package / integration tests
├── examples/             # Demo project, sample models, GitHub Action workflow
├── docs/                 # Architecture, API reference, CLI reference, engineering docs
├── scripts/              # dev_setup.sh, e2e_smoke_test.sh
├── pyproject.toml        # uv workspace root — members: core_engine, ai_engine, api, cli
├── Cargo.toml            # Rust workspace root — member: check_engine
└── docker-compose.yml    # Full local stack: API, AI service, frontend, Postgres, Redis, Prometheus, Grafana
```

**Workspace dependency graph:** `cli` → `core_engine` ← `api` → `ai_engine`. The `check_engine` Rust crate is a PyO3 extension imported by `core_engine`.

---

## Locked Technical Decisions

| # | Decision | Rationale |
|---|----------|-----------|
| 1 | **SQLGlot pinned to 25.34.1** | Last MIT-licensed version before Fivetran acquisition risk. Do NOT upgrade without legal review. |
| 2 | **uv workspace** (not Poetry, not pip) | Single lockfile, fast resolution, workspace-aware `uv run --package`. |
| 3 | **Ruff line-length=120** | Set in root `pyproject.toml`. No per-package overrides. E501 ignored (handled by formatter). |
| 4 | **mypy strict mode** at workspace level | Per-package configs relax `disallow_untyped_defs` during migration; workspace `pyproject.toml` is the target. |
| 5 | **SQLAlchemy 2.0 async** + asyncpg (prod) / aiosqlite (dev) | Async-first persistence. PostgreSQL 16 in production, SQLite for local dev and tests. |
| 6 | **Pydantic v2** everywhere | Settings via `pydantic-settings`. No v1 compat shims. |
| 7 | **Hatchling** build backend | All four Python packages use `hatchling`. No setuptools. |
| 8 | **PyO3 abi3-py311** stable ABI | Single Rust wheel works across Python 3.11+. Rayon for parallel rule execution. |
| 9 | **React 18 + Vite + Tailwind 3** | No Next.js. SPA served by Nginx in Docker. ReactFlow for lineage visualization. |
| 10 | **FastAPI 0.115.x** pinned | Both `api` and `ai_engine` pin `>=0.115,<0.116`. Upgrade together. |
| 11 | **Redis for caching/queues** | docker-compose maps to port 6380 (host) → 6379 (container). |
| 12 | **Prometheus + Grafana** observability | Pushgateway for check_engine metrics, postgres_exporter for DB health, custom API `/metrics`. |
| 13 | **Apache 2.0 license** | Every package has its own `LICENSE` file. OSS repo; no proprietary dependencies. |

---

## Core Rules

1. **Never upgrade SQLGlot** past 25.34.1 without explicit legal + architectural review.
2. **`uv run` for everything** — never bare `python`, `pip`, or `pytest`. Always `uv run --package <pkg>` for package-scoped commands.
3. **Type hints on all function signatures.** Docstrings on all public methods.
4. **`rich.console.Console` for output** — never `print()`. Use `structlog` for structured logging.
5. **No hardcoded secrets.** Read from `os.environ` or config files. Never commit `.env` files.
6. **Conventional commits:** `type(scope): description`. Types: feat, fix, docs, refactor, test, chore, ci, perf.
7. **Ruff is the single linter and formatter.** No flake8, black, or isort. Run `make format` then `make lint`.
8. **Tests must pass before merge.** Coverage gates enforced per package (see Testing section).
9. **Sync with ironlayer_infra** via `make sync-rules` (copies CLAUDE.md and AGENTS.md from infra to OSS). BACKLOG.md and LESSONS.md are private and intentionally NOT synced.
10. **B008 ignored** — FastAPI `Depends()` pattern uses function calls in default arguments. This is intentional.

---

## Local Development (from Makefile)

```bash
# Install all packages + frontend
make install                    # uv sync --all-packages && cd frontend && npm install

# Lint (Ruff + mypy across all 4 packages)
make lint                       # ruff check + mypy per package

# Format (Ruff)
make format                     # ruff format + ruff check --fix

# Run full local stack
make docker-up                  # docker compose up -d (Postgres, Redis, API, AI, frontend, Prometheus, Grafana)
make docker-down                # docker compose down

# Database migrations
make migrate                    # alembic upgrade head (core_engine state DB)
make migrate-create msg="..."   # alembic revision --autogenerate

# Rust check_engine
cd check_engine && cargo build --release --features extension-module
cargo test                      # unit tests
cargo bench                     # Criterion benchmarks

# Frontend
cd frontend && npm run dev      # Vite dev server
cd frontend && npm run build    # tsc + vite build
cd frontend && npm run test     # Vitest
cd frontend && npm run test:e2e # Playwright

# Cleanup caches
make clean                      # removes __pycache__, .pytest_cache, .mypy_cache, .ruff_cache

# Emergency rollback (Azure Container Apps)
make rollback                   # all services
make rollback TARGET=api        # single service

# Sync AI config to OSS repo
make sync-rules                 # copies CLAUDE.md + AGENTS.md from infra → OSS
```

---

## Testing (with coverage gates)

```bash
# All tests
make test                       # runs test-unit + test-integration

# Unit tests with coverage gates
make test-unit
#   core_engine  → --cov-fail-under=70
#   ai_engine    → --cov-fail-under=75
#   api          → --cov-fail-under=75
#   cli          → no minimum (coverage reported)

# Integration tests
make test-integration           # core_engine/tests/integration/

# E2E tests
make test-e2e                   # core_engine/tests/e2e/

# Benchmarks
make test-benchmark             # core_engine/tests/benchmark/ (-m benchmark)

# Slow tests (AI model tests)
make test-slow                  # ai_engine/tests/ (-m slow)

# Frontend tests
cd frontend && npm run test     # Vitest (unit + component)
cd frontend && npm run test:e2e # Playwright (browser e2e)

# Rust check_engine
cd check_engine && cargo test
cd check_engine && cargo bench  # Criterion HTML reports in target/criterion/
```

**Test configuration:** `asyncio_mode = "auto"` across all packages. Pytest paths scoped per package in each `pyproject.toml`.

---

## Environment Variables

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `API_DATABASE_URL` | prod | `sqlite+aiosqlite:///...` | Async DB URL. PostgreSQL in prod, SQLite in dev. |
| `API_AI_ENGINE_URL` | yes | `http://localhost:8001` | AI engine service endpoint. |
| `API_PLATFORM_ENV` | no | `dev` | Environment: `dev`, `staging`, `prod`. |
| `AI_ENGINE_SHARED_SECRET` | prod | `change-me-in-production` | Inter-service auth between API and AI engine. |
| `AI_ENGINE_PORT` | no | `8001` | AI engine listen port. |
| `REDIS_URL` | prod | `redis://redis:6379/0` | Redis connection for caching and queues. |
| `JWT_SECRET` | prod | `dev-change-me-...` | JWT signing secret. Must be strong in prod. |
| `API_CREDENTIAL_ENCRYPTION_KEY` | prod | `dev-change-me-...` | Fernet key for encrypting stored credentials. |
| `API_METRICS_TOKEN` | prod | `dev-metrics-token` | Bearer token for `/metrics` endpoint (Prometheus). |
| `API_ALLOWED_REPO_BASE` | no | `/workspace` | Base path for local repo access from API container. |
| `AUTH_MODE` | no | `development` | Auth mode. `development` disables strict auth. |
| `LLM_ENABLED` | no | `false` | Enable LLM calls in AI engine. |
| `ANTHROPIC_API_KEY` | if LLM | — | Claude API key for AI advisory features. |
| `DATABRICKS_HOST` | runtime | — | Databricks workspace URL. |
| `DATABRICKS_TOKEN` | runtime | — | Databricks personal access token. |
| `DATABRICKS_WAREHOUSE_ID` | runtime | — | SQL Warehouse for query execution. |
| `STRIPE_SECRET_KEY` | prod | — | Stripe billing integration. |
| `GF_ADMIN_PASSWORD` | no | `changeme` | Grafana admin password (docker-compose). |

---

## Playbook Documentation (cross-references)

All operational and development playbooks live under `docs/`:

| Document | Path | Purpose |
|----------|------|---------|
| **Quick Reference** | [`docs/build-notes/quick-reference.md`](docs/build-notes/quick-reference.md) | One-page cheat sheet for common commands, ports, and service URLs. |
| **Dev Journal** | [`docs/dev-journal.md`](docs/dev-journal.md) | Chronological log of design decisions, trade-offs, and lessons learned. |
| **Engineering Patterns** | [`docs/engineering-patterns.md`](docs/engineering-patterns.md) | Reusable patterns: async DB sessions, Pydantic model conventions, error handling, testing strategies. |
| **Backlog Execution** | [`docs/backlog-execution.md`](docs/backlog-execution.md) | Current sprint items, priority ordering, and completion criteria. |
| **Bot Activity Log** | [`docs/build-notes/bot-activity-log.jsonl`](docs/build-notes/bot-activity-log.jsonl) | Machine-readable JSONL log of automated agent actions on this repo. |
| **Plans** | [`docs/build-notes/plans/`](docs/build-notes/plans/) | Detailed implementation plans for major features and migrations. |
| **Architecture** | [`docs/architecture.md`](docs/architecture.md) | System architecture, component interactions, data flow diagrams. |
| **API Reference** | [`docs/api-reference.md`](docs/api-reference.md) | REST API endpoints, request/response schemas, auth flows. |
| **CLI Reference** | [`docs/cli-reference.md`](docs/cli-reference.md) | All `ironlayer` CLI commands, flags, and usage examples. |
| **Production Readiness** | [`docs/production-readiness-checklist.md`](docs/production-readiness-checklist.md) | Pre-deployment checklist for staging and production releases. |
| **Release Verification** | [`docs/release-verification.md`](docs/release-verification.md) | Post-release smoke tests and rollback procedures. |

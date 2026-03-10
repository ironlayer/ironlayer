# AGENTS.md — IronLayer

This file provides AI coding agents (Cursor, GitHub Copilot, Claude Code, etc.) with workspace-level context.

---

## Project Overview

IronLayer is an AI-native SQL transformation control plane for Databricks.

| Component | Path | Role |
|---|---|---|
| **API** | `api/` | FastAPI control plane (port 8000) |
| **AI Engine** | `ai_engine/` | FastAPI advisory service (port 8001) |
| **Core Engine** | `core_engine/` | Execution engine, ORM, state, DAG |
| **CLI** | `cli/` | Typer CLI (`ironlayer`) |
| **Check Engine** | `check_engine/` | Rust/PyO3 validation engine (90+ rules) |
| **Frontend** | `frontend/` | React + Vite (port 3000) |

---

## Build and Test Commands

```bash
# Run tests (from repo root, per package)
uv run --package ironlayer-api pytest api/tests/ -v
uv run --package ai-engine pytest ai_engine/tests/ -v
uv run --package ironlayer-core pytest core_engine/tests/ -v
uv run --package ironlayer pytest cli/tests/ -v

# With coverage
uv run --package ironlayer-api pytest api/tests/ --cov=api --cov-report=term-missing
uv run --package ai-engine pytest ai_engine/tests/ --cov=ai_engine --cov-report=term-missing

# Lint and type-check
uv run ruff check .
uv run ruff check . --fix          # auto-fix safe issues
uv run mypy . --ignore-missing-imports

# Make targets (from repo root)
make test-unit          # all unit tests
make lint               # ruff + mypy
make format             # ruff format + ruff --fix
make migrate            # run Alembic migrations

# CLI commands
ironlayer plan ./project HEAD~1 HEAD
ironlayer diff ./project
ironlayer status
```

---

## Development Workflow

For every non-trivial task, follow:

```
PLAN → REVIEW → IMPLEMENT → VERIFY → INSPECT → ACCEPT
```

1. **Read the relevant existing code** — never assume structure.
2. **Produce a written plan:** steps, files to change, acceptance criteria.
3. **Self-review the plan** — check for gaps, missing tests, scope issues.
4. **Implement** step by step. If the plan turns out wrong, stop and replan.
5. **Verify** — run the verification suite (ruff, mypy, pytest).
6. **Inspect** — self-review: acceptance criteria met? Consistent style?
   Hardcoded values that should be config? Correct module placement?

Skip the loop for trivial tasks: single-line typos, comment rewording,
dependency version bumps with existing test coverage.

---

## Coding Conventions

### Python

- Type hints required, docstrings on public methods
- `rich` for CLI output, `typer` for CLI structure
- Never hardcode credentials — read from `os.environ`
- `uv run` for all commands — never call `python`, `pip`, or `.venv/bin/` directly
- Line length: 120 characters

### Ruff Config

All Python code is linted and formatted with [Ruff](https://docs.astral.sh/ruff/).
Key settings in `pyproject.toml`:

```toml
[tool.ruff]
line-length = 120
target-version = "py311"

[tool.ruff.lint]
select = ["E", "W", "F", "I", "B", "C4", "UP", "SIM", "TCH", "RUF"]
ignore = ["E501", "B008"]
```

- `uv run ruff check .` — lint (fix with `--fix`)
- `uv run ruff format .` — format
- Never use `black`, `isort`, or `autopep8` — Ruff handles all of it

### Terraform

- Every module: `main.tf`, `variables.tf`, `outputs.tf`, `versions.tf`
- `for_each` with named maps — `count` only for boolean toggles
- Tag all resources with `common_tags` (ManagedBy, Product, Environment)
- Security baselines: no `0.0.0.0/0` ingress, KMS rotation enabled,
  S3 versioning + encryption, IAM least-privilege, Unity Catalog grants
  at catalog/schema/table level
- Always run `terraform fmt` before committing
- Never `terraform apply` on production without plan review + CI passing

### SQL

- UPPERCASE keywords, CTE pattern, 4-space indent
- Framework-agnostic — supports dbt Core, dbt Cloud, and SQLMesh

### YAML

- 2-space indentation for all YAML files
- Strings with special characters must be quoted
- Lists use `- item` on new lines (not inline `[a, b, c]` except short arrays)
- Block scalars for multiline: `|` (literal) or `>` (folded)
- Never hardcode credentials in YAML — use `${ENV_VAR}` or `${{ secrets.NAME }}`

### Git Commit Convention

```
type(scope): description

[optional body — explain WHY not WHAT]
[optional footer: Refs #123, Closes #456, BREAKING CHANGE: ...]
```

| Type | When |
|---|---|
| `feat` | New feature or capability |
| `fix` | Bug fix |
| `docs` | Documentation only |
| `refactor` | Code restructuring, no behavior change |
| `test` | Adding or updating tests |
| `chore` | Build, CI, tooling changes |
| `ci` | CI/CD pipeline changes |
| `perf` | Performance improvement |

Scopes: `core`, `api`, `ai`, `cli`, `plan`, `lineage`, `check-engine`, `frontend`, `cicd`

### Branch Naming

```
feature/<description>       # New features
fix/<issue-description>     # Bug fixes
docs/<topic>                # Documentation updates
refactor/<area>             # Code cleanup
ci/<pipeline>               # CI/CD changes
infra/<resource>            # Terraform/infrastructure
```

---

## Testing Conventions

### Test Layout

```
tests/
├── unit/                   # Fast, no I/O, no API calls
│   ├── test_plan_engine.py
│   └── test_llm_router.py
├── integration/            # Real APIs — skip without credentials
│   └── test_tenant_isolation.py
└── conftest.py             # Shared fixtures
```

### Rules

- Write tests alongside code — not after
- Never make real API calls in unit tests — mock external services
- Integration tests guarded by `@pytest.mark.integration` and
  `@pytest.mark.skipif(not os.getenv("..."), reason="...")`

### Coverage Targets

| Package | Threshold | Current |
|---------|-----------|---------|
| API | 75% | 94% |
| AI Engine | 75% | 94% |
| Core Engine | 70% | 86% |
| CLI | 60% | 91% |

### Running Tests

```bash
uv run pytest tests/unit/ -v --tb=short                            # unit (fast)
uv run pytest tests/unit/ --cov=<package> --cov-report=term-missing # with coverage
uv run pytest tests/integration/ -v -m integration                  # integration
uv run pytest tests/unit/test_specific.py -v                        # single file
```

### Markers

```python
@pytest.mark.integration   # Requires credentials + live services
@pytest.mark.slow          # > 10 seconds — skip in pre-commit
```

---

## Toolchain Reference

This repo uses the [Astral](https://astral.sh/) toolchain: **uv** (package/project
manager), **Ruff** (linter + formatter), and **mypy** (type checker).

### uv

- **Always `uv run`** — never `python`, `python3`, or `pip` directly
- **Always `uv sync`** to install deps — never `pip install`
- **Commit `uv.lock`** — lockfile checked in for reproducible installs
- **Never commit `.venv/`** — always gitignored

Common commands:

```bash
uv sync                         # Install all deps from uv.lock
uv sync --no-dev               # Production install only
uv add requests                 # Add a production dependency
uv add --dev pytest             # Add a dev dependency
uv run pytest tests/ -v         # Run in project's virtual environment
uv lock                         # Regenerate uv.lock
```

### Check Engine (Rust)

```bash
cd check_engine
cargo fmt --check               # Format check
cargo clippy -- -D warnings     # Lint (treat warnings as errors)
cargo test                      # Run tests
maturin develop                 # Build PyO3 extension for local dev
```

---

## CI/CD Pipeline

### Workflows

| Workflow | Trigger | What it does |
|----------|---------|-------------|
| `ci.yml` | Push to main, PRs, tags `v*` | Lint → test (4 packages + frontend + check_engine) → security scan → Docker build → canary deploy |
| `publish.yml` | Tags `v*` | Build and publish `ironlayer-core` + `ironlayer` CLI to PyPI (OIDC trusted publisher) |

### CI Jobs

1. **lint** — ruff check + format, mypy (4 Python packages)
2. **test-core / test-ai / test-api / test-cli** — pytest per package with coverage thresholds
3. **test-frontend** — ESLint, TypeScript, vitest, npm audit
4. **planner-determinism** — core invariant gate
5. **test-check-engine** — cargo test + clippy + maturin build
6. **security-scan** — pip-audit, Trivy filesystem, bandit
7. **validate-migrations** — Alembic upgrade → downgrade → upgrade
8. **build-and-push** — Docker images (api, ai, frontend) to Azure Container Registry
9. **trivy-image-scan** — CRITICAL/HIGH CVE scan on built images
10. **deploy** — canary rollout to Azure Container Apps (release tags only)

### PyPI Publishing

Two packages published on `v*` tags:
- `ironlayer-core` (core_engine) — published first
- `ironlayer` (cli) — depends on core, published second

Uses OIDC trusted publisher (no API tokens — GitHub OIDC federation with PyPI).

### Custom GitHub Action

`.github/actions/ironlayer-plan/` — generates execution plans for SQL model
changes on PRs and posts formatted comments with cost/risk analysis.

---

## Architecture Quick Reference

| Concern | Implementation | Notes |
|---------|---------------|-------|
| Auth modes | dev / JWT / KMS / OIDC | Configured via `AUTH_MODE` env var |
| Multi-tenancy | PostgreSQL RLS via `app.tenant_id` | Set in `dependencies.py` |
| Rate limiting | Redis-backed (distributed) | Falls back to in-process when no Redis |
| Token revocation | 3-layer: L1 in-process → L2 Redis → L3 DB | Shared across replicas |
| AI engine role | Advisory only, never mutates | Enforced architecturally |
| Feature gates | `require_feature()` dependency | 3 tiers: community/team/enterprise |
| Credential encryption | Fernet + PBKDF2 (480k rounds) | Always-on security behaviour |
| Event bus | Transactional outbox | At-least-once delivery via `EventOutboxTable` |
| Determinism | Tested via `TestDeterminism` gate | Core invariant — never break |

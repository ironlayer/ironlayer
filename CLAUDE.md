# CLAUDE.md — IronLayer OSS (Public Repo)

> **Work tracking lives in the private repo.**
> Before making any change here, the corresponding backlog item must be
> `[IN-PROGRESS]` in `ironlayer_infra/BACKLOG.md`.

---

## Quick Rules

1. **Check the backlog first** — all work is tracked in `ironlayer_infra/BACKLOG.md`.
   Do not write code until the item is marked `[IN-PROGRESS]` there.
2. **This repo is public (Apache 2.0)** — no internal URLs, no private tokens, no
   infra-specific config, no Terraform backend secrets. Run `sync-to-public.yml`
   checks mentally before committing.
3. **No stubs, no TODOs, no placeholders** — every commit must be production-complete.
4. **Run tests before marking done** (see commands below).
5. **Update `ironlayer_infra/LESSONS.md` and `MEMORY.md`** after completing work
   if there are architectural or process insights.

---

## Build and Test Commands

```bash
# CRITICAL: pytest shebang is broken — always use python -m pytest
VENV="/Users/aronriley/Developer/GitHub Repos/IronLayer/ironlayer_OSS/.venv/bin"

# Run tests (per package)
cd api        && "${VENV}/python" -m pytest tests/ -v -x
cd ai_engine  && "${VENV}/python" -m pytest tests/ -v -x
cd core_engine && "${VENV}/python" -m pytest tests/ -v -x
cd cli        && PYTHONPATH=../core_engine "${VENV}/python" -m pytest tests/ -v -x

# With coverage
"${VENV}/python" -m pytest tests/ --cov=<package_name> --cov-report=term-missing

# Lint
"${VENV}/python" -m ruff check .
"${VENV}/python" -m ruff check . --fix

# Type-check
"${VENV}/python" -m mypy . --ignore-missing-imports

# Makefile targets (from repo root)
make test-unit
make lint
make format
```

---

## Package Layout

```
api/           ironlayer-api   v0.1.0  FastAPI control plane (port 8000)
ai_engine/     ai-engine       v0.1.0  Advisory AI service (port 8001)
core_engine/   ironlayer-core  v0.3.0  Execution engine + ORM + state
cli/           ironlayer       v0.2.0  Typer CLI
check_engine/  Rust/PyO3       —       90+ validation rules
frontend/      React + Vite    —       SPA (port 3000)
```

---

## Architecture Notes (quick ref)

- Auth: dev / JWT / KMS / OIDC — configured via `AUTH_MODE` env var
- RLS: PostgreSQL row-level security via `app.tenant_id` (set in `dependencies.py`)
- AI engine: advisory only — never mutates plans or executes SQL
- Determinism: core invariant — same input must always produce identical plan JSON
- Feature gates: `require_feature()` FastAPI dependency injection
- Rate limiting: in-memory per-replica (not Redis-backed — see backlog)
- Token revocation: 30s TTL in-memory cache (not cross-replica — see backlog)

For complete architecture context, see `ironlayer_infra/CLAUDE.md`.

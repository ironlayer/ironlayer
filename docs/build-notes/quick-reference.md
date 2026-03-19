# Quick Reference — ironlayer_oss

## Project Overview
IronLayer is an AI-native transformation control plane for Databricks. It generates deterministic execution plans from git diffs, manages incremental state, and layers AI advisory analysis (cost predictions, risk scoring, optimization suggestions) on top.

## Locked Technical Decisions
1. **Python 3.11+** with `uv` package management — never use `python` or `pip` directly; always `uv run`.
2. **Dual-engine architecture** — Layer A (core_engine) is purely deterministic; Layer B (ai_engine) is advisory-only. AI never mutates plans.
3. **Type hints on ALL function signatures**; docstrings on all public methods.
4. **`rich.console.Console` for output** — never `print()`.
5. **`@dataclass` for structured return types**; `structlog` for logging.
6. **Ruff** for linting (line-length=120); **mypy** for type checking.
7. **Never hardcode API keys** — read from `os.environ` or `~/.iron/env.local`.
8. **SQLGlot (Databricks dialect)** for SQL parsing and canonicalization.
9. **NetworkX** for DAG operations.
10. **PostgreSQL 16** (production) / **SQLite** (local dev) for metadata; **DuckDB** for local SQL execution.
11. **Git commit format:** `type(scope): description` — types: feat, fix, docs, style, refactor, test, chore, ci, perf.
12. **Budget-protected AI** — all Claude calls through LLM router with `IRON_BUDGET_LIMIT` cap and SHA-256 response cache.
13. **Two-pass AI review** — Pass 1: qwen2.5-coder:32b (vLLM, free); Pass 2: claude-opus-4 (conditional, confidence < 70% or BLOCK).
14. **Apache 2.0 license** (open source).

## Current State
- Monorepo with core_engine, ai_engine, api, cli, frontend, infra, examples, docs.
- CI workflows and pre-commit hooks are configured.
- Uses pyproject.toml + uv.lock for dependency management.

## File Structure Overview
```
ironlayer_oss/
  core_engine/    # Deterministic core (models, loader, parser, graph, planner, executor)
  ai_engine/      # AI advisory service (classifier, cost predictor, risk scorer, optimizer)
  api/            # FastAPI control plane (routers, services, middleware, security, billing)
  cli/            # Typer CLI (login, plan, show, apply, backfill, models, lineage)
  frontend/       # React + TypeScript + Tailwind SPA
  infra/          # Docker, Terraform (Azure), CI/CD pipeline
  examples/       # Demo project and example models
  docs/           # Architecture, quickstart, CLI reference, API reference, deployment
  .github/        # CI workflows, actions, PR template
  .claude/        # Claude skills
```

## Key Patterns / Conventions
- All tests: `uv run pytest tests/ -v`
- Lint: `uv run ruff check .`
- Type check: `uv run mypy . --ignore-missing-imports`
- Pre-commit: `pre-commit run --all-files`
- Agent base class: `ironrecall_core.agents.base.BaseAgent`
- LLM routing: `ironrecall_core.llm.ModelTier`
- CLI commands: `ironlayer plan`, `ironlayer diff`, `ironlayer status`

## Environment Variables
```bash
ANTHROPIC_API_KEY       # Claude API key
DATABRICKS_HOST         # Databricks workspace URL
DATABRICKS_TOKEN        # Databricks personal access token
DATABRICKS_WAREHOUSE_ID # SQL Warehouse ID
GITHUB_TOKEN            # GitHub PAT
GITHUB_APP_ID           # GitHub App ID (Iron Review Engine)
GITHUB_APP_PRIVATE_KEY  # GitHub App private key
GITHUB_WEBHOOK_SECRET   # GitHub webhook secret
STRIPE_SECRET_KEY       # Stripe billing key
IRON_BUDGET_LIMIT       # AI spend cap (default 15.00)
IRON_USE_LOCAL_LLMS     # Use local vLLM (true/false)
VLLM_BASE_URL           # Local vLLM endpoint
VLLM_BASE_URL_REMOTE    # Remote vLLM endpoint (Mac Studio via Tailscale)
WORKSPACE_ROOT          # Auto-set by activate.sh
IRONRECALL_CORE_PATH    # Auto-set by activate.sh
```

# AGENTS.md — IronLayer

This file provides AI coding agents (Cursor, GitHub Copilot, Claude Code, etc.) with IronLayer-specific context.

---

## Project Overview

IronLayer is an **AI-native SQL transformation control plane** for Databricks — the `terraform plan` / `terraform apply` for your dbt models.

| Component | Role |
|-----------|------|
| **core_engine/** | Deterministic plan engine, DAG, diff, executor |
| **ai_engine/** | AI advisory (cost, risk, suggestions) |
| **cli/** | Typer CLI + MCP server |

---

## Build and Test Commands

```bash
# Run tests
uv run pytest tests/ -v

# Lint Python
uv run ruff check .
uv run mypy core_engine/ cli/ ai_engine/ --ignore-missing-imports

# Pre-commit (all checks)
pre-commit run --all-files

# IronLayer CLI
ironlayer plan ./project HEAD~1 HEAD
ironlayer diff ./project HEAD~1 HEAD --model orders
ironlayer lineage ./project --model staging.orders
ironlayer validate ./project
```

---

## Architecture Decisions

1. **Deterministic core** — Same input → same output; no LLM in execution path
2. **AI advisory only** — AI annotates plans; never changes them
3. **Content-based IDs** — SHA-256 of plan content for reproducibility
4. **Framework-agnostic** — Supports dbt Core, dbt Cloud, and SQLMesh

---

## Coding Conventions

### Python
- Type hints required, docstrings on public methods
- `rich` for CLI output, `typer` for CLI structure
- `structlog` for structured logging
- Never hardcode credentials — read from `os.environ`
- `uv run` for all commands

### Git (Conventional Commits)
```
type(scope): description

Types: feat, fix, docs, style, refactor, test, chore, ci, perf
Scopes: plan, lineage, cost, mcp, cli, core_engine, ai_engine
```

---

## PR Process

1. Title follows conventional commit format
2. Description includes: Summary, Test Plan, Checklist
3. All tests must pass
4. Plans must be deterministic — add tests for new planner logic

# AGENTS.md

## Cursor Cloud specific instructions

### Project overview

IronLayer is a Python/TypeScript monorepo with 4 Python workspace packages (`core_engine`, `ai_engine`, `api`, `cli`) and a React frontend (`frontend/`). Managed by **uv workspaces** for Python and **npm** for the frontend. See `README.md` for full architecture.

### Running services

- **CLI (local dev mode):** `uv run ironlayer dev --no-ai --no-ui` in a project directory scaffolded with `ironlayer init --non-interactive`. Uses SQLite + DuckDB, no Postgres/Docker needed.
- **API standalone:** `uv run uvicorn api.main:app --host 127.0.0.1 --port 8000` — requires env vars for local mode (see `cli/cli/commands/dev.py` `_setup_local_env` for the full list). Key ones: `PLATFORM_STATE_STORE_TYPE=local`, `PLATFORM_DATABASE_URL=sqlite+aiosqlite:///...`, `API_AUTH_MODE=dev`, `PLATFORM_ENV=dev`.
- **Frontend dev:** `npx vite --host 0.0.0.0 --port 3000` from `frontend/`. Set `VITE_API_URL=http://localhost:8000`.
- **PostgreSQL (for full-stack):** `docker run -d --name ironlayer-postgres -e POSTGRES_DB=ironlayer -e POSTGRES_USER=ironlayer -e POSTGRES_PASSWORD=ironlayer_dev -p 5432:5432 postgres:16-alpine`. Or use `docker compose up -d postgres` from repo root.

### Lint / Test / Build commands

All documented in `Makefile`:
- `make lint` — ruff check + mypy across all 4 Python packages
- `make test` — unit + integration tests (equivalent to `make test-unit && make test-integration`)
- `make test-unit` — unit tests per package with coverage
- Frontend lint: `npm run lint` from `frontend/`
- Frontend test: `npx vitest run` from `frontend/`
- Frontend build: `npm run build` from `frontend/`

### Gotchas

- The API's `/ready` endpoint returns `"degraded"` when AI engine is not running — this is expected in local dev with `--no-ai`.
- Pre-existing lint warnings (798 ruff errors, mypy type errors) exist in the repo. Do not attempt to fix these unless explicitly asked.
- Pre-existing test failures: 1 in `core_engine` (`test_removes_databricks_tokens`), 1 in `ai_engine` (`test_token_detected`), 4 in `cli` (`test_display.py`). These are known and not caused by environment setup.
- Docker in this cloud VM requires `fuse-overlayfs` storage driver and `iptables-legacy`. These are configured during initial setup.
- `uv run --project /workspace ironlayer <cmd>` can be used from any directory to invoke the CLI without activating the virtualenv.

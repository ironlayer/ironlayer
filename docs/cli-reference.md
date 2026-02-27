# CLI Reference

The IronLayer CLI is invoked as `ironlayer`. All commands support `--help` for detailed usage.

## Global Options

These options apply to every command:

| Option | Default | Description |
|--------|---------|-------------|
| `--json / --no-json` | `--no-json` | Emit structured JSON to stdout instead of human-readable output |
| `--metrics-file PATH` | None | Write metrics events to this file (JSONL format) |
| `--env TEXT` | `dev` | Environment override (dev, staging, prod). Also set via `PLATFORM_ENV` |

## Commands

### `ironlayer init`

Scaffold a new IronLayer project in the current (or specified) directory.

```bash
ironlayer init [OPTIONS] [DIRECTORY]
```

| Option | Default | Description |
|--------|---------|-------------|
| `--name TEXT` | Directory name | Project name |
| `--non-interactive` | False | Skip all prompts, use defaults |
| `--state-store TEXT` | `local` | State store type: `local` or `postgres` |
| `--databricks-host TEXT` | None | Databricks workspace URL (optional) |
| `--no-ai` | False | Disable AI advisory engine |
| `--no-git` | False | Skip git repository initialization |

**Generated files:**
- `.ironlayer/config.yaml` -- Project configuration
- `.env` -- Environment variables
- `.gitignore` -- Ignore patterns for IronLayer artifacts
- `models/` -- Example SQL models (4 files across raw/staging/analytics)

**Exit codes:**
- `0` -- Success
- `3` -- Error (invalid options, file system errors)

---

### `ironlayer dev`

Start a local development server with zero external dependencies.

```bash
ironlayer dev [OPTIONS]
```

| Option | Default | Description |
|--------|---------|-------------|
| `--port, -p INT` | `8000` | API server port |
| `--ai-port INT` | `8001` | AI engine port (if AI is enabled) |
| `--no-ai` | False | Disable the AI advisory engine |
| `--no-ui` | False | Skip starting the frontend dev server |
| `--host TEXT` | `127.0.0.1` | Host to bind the API server to |
| `--reload` | False | Enable auto-reload on code changes |

**What it starts:**
- FastAPI API server (SQLite-backed, dev auth mode)
- DuckDB for local SQL execution
- Rate limiting disabled
- OpenAPI docs at `http://{host}:{port}/docs`
- Readiness probe at `http://{host}:{port}/ready`

**Environment variables set:**
- `PLATFORM_DATABASE_URL` -- SQLite connection string
- `PLATFORM_STATE_STORE_TYPE` -- `local`
- `PLATFORM_ENV` -- `dev`
- `API_AUTH_MODE` -- `dev`
- `API_RATE_LIMIT_ENABLED` -- `false`

**Exit codes:**
- `0` -- Clean shutdown
- `3` -- No IronLayer project found, or server error

---

### `ironlayer plan`

Generate a deterministic execution plan from a git diff.

```bash
ironlayer plan REPO BASE TARGET [OPTIONS]
```

| Argument | Description |
|----------|-------------|
| `REPO` | Path to the git repository containing SQL models |
| `BASE` | Base git ref (commit SHA or branch) -- current state |
| `TARGET` | Target git ref (commit SHA or branch) -- desired state |

| Option | Default | Description |
|--------|---------|-------------|
| `--out, -o PATH` | `plan.json` | Output path for the generated plan JSON |
| `--as-of-date TEXT` | Today | Reference date for date arithmetic (YYYY-MM-DD) |

**How it works:**
1. Validates the git repository
2. Loads models from the `models/` subdirectory (or repo root)
3. Builds a dependency DAG
4. Diffs content hashes between BASE and TARGET commits
5. Computes a structural diff (added, modified, removed models)
6. Generates execution steps in topological order
7. Writes deterministic plan JSON to the output path

**Exit codes:**
- `0` -- Plan generated (or no changes detected)
- `3` -- Error (invalid git repo, parse errors)

---

### `ironlayer show`

Display a human-readable summary of a plan.

```bash
ironlayer show PLAN_PATH
```

| Argument | Description |
|----------|-------------|
| `PLAN_PATH` | Path to the plan JSON file |

With `--json`, outputs the raw plan JSON to stdout.

---

### `ironlayer apply`

Execute a previously generated plan.

```bash
ironlayer apply PLAN_PATH --repo REPO [OPTIONS]
```

| Option | Default | Description |
|--------|---------|-------------|
| `--repo PATH` | (required) | Path to the git repository containing SQL model definitions |
| `--approve-by TEXT` | None | Name of the approver (required in non-dev environments) |
| `--auto-approve` | False | Skip manual approval (only allowed in dev) |
| `--override-cluster TEXT` | None | Override the cluster/warehouse for execution |

**Approval gate:**
- In `dev` environment: auto-approve is permitted
- In `staging` / `prod`: requires `--approve-by` or explicit approval

**Exit codes:**
- `0` -- All steps succeeded
- `3` -- One or more steps failed (remaining steps are cancelled)

---

### `ironlayer backfill`

Run a targeted backfill for a single model over a date range.

```bash
ironlayer backfill --model MODEL --start YYYY-MM-DD --end YYYY-MM-DD --repo REPO [OPTIONS]
```

| Option | Description |
|--------|-------------|
| `--model, -m TEXT` | Canonical model name to backfill (required) |
| `--start TEXT` | Start date, inclusive (required) |
| `--end TEXT` | End date, inclusive (required) |
| `--repo PATH` | Path to the git repository (required) |
| `--cluster TEXT` | Override cluster/warehouse |

---

### `ironlayer models`

List all models discovered in a repository.

```bash
ironlayer models REPO
```

| Argument | Description |
|----------|-------------|
| `REPO` | Path to the repository containing SQL models |

Displays a table with: name, kind, materialization, time column, owner, and tags.

---

### `ironlayer lineage`

Display upstream and downstream lineage for a model.

```bash
ironlayer lineage REPO --model MODEL [--column COL] [--depth N]
```

| Option | Description |
|--------|-------------|
| `--model, -m TEXT` | Canonical model name to trace lineage for (required) |
| `--column, -c TEXT` | Column name for column-level lineage tracing (optional) |
| `--depth INT` | Maximum traversal depth for cross-model tracing (default: 50) |

Without `--column`, outputs a tree showing all upstream and downstream models.
With `--column`, traces a specific column back through the DAG to its source tables and columns.

---

### `ironlayer migrate from-dbt`

Import models from a dbt project into IronLayer format.

```bash
ironlayer migrate from-dbt PROJECT_PATH [OPTIONS]
```

| Option | Default | Description |
|--------|---------|-------------|
| `--output, -o PATH` | `./models` | Output directory for generated model files |
| `--tag TEXT` | None | Only migrate models with this tag |
| `--dry-run` | False | Show what would be migrated without writing files |

**Prerequisites:** Run `dbt compile` or `dbt build` first to generate `manifest.json`.

---

### `ironlayer migrate from-sql`

Import raw SQL files into IronLayer format with inferred dependencies.

```bash
ironlayer migrate from-sql SQL_DIR [OPTIONS]
```

| Option | Default | Description |
|--------|---------|-------------|
| `--output, -o PATH` | `./models` | Output directory |
| `--materialization TEXT` | `TABLE` | Default materialization (TABLE, VIEW, INSERT_OVERWRITE, MERGE) |
| `--dry-run` | False | Preview mode |

Dependencies are inferred from FROM/JOIN clauses in the SQL.

---

### `ironlayer migrate from-sqlmesh`

Import a SQLMesh project into IronLayer format.

```bash
ironlayer migrate from-sqlmesh PROJECT_PATH [OPTIONS]
```

| Option | Default | Description |
|--------|---------|-------------|
| `--output, -o PATH` | `./models` | Output directory |
| `--tag TEXT` | None | Only migrate models with this tag |
| `--dry-run` | False | Preview mode |

Supports both SQL MODEL headers and Python `@model` decorators.

---

## Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `PLATFORM_ENV` | `dev` | Environment (dev, staging, prod) |
| `PLATFORM_STATE_STORE_TYPE` | `postgres` | State store backend (local or postgres) |
| `PLATFORM_DATABASE_URL` | PostgreSQL URL | Database connection string |
| `PLATFORM_LOCAL_DB_PATH` | `.ironlayer/local.duckdb` | DuckDB path for local execution |
| `PLATFORM_METRICS_FILE` | None | Path for metrics JSONL output |
| `API_HOST` | `0.0.0.0` | API server bind host |
| `API_PORT` | `8000` | API server port |
| `API_AUTH_MODE` | `jwt` | Authentication mode (dev, jwt, oidc) |
| `API_JWT_SECRET` | None | JWT signing secret |
| `API_CORS_ORIGINS` | `["http://localhost:3000"]` | CORS allowed origins |
| `API_RATE_LIMIT_ENABLED` | `true` | Enable/disable rate limiting |
| `AI_ENGINE_URL` | `http://localhost:8001` | AI engine base URL |
| `AI_LLM_ENABLED` | `true` | Enable/disable LLM integration |
| `IRONLAYER_API_URL` | None | CLI: API base URL (stored from `login`) |
| `IRONLAYER_API_TOKEN` | None | CLI: Auth token (overrides stored credentials) |

## Exit Codes

| Code | Meaning |
|------|---------|
| `0` | Success |
| `3` | Error (invalid input, execution failure, missing configuration) |

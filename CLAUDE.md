# CLAUDE.md — TheAiGroup / IronLayer Platform

> **Single source of truth for AI agents working across TheAiGroup / IronLayer workspace.**
> Covers workspace-level context. Each product repo has its own CLAUDE.md for repo-specific context.
> Last updated: March 2026

---

## What Is TheAiGroup?

TheAiGroup is an **AI-native data platform company** building three products that together eliminate the fragmented, manual work of modern data engineering:

| Product | Tag | What It Does |
|---|---|---|
| **IronLayer** | SHIP | SQL control plane — runs BEFORE dbt or SQLMesh. Deterministic plans, cost modeling, column-level lineage, schema guardrails. Framework-agnostic. |
| **Iron Foundation** | BUILD | Turnkey production data stack — Terraform + dbt/SQLMesh + extractors deployed to client Databricks in < 1 week. |
| **IronPilot** | RUN | Agent fleet — GitHub App (AI PR review), automated pipeline monitoring, self-healing agents. |

**One-line pitch:** *"AI that gets smarter about YOUR data stack with every PR it reviews."*

---

## Repository Map

```
# Repos live as siblings in a shared parent directory.
# activate.sh sets WORKSPACE_ROOT; paths resolve relative to it.
#
├── iron-dev-workspace/             # Workspace orchestrator — AI configs, standards, tooling
├── ironrecall-core/                # Shared kernel (auth, llm, security, db, memory, mcp)
├── ironlayer/                      # IronLayer — SHIP (public, Apache 2.0)
├── ironlayer-infra/                # Iron Foundation — BUILD (private)
├── ironpilot/                      # IronPilot — RUN (private)
├── iron-client-template/           # Per-client config template
├── iron-terraform/                 # GitHub org Terraform management
├── ironmigrate/                    # Redshift→Databricks migration CLI
├── ironexchange/                   # Rust CLI utility (dx diff, validate, query)
│
├── dpb-data-platform-in-a-box/     # [REFERENCE] Legacy monolith — agent code reference
└── AEGIS-DWH-IN-A-BOX-V2/         # [REFERENCE] Prototype
```

---

## Architecture Principles

### 1. Hybrid: Shared Kernel + Product Repos
`ironrecall-core` is the shared Python package. Product repos depend on it; they don't duplicate shared logic.
- Auth, LLM routing, security, DB, memory → `ironrecall-core`
- Plan engine, lineage, cost, framework detection → `ironlayer`
- Terraform, dbt/SQLMesh, extractors → `ironlayer-infra`
- Agent fleet, GitHub App, billing → `ironpilot`

### 2. Databricks-Native CI/CD
All CI/CD runs on Databricks job compute (cheapest). SQL Warehouses are user-facing only.

### 3. Two-Pass AI Review
- Pass 1: `qwen2.5-coder:32b` (vLLM, Mac Studio) — fast, $0
- Pass 2: `claude-opus-4` — conditional, only when confidence < 70% or BLOCK detected

### 4. Client-Agnostic Core
Platform IP in the Docker image. Client-specific knowledge in `iron-client-template`.

### 5. Budget-Protected AI
All Claude calls through `ironrecall-core` LLM router with `IRON_BUDGET_LIMIT` cap and SHA-256 response cache.

### 6. Everything Terraform
All GitHub repos, branch protection, environments, and secrets managed by `iron-terraform`.

---

## Build and Test Commands

```bash
# Activate workspace (always use this)
source activate.sh

# Any repo — Python
uv run pytest tests/ -v
uv run ruff check .
uv run mypy . --ignore-missing-imports

# ironlayer-infra — SQL + Terraform
sqlfluff lint dbt-framework/models/ --dialect databricks
terraform fmt -check -recursive terraform/
dbt compile --target dev            # dbt Core projects
sqlmesh plan --dry-run              # SQLMesh projects

# ironexchange — Rust
cargo fmt --check && cargo clippy && cargo test

# Pre-commit (all repos)
pre-commit run --all-files

# IronLayer CLI
ironlayer plan                   # Validate execution plan
ironlayer diff                   # Schema/data diff
ironlayer status                 # System health

# IronPilot CLI
ironpilot review code <path>     # AI code review (local first)
ironpilot agent run --item <ID>  # Run backlog item
ironpilot ai-usage               # Track AI spend
```

---

## Claude Skills (available in this workspace)

```bash
cat ai/claude/skills/{skill-name}/SKILL.md
```

| Skill | When to Use |
|---|---|
| `iron-pr-review` | Reviewing PRs with BLOCK/WARN/NOTE output (dbt + SQLMesh aware) |
| `iron-dbt-model` | Creating dbt Core staging/intermediate/mart models |
| `iron-sqlmesh` | Creating SQLMesh models, converting dbt→SQLMesh, plan/apply workflows |
| `iron-extractor` | Adding new data source extractors |
| `iron-kimball-design` | Designing star schemas (dbt + SQLMesh model kinds) |
| `iron-terraform` | Creating Terraform modules (Databricks, AWS, GitHub) |
| `iron-pipeline-design` | Designing end-to-end data pipelines (dbt or SQLMesh) |
| `iron-data-quality` | Adding dbt tests and SQLMesh audits / data quality rules |
| `iron-dbt-cloud` | Managing dbt Cloud Enterprise projects, jobs, and environments |
| `iron-dev-loop` | PRIVIA development loop for non-trivial tasks |

---

## Agent Conventions

```python
from ironrecall_core.agents.base import BaseAgent, AgentResult
from ironrecall_core.llm import ModelTier

class MyAgent(BaseAgent):
    AGENT_NAME = "MyAgent"
    AGENT_DESCRIPTION = "What this agent does."
    DEFAULT_TIER = ModelTier.STANDARD
    MAX_TOKENS = 4096
    PREFER_LOCAL = True  # Try vLLM first

    def _get_agent_specific_instructions(self) -> str:
        return "Detailed instructions for the agent's role."

    def analyze(self, input_data: str) -> AgentResult:
        response = self._call_claude(f"Analyze: {input_data}")
        self._track_usage()
        return AgentResult(success=True, summary=response)
```

---

## Coding Standards

### Python
- Type hints on ALL function signatures
- Docstrings on all public methods
- `rich.console.Console` for output — never `print()`
- `@dataclass` for structured return types
- `structlog` for structured logging
- Never hardcode API keys — read from `os.environ` or `~/.iron/env.local`
- `uv run` for all Python commands (never `python` or `pip`)
- Ruff: line-length=120, mypy for type checking

### SQL (dbt + SQLMesh)
- UPPERCASE keywords
- **dbt Core:** CTE pattern with `{{ config() }}`, `{{ ref() }}`, `{{ source() }}`; every model needs YAML schema file
- **SQLMesh:** `MODEL()` DDL block before the query; grain + audits required on incremental models; `@start_ds`/`@end_ds` for time-range incremental
- `{{ surrogate_key([...]) }}` (dbt) / `@safe_divide(...)` macro (SQLMesh) — never raw MD5 or division
- For SQLMesh projects use `sqlmesh.mdc` rule and `iron-sqlmesh` skill

### Terraform
- `for_each` with named maps — NEVER `count` for multi-resource
- Tag all AWS resources with `common_tags`
- Module structure: `main.tf`, `variables.tf`, `outputs.tf`, `versions.tf`
- S3 backend + DynamoDB locking

### Git
```
type(scope): description

Types: feat, fix, docs, style, refactor, test, chore, ci, perf
Scopes: core, llm, auth, security, plan, lineage, terraform, dbt, sqlmesh, agents, github-app, cicd, ai, standards, tooling, workspace, config, bundle, monitoring, memory, ironlayer, extractors, cli, docs
```

---

## Workflow & Backlog

All agents follow [standards/WORKFLOW_RULES.md](../../standards/WORKFLOW_RULES.md) (six rules: backlog-first, verify dependencies, no stubs, verification suite, update memory/lessons, conventional commits).

- **Canonical backlog:** [development_docs/UNIFIED_BACKLOG.md](../../development_docs/UNIFIED_BACKLOG.md)
- **Legacy code promotion:** [standards/LEGACY_CODE_PROMOTION.md](../../standards/LEGACY_CODE_PROMOTION.md)
- **Development loop:** PRIVIA (Plan → Review → Implement → Verify → Inspect → Accept) for non-trivial tasks. See `iron-dev-loop` skill.

Each repo may have a `CLAUDE_REPO.md` for repo-specific context that supplements this workspace-level CLAUDE.md. The sync mechanism (`make sync-ai`) only touches `CLAUDE.md` — repo-specific files are preserved.

---

## Key Documents

| Document | Purpose |
|----------|---------|
| [README.md](../../README.md) | Workspace overview, products, quick start |
| [docs/COFOUNDER_SETUP_GUIDE.md](../../docs/COFOUNDER_SETUP_GUIDE.md) | First-time setup and onboarding |
| [docs/REPO_INDEX.md](../../docs/REPO_INDEX.md) | Full repo index with roles and status |
| [docs/ARCHITECTURE.md](../../docs/ARCHITECTURE.md) | System architecture overview |
| [docs/ENVIRONMENT_GUIDE.md](../../docs/ENVIRONMENT_GUIDE.md) | Dev/staging/prod connection details |
| [docs/VERSIONING.md](../../docs/VERSIONING.md) | Version management strategy |
| [development_docs/UNIFIED_BACKLOG.md](../../development_docs/UNIFIED_BACKLOG.md) | Master backlog (all initiatives) |
| [development_docs/FEATURE_REPO_MAPPING.md](../../development_docs/FEATURE_REPO_MAPPING.md) | Feature-to-repo mapping |
| [standards/README.md](../../standards/README.md) | Coding standards index |
| [tooling/env/README.md](../../tooling/env/README.md) | Environment configuration guide |
| [docs/adr/](../../docs/adr/) | Architecture Decision Records |

---

## Environment Variables

```bash
# Core — ~/.iron/env.local
ANTHROPIC_API_KEY=sk-ant-xxx
DATABRICKS_HOST=https://xxx.azuredatabricks.net
DATABRICKS_TOKEN=dapiXXX
DATABRICKS_WAREHOUSE_ID=xxx
GITHUB_TOKEN=ghp_xxx

# GitHub App (Iron Review Engine)
GITHUB_APP_ID=xxx
GITHUB_APP_PRIVATE_KEY="-----BEGIN RSA PRIVATE KEY-----..."
GITHUB_WEBHOOK_SECRET=xxx

# Billing
STRIPE_SECRET_KEY=sk_xxx

# Iron config
IRON_BUDGET_LIMIT=15.00
IRON_USE_LOCAL_LLMS=true
VLLM_BASE_URL=http://localhost:8000
VLLM_BASE_URL_REMOTE=http://100.x.x.x:8000  # Mac Studio via Tailscale
WORKSPACE_ROOT=<auto-set by activate.sh>
IRONRECALL_CORE_PATH=<auto-set by activate.sh>
```

---

## What NOT to Build Right Now

- NL-to-SQL Studio — nice demo, not needed for first clients
- React Canvas — Streamlit is sufficient
- Meltano expansion — clients have their own extractors
- Prometheus/Grafana — GitHub Actions logs are sufficient
- SaaS API — build at 5+ clients
- Jira integration — enterprise feature

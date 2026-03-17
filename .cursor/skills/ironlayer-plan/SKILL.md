---
name: ironlayer-plan
description: >
  Generate an IronLayer execution plan from a git diff and interpret the results.
  Use when you want to understand what will change, estimate cost, or identify risk
  before running dbt models in production.
triggers:
  - "ironlayer plan"
  - "what will change when I run dbt"
  - "generate a plan"
  - "cost estimate for this dbt change"
  - "risk analysis for this PR"
outputs:
  - Execution plan JSON
  - Risk and cost summary
  - Action recommendation (safe to apply / review first / block)
---

# IronLayer Plan — Cursor Skill

> Run this skill before applying any dbt changes to production.
> IronLayer gives you terraform-plan-style confidence for your data warehouse.

---

## Step 1 — Generate the Plan via MCP

Use the `ironlayer_plan` MCP tool directly in Cursor:

```
Call MCP tool: ironlayer_plan
Arguments:
  project_path: /path/to/your/dbt/project
  from_ref: HEAD~1
  to_ref: HEAD
```

Or via CLI:

```bash
cd ironlayer
uv run ironlayer plan ./path/to/project HEAD~1 HEAD --output plan.json
```

---

## Step 2 — Interpret the Plan Output

The plan returns:

```json
{
  "plan_id": "sha256:abc...",
  "steps": [
    {
      "model": "stg_coinbase__candles",
      "action": "FULL_REFRESH",
      "reason": "model content hash changed",
      "estimated_rows": 125000,
      "estimated_cost_usd": 0.12,
      "risk": "LOW"
    },
    {
      "model": "fct_daily_revenue",
      "action": "INCREMENTAL",
      "reason": "upstream dependency changed",
      "estimated_rows": 3200,
      "estimated_cost_usd": 0.04,
      "risk": "MEDIUM",
      "downstream_impact": ["dim_customer_ltv", "dashboard_revenue"]
    }
  ],
  "total_cost_usd": 0.16,
  "total_risk": "MEDIUM"
}
```

---

## Step 3 — Risk Classification

| Risk Level | Criteria | Your Action |
|-----------|----------|-------------|
| **LOW** | Staging view refresh, cosmetic column rename | ✅ Safe to apply directly |
| **MEDIUM** | Intermediate or mart change, < 10% row delta | ⚠️ Review downstream impact first |
| **HIGH** | Full refresh on large table, PK change, 10%+ row delta | 🔴 Human review required |
| **CRITICAL** | Schema breaking change, DROP implied | 🛑 Block deployment, open discussion |

---

## Step 4 — Downstream Impact Check

If `downstream_impact` is non-empty in the plan:

```bash
# Via MCP
Call MCP tool: ironlayer_lineage
Arguments:
  project_path: /path/to/project
  model: fct_daily_revenue

# Or CLI
uv run ironlayer lineage ./project --model fct_daily_revenue
```

For each downstream model:
- Is it a dashboard source? → Alert the dashboard owner
- Is it another team's dependency? → Coordinate before applying
- Is it a golden metric? → Check anomaly detection thresholds

---

## Step 5 — Apply or Gate

**If risk is LOW/MEDIUM and plan reviewed:**
```bash
uv run ironlayer apply plan.json --auto-approve
# or in CI: ironlayer apply plan.json (prompts for confirmation)
```

**If risk is HIGH:**
```bash
# Show plan to team, get approval, then:
uv run ironlayer apply plan.json  # interactive confirmation
```

**If risk is CRITICAL:**
- Do not apply
- Open a PR discussion with `ironlayer show plan.json` output in the body
- Tag relevant data engineers for review

---

## Step 6 — Cost Attribution

Plan outputs cost estimates using historical telemetry. For budgeting:

```bash
# All plans in last 30 days
uv run ironlayer history --since 30d --format cost-report

# Monthly cost by model tier
uv run ironlayer history --group-by model --since 30d
```

---

## Quick Reference — MCP Tools Available

| Tool | Purpose |
|------|---------|
| `ironlayer_plan` | Generate execution plan from git diff |
| `ironlayer_show` | Load and display a saved plan JSON |
| `ironlayer_lineage` | Table-level lineage (upstream + downstream) |
| `ironlayer_column_lineage` | Column-level lineage |
| `ironlayer_diff` | Semantic SQL diff (cosmetic vs structural) |
| `ironlayer_validate` | Schema contract validation |
| `ironlayer_models` | List all models with metadata |
| `ironlayer_transpile` | SQL dialect conversion |

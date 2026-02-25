# IronLayer Demo Project

A ready-made example project with git history for trying out the IronLayer CLI.

## Quick Start

```bash
# 1. Set up the demo (creates a git repo with two commits)
cd examples/demo-project
bash setup.sh

# 2. Generate a migration plan from the diff
cd demo
platform plan . HEAD~1 HEAD

# 3. Inspect the plan
platform show plan.json

# 4. View all models
platform models models/

# 5. View the dependency lineage
platform lineage models/
```

## What's Inside

The demo contains an e-commerce analytics pipeline with 9 models across three layers:

### Raw Layer
| Model | Type | Description |
|-------|------|-------------|
| `raw.source_events` | Full Refresh | Event ingestion from source system |
| `raw.source_orders` | Full Refresh | Order ingestion from source system |

### Staging Layer
| Model | Type | Description |
|-------|------|-------------|
| `staging.stg_events` | Incremental | Events enriched with user dimensions |
| `staging.stg_customers` | Full Refresh | Customer lifecycle staging |
| `staging.stg_orders` | Incremental | Orders with customer dimensions |

### Analytics Layer
| Model | Type | Description |
|-------|------|-------------|
| `analytics.orders_daily` | Incremental | Daily order aggregations |
| `analytics.customer_lifetime_value` | Full Refresh | CLV per customer |
| `analytics.user_metrics` | Full Refresh | User engagement metrics |
| `analytics.revenue_summary` | Full Refresh | Executive dashboard metrics |

## Git History

The setup script creates two commits:

1. **Baseline** (HEAD~1) — 8 models forming a complete pipeline
2. **Changes** (HEAD) — Adds `user_metrics`, a `net_revenue` column to `orders_daily`, and updates `revenue_summary` to include user metrics

Running `platform plan . HEAD~1 HEAD` diffs these two commits and generates a migration plan showing exactly what changed and what needs to be re-materialized.

## DAG Structure

```
raw.source_events ──> staging.stg_events ──> analytics.user_metrics ──┐
                                                                      │
raw.source_orders ──> staging.stg_orders ──> analytics.orders_daily ──┤
                                                                      ├──> analytics.revenue_summary
              staging.stg_customers ──> analytics.customer_lifetime_value ──┘
```

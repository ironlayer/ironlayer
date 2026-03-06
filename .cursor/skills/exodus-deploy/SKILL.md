---
name: exodus-deploy
description: >
  Walkthrough for deploying Exodus Foundation to a new client environment. Covers
  Terraform provisioning, Unity Catalog setup, dbt configuration, client YAML,
  GitHub App installation, and first PR review validation.
triggers:
  - "deploy to a new client"
  - "onboard a new client"
  - "client deployment"
  - "provision foundation for"
  - "set up exodus for"
outputs:
  - Deployment checklist with status
  - Terraform command sequence
  - Validation checklist
---

# Exodus Deploy — Client Onboarding Skill

> Deploy Exodus Foundation to a new client in 2 weeks.
> This skill walks you through every step with verification gates.

---

## Prerequisites — Gather Before Starting

From the client:

- [ ] GitHub organization name
- [ ] Cloud provider (AWS / Azure / GCP) and region
- [ ] Databricks workspace URL
- [ ] Service principal credentials (or agreement to create them)
- [ ] List of data sources needed (which bundles to enable)
- [ ] Agreed SLA for data freshness

From you:
- [ ] `exodus-clients/clients/{client-slug}/` directory created
- [ ] GitHub App installed on client repo
- [ ] Stripe subscription created if billable

---

## Phase 1 — Terraform Provisioning (Days 1-3)

```bash
cd exodus-foundation/terraform/environments/{client-slug}/

# 1. Initialize
terraform init

# 2. Plan — review before applying
terraform plan -var-file={client-slug}.tfvars -out=plan.tfplan

# 3. Apply cloud foundation (VPC/VNet, S3/ADLS/GCS, IAM)
terraform apply plan.tfplan

# 4. Apply Databricks workspace
cd ../databricks-workspace
terraform init && terraform plan -var-file={client-slug}.tfvars
terraform apply

# 5. Apply Unity Catalog (catalogs, schemas, grants)
cd ../databricks-unity-catalog
terraform init && terraform plan -var-file={client-slug}.tfvars
terraform apply
```

**Verification:**
```bash
# Confirm Unity Catalog catalogs exist
databricks unity-catalog catalogs list
# Should see: foundation_raw, foundation_dev, foundation_ci, foundation_prod
```

---

## Phase 2 — Client Configuration (Day 3-4)

```bash
# Create client config directory
mkdir -p exodus-clients/clients/{client-slug}/
mkdir -p exodus-clients/review-standards/
```

Create `exodus-clients/clients/{client-slug}/config/client.yml` (see `yaml-configs.mdc` for schema).

Create `exodus-clients/review-standards/{client-slug}.yml`:
```yaml
extends: default
client: {client-slug}
# Add client-specific rules here
```

---

## Phase 3 — dbt Configuration (Day 4-5)

```bash
cd exodus-foundation/dbt

# Create client profile
cat >> profiles.yml << EOF
{client-slug}:
  target: dev
  outputs:
    dev:
      type: databricks
      host: {workspace_url}
      http_path: /sql/1.0/warehouses/{warehouse_id}
      catalog: foundation_dev
      schema: staging
EOF

# Test connection
dbt debug --profile {client-slug}

# Enable bundles per client config
dbt deps
dbt compile --vars '{"bundle_crypto": true, "bundle_crm": true}'
dbt run --target dev --select tag:silver
```

---

## Phase 4 — First Extractor + Data Load (Day 5-8)

```bash
# Configure extractor
cp config/extractors/coinbase.yml config/extractors/coinbase_{client-slug}.yml
# Edit with client API credentials

# Test extraction (dry run)
uv run python -m foundation.extractors.cli run coinbase --dry-run

# Real extraction to foundation_raw
export COINBASE_API_KEY={client_api_key}
uv run python -m foundation.extractors.cli run coinbase

# Trigger dbt build
cd dbt && dbt run --target dev --select tag:silver tag:gold
```

---

## Phase 5 — GitHub App Installation (Day 8-9)

1. Direct client to: `https://github.com/apps/exodus-autopilot`
2. Client installs app on their org or specific repo
3. Verify webhook delivery in GitHub App settings
4. Check Foundation store: `sqlite3 ~/.exodus/store.db "SELECT * FROM installations;"`

```bash
# Test webhook (send a test ping)
gh api -X POST repos/{org}/{repo}/dispatches \
  --field event_type=test-ping
```

---

## Phase 6 — First PR Review Validation (Day 9-10)

```bash
# Create a test PR with a minor SQL change
git checkout -b test/first-review
echo "-- minor comment" >> dbt/models/staging/coinbase/stg_coinbase__candles.sql
git commit -m "test: trigger first exodus review"
gh pr create --title "test: trigger first exodus review" --body "Testing Autopilot Review Engine"
```

Verify in GitHub:
- [ ] Review Engine posted a comment within 60 seconds
- [ ] Comment has BLOCK/WARN/NOTE format
- [ ] Confidence score > 70
- [ ] Machine-readable `<!-- review-data: ... -->` block present

---

## Phase 7 — Monitoring Setup (Day 10-14)

```yaml
# Add to config/client.yml
golden_metrics:
  fct_daily_revenue:
    - column: revenue_usd
      threshold: 2.0
    - column: order_count
      threshold: 1.5
```

```bash
# Verify DataStewardAgent can see the metrics
# Via MCP:
# Call: foundation_pipeline_status
# Call: autopilot_agent_status
```

---

## Deployment Checklist

```
Phase 1 — Infrastructure
  [ ] Cloud foundation (VPC, S3/ADLS, IAM) applied
  [ ] Databricks workspace provisioned
  [ ] Unity Catalog: 4 catalogs exist (raw/dev/ci/prod)

Phase 2 — Config
  [ ] config/client.yml created and validated
  [ ] review-standards/{client}.yml created
  [ ] Bundle toggles match client data sources

Phase 3 — dbt
  [ ] dbt debug passes
  [ ] dbt compile succeeds for enabled bundles
  [ ] dbt run --target dev succeeds

Phase 4 — Data
  [ ] At least one extractor runs successfully
  [ ] foundation_raw.{source} tables have data
  [ ] dbt run produces rows in foundation_dev.gold

Phase 5 — GitHub App
  [ ] App installed on client repo
  [ ] Webhook delivery confirmed
  [ ] Installation record in Foundation store

Phase 6 — First Review
  [ ] Test PR created
  [ ] Review Engine posted comment < 60s
  [ ] Review format correct (BLOCK/WARN/NOTE)

Phase 7 — Monitoring
  [ ] golden_metrics configured
  [ ] DataStewardAgent active
  [ ] Freshness alerts configured
```

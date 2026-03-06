---
name: exodus-review
description: >
  Interactive PR review in Cursor using the Autopilot MCP. Reviews staged changes or a
  GitHub PR against Exodus standards, produces BLOCK/WARN/NOTE output, and optionally
  triggers the PRHealingAgent for auto-fix.
triggers:
  - "review my changes"
  - "review staged changes"
  - "check my PR before pushing"
  - "exodus review"
  - "run a code review"
outputs:
  - BLOCK/WARN/NOTE review findings
  - Confidence score
  - PRHealingAgent trigger (if BLOCK/WARN found)
---

# Exodus Review — Cursor Skill

> Get AI code review on your changes before or after pushing.
> Same standards as the GitHub App Review Engine — consistent quality gate.

---

## Option A — Review Staged/Local Changes (Before Push)

Review your uncommitted changes right now in Cursor:

```bash
# 1. Get your diff
git diff HEAD > /tmp/my-changes.diff
# or for staged only:
git diff --cached > /tmp/my-changes.diff
```

Then describe the diff and file types to Claude in Cursor:
- "Review this diff against Exodus standards"
- Paste the diff or share the file path

Claude will apply the `exodus-pr-review` skill checklist.

---

## Option B — Review a GitHub PR via MCP

```
Call MCP tool: autopilot_review_pr
Arguments:
  pr_url: https://github.com/org/repo/pull/42
  review_standards_path: /path/to/exodus-clients/review-standards/client-alpha.yml
```

This runs the full `CodeReviewAgent` cycle:
1. Fetches diff from GitHub API
2. Applies review standards (BLOCK/WARN/NOTE)
3. Returns structured findings
4. Posts review to GitHub PR

---

## Option C — Check PR Status

```
Call MCP tool: autopilot_agent_status
Arguments:
  pr_url: https://github.com/org/repo/pull/42
```

Returns:
- Current review findings
- Healing agent status (running / completed / needs human)
- Confidence score
- Auto-merge eligibility

---

## Interpreting Results

### BLOCK — Must Fix

These findings prevent merge. PRHealingAgent will attempt auto-fix.

Common BLOCK causes:
- Hardcoded API key or model ID
- `SELECT *` in staging
- Missing `surrogate_key()` macro
- LLM call in `execute()` method (determinism violation)
- Terraform wildcard IAM

### WARN — Should Fix

These should be addressed but don't block merge. PRHealingAgent will attempt auto-fix.

### NOTE — Suggestions

Non-blocking observations. Human decides whether to act.

---

## Triggering the Healing Agent

If BLOCK or WARN findings exist after review:

```
Call MCP tool: autopilot_heal_pr
Arguments:
  pr_url: https://github.com/org/repo/pull/42
  max_cycles: 3
```

Healing agent will:
1. Read each BLOCK/WARN finding
2. Apply the Fix instruction literally
3. Push fix commit to the PR branch
4. Re-run review to verify findings resolved
5. Repeat up to `max_cycles` times

---

## Review Standards Location

Default: `exodus-clients/review-standards/default.yml`
Per-client: `exodus-clients/review-standards/{client}.yml`

To see what rules apply:
```bash
cat exodus-clients/review-standards/default.yml
cat exodus-clients/review-standards/{client}.yml  # extends default
```

---

## After Review

If confidence ≥ 90 AND zero BLOCK findings AND ≥ 10 historical agent PRs:

```
Call MCP tool: autopilot_agent_status
# Check auto-merge eligibility
```

Otherwise, request human review via GitHub.

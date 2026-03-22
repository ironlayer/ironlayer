---
name: building-item
description: Walk through the 12-step development cycle when starting work on a backlog item. Use WHEN beginning any new work item from backlog-execution.md.
---

# Building a Backlog Item

Follow the 12-step development cycle from the AI-Driven Development Playbook.

## Steps

### Phase 1: Planning (before any code)
1. **READ** — Read `docs/build-notes/quick-reference.md`, the backlog item, `docs/dev-journal.md`, `docs/engineering-patterns.md`, and the last 10 entries of `docs/build-notes/bot-activity-log.jsonl`.
2. **VERIFY** — Read the ACTUAL source files you will modify. Mark each as VERIFIED or INFERRED.
3. **PLAN** — Write a plan to `docs/build-notes/plans/{item-id}-plan.md`. Include: files to change, approach + WHY, risks, tests, estimated commits. Assign a complexity tier.
4. **REVIEW PLAN** — Re-read the plan. Check against acceptance criteria, locked decisions, dev-journal lessons.

### Phase 2: Execution (plan approved)
5. **BRANCH** — Create feature branch: `{scope}/{item-slug}`
6. **BUILD** — Execute the plan. Commit incrementally. Format: `{item-id}: {what changed}`
7. **TEST** — Run full test suite. Fix ALL failures.
8. **NOTES** — Update dev-journal.md and engineering-patterns.md if applicable.

### Phase 3: Ship
9. **PR** — Push branch. Create PR using `.github/pull_request_template.md`.
10. **SELF-REVIEW** — Review via `git diff main...HEAD`.
11. **APPROVE** — Approve the PR.
12. **MERGE** — Squash-merge to main. Delete branch.
13. **NEXT** — Log completion to activity log. Update quick-reference.md. Proceed to next item.

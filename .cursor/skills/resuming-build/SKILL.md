---
name: resuming-build
description: Recovery sequence after context loss or session restart. Use WHEN returning to work after a break, crash, or new session.
---

# Resuming After Context Loss

## Recovery Sequence
1. Check git state: `git status && git log --oneline -5 && git branch --show-current`
2. Read `docs/build-notes/quick-reference.md`
3. Read last 10 entries of `docs/build-notes/bot-activity-log.jsonl`
4. Read `CLAUDE.md`
5. Determine: What item am I on? Is there uncommitted work? An open PR?
6. Resume from where you left off using the 12-step workflow.
7. If on main with no open work, start the next backlog item from `docs/backlog-execution.md`.

## Detection Signals
| Signal | Meaning | Action |
|--------|---------|--------|
| Uncommitted changes | Work in progress | Review diff, continue |
| Feature branch checked out | Item started | Check if plan exists, continue |
| Open PR | Ready for review/merge | Self-review and merge |
| Activity log shows completion | Done | Move to next item |
| Clean main, no open work | Ready | Start next backlog item |

---
name: capturing-lesson
description: Capture a non-obvious discovery or debugging breakthrough to dev-journal.md and/or engineering-patterns.md. Use WHEN you encounter something that would help a future developer.
---

# Capturing a Lesson

## When to Capture
- Non-obvious debugging breakthrough
- Surprising behavior discovered
- Reusable pattern identified
- Architectural decision made with tradeoffs

## Dev Journal Entry (`docs/dev-journal.md`)
Format:
### YYYY-MM-DD: {Title}
**Context**: What you were doing.
**Lesson**: What you learned.
**Pattern**: Generalized takeaway.

## Engineering Pattern Entry (`docs/engineering-patterns.md`)
Format:
### {Problem Title}
**Problem**: What went wrong or was non-obvious.
**Pattern**: The solution approach.
(Include code example if relevant)

## Rules
- Only entries that would help a future developer.
- No status updates or progress notes.
- If it doesn't teach something, skip it.
- Mark dev-journal entries extracted as patterns: `[→ engineering-patterns.md]`

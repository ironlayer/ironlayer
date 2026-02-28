---
description: Audit a completed phase of the IronLayer Check Engine against all 8 quality categories. Use this skill after any build phase of the Rust-powered ironlayer check engine is complete. Trigger whenever the user mentions auditing, reviewing, or verifying a check engine phase, or says something like "audit phase X" or "is phase X ready."
argument-hint: [phase-number]
---

# IronLayer Check Engine Audit — Phase $ARGUMENTS

You are auditing **Phase $ARGUMENTS** of the IronLayer Check Engine. This audit is **pass/fail** — every failure must be fixed before proceeding to the next phase. Execute every applicable check below, report findings, and block progression until all critical issues are resolved.

---

## AUDIT EXECUTION INSTRUCTIONS

1. Create a TodoWrite list with all 8 audit categories
2. Execute each category sequentially
3. Record every finding with file:line references
4. After all 8 categories, produce the formal audit report
5. If ANY category is FAIL, list the specific fixes needed

---

## AUDIT CATEGORY 1: COMPILATION & TOOLCHAIN

**Run these commands. Every single one must pass clean.**

```bash
# Must compile with zero warnings
cargo build --workspace 2>&1 | grep -c "warning"  # Must be 0

# Must pass clippy with warnings-as-errors
cargo clippy --workspace -- -D warnings

# Must be formatted
cargo fmt --all -- --check

# Must have no known vulnerabilities
cargo audit

# Must build in release mode (catches LTO/optimization issues)
cargo build --workspace --release

# PyO3 bindings must import successfully
python -c "from ironlayer_check_engine import CheckEngine, CheckConfig, CheckResult, Severity, CheckCategory, Dialect, quick_check; print('PyO3 OK')"
```

**Failure criteria:**
- ANY compiler warning = FAIL
- ANY clippy lint = FAIL
- ANY fmt diff = FAIL
- ANY cargo audit advisory with severity >= moderate = FAIL
- Release build failure = FAIL
- PyO3 import failure = FAIL

---

## AUDIT CATEGORY 2: CODE COMPLETENESS & INTEGRITY

**Scan the entire codebase for incomplete, softened, or placeholder implementations.**

### 2A: Forbidden Patterns Scan

Search for these forbidden patterns in `check_engine/src/` — ALL must return 0 results:

- `todo!()`
- `unimplemented!()`
- `FIXME`
- `HACK`
- `XXX`
- `PLACEHOLDER`
- `stub` (case insensitive)
- `// TODO`
- `.unwrap()` — flag ALL, must justify each one

**For each `.unwrap()` found:**
- If in a `#[cfg(test)]` block = PASS (acceptable in tests)
- If on regex compilation of a literal string = PASS with `.expect("regex is valid")`
- If in library code without justification = FAIL — must be replaced with `?` operator or `.expect("reason")`

### 2B: Empty/Trivial Function Bodies

Scan for functions that:
- Return `Vec::new()` when the spec requires cross-file checks (e.g., `check_project()` on checkers that have CON/REF cross-file rules)
- Return `Ok(())` or `Ok(CheckResult::default())` without performing work
- Contain only a single-line return with no validation logic

### 2C: Dead Code

- Commented-out code blocks > 3 lines = FAIL (delete or implement)
- `// ... additional cases ...` style truncation comments = FAIL
- Unused imports or functions flagged by clippy

### 2D: Code Softening Detection (CRITICAL)

**This catches AI-generated code that compiles but is incomplete.**

- **Catch-all match arms**: Search for `_ => Vec::new()`, `_ => vec![]`, `_ => Ok(vec![])`, `_ => {}` in match blocks on `ModelKind`, `Materialization`, `Dialect`, `Severity`, `CheckCategory`, `TokenKind` — every variant must be handled explicitly
- **Ellipsis/truncation comments**: Search for `similar`, `same pattern`, `follow the same`, `rest of`, `additional cases`, `other rules`, `remaining`, `etc.`, `and so on`, `likewise` in comments — these indicate truncated implementations
- **Rule ID completeness verification**: Count actually-implemented rule IDs vs. spec requirement per phase:

  | Phase | Required Rule IDs | Count |
  |-------|-------------------|-------|
  | 1 | HDR001-HDR013 | 13 |
  | 2 | + SQL001-SQL009, SAF001-SAF010, REF001-REF006, NAME001-NAME008 | +33 = 46 |
  | 3 | + YML001-YML009, DBT001-DBT006, CON001-CON005 | +20 = 66 |
  | 4 | All 66 rules (complete set) | 66 |

  **Verification method**: Grep for each rule ID string literal (e.g., `"HDR001"`, `"SAF005"`) in the checker source files. Every rule ID listed in the spec for this phase must appear in at least one `CheckDiagnostic` construction AND at least one test assertion.

- **Checker trait completeness**: Verify every checker struct implements both `check_file()` and `check_project()` where the spec requires cross-file checks (RefResolver, ModelConsistency).

- **Header parser termination logic**: Verify the SQL header parser in `sql_header.rs` follows the exact 4-point termination rule from §5.1:
  1. `-- key: value` lines are metadata (only `_KNOWN_FIELDS` stored)
  2. `--` with text but no colon = plain comment, does NOT terminate
  3. `--` alone = bare separator, does NOT terminate
  4. Empty/whitespace-only lines = skipped, do NOT terminate
  The first line that is **both non-empty AND not a comment** terminates the header. Blank lines inside the header block must be allowed.

- **Disabled-by-default rules**: Verify these rules are disabled by default in the checker implementations (not just config):
  - HDR007 (unrecognized header field) — preserves forward-compatible header extensions
  - HDR008, HDR009 (optional recommended fields)
  - CON004 (orphan model) — terminal mart models are legitimate leaf nodes
  - CON005 (no declared owner)
  - SQL006, SQL009, REF006, NAME007, NAME008, DBT005, DBT006, YML009

- **Token kind coverage**: Count implemented `TokenKind` variants in `sql_lexer.rs`. The spec requires 19 variants: `Keyword`, `Identifier`, `QuotedIdent`, `StringLiteral`, `NumberLiteral`, `Operator`, `LeftParen`, `RightParen`, `Comma`, `Semicolon`, `Dot`, `LineComment`, `BlockComment`, `JinjaOpen`, `JinjaClose`, `JinjaBlock`, `Whitespace`, `Newline`, `Unknown`. (Phase 2+)

- **Safety rule logic**: Read SAF001-SAF010 implementations. Verify each has UNIQUE keyword-sequence detection logic (not a generic "check if keyword exists" for all). Specifically:
  - SAF005 must scan for DELETE FROM without subsequent WHERE
  - SAF006 must detect ALTER TABLE ... DROP COLUMN (3 keyword sequence)
  - SAF010 must check INSERT OVERWRITE without PARTITION clause

- **Levenshtein implementation** (Phase 2+): Read the `levenshtein()` or equivalent function. Verify it uses the real Wagner-Fischer DP algorithm with an O(m×n) matrix, not a trivial comparison.

- **Config loading**: Verify config resolution order is implemented: `ironlayer.check.toml` → `pyproject.toml` → `ironlayer.yaml` → defaults. Check that per-path overrides use `globset` for matching.

### 2E: Crate Verification

Search `Cargo.toml` and `Cargo.lock` for banned crates:
- `serde_yaml_ng` should NOT be used — the spec specifies `serde_yaml = "0.9"`
- Verify `pyo3` version is `0.22` with `abi3-py311` feature
- Verify `ignore` crate is used (not just `walkdir` alone — must respect `.gitignore`)

**Failure criteria:**
- ANY `todo!()` or `unimplemented!()` = FAIL
- ANY unjustified `.unwrap()` in library code = FAIL
- ANY empty/placeholder function body = FAIL
- ANY commented-out code block > 3 lines = FAIL
- ANY catch-all match arm discarding variants = FAIL
- ANY truncation comment indicating unwritten code = FAIL
- ANY missing rule ID from the phase's required set = FAIL
- ANY missing TokenKind variant (Phase 2+) = FAIL
- ANY simplified/fake Levenshtein (Phase 2+) = FAIL

---

## AUDIT CATEGORY 3: DOCUMENTATION

**Every public item must be documented.**

```bash
# Compile with missing_docs warning
RUSTDOCFLAGS="-D missing_docs" cargo doc --workspace --no-deps 2>&1
```

**Manual checks:**
- Every `pub fn` has a `///` doc comment with one-line summary and `# Errors` section if it returns `Result`
- Every `pub struct` and `pub enum` has a `///` doc comment
- Every module has a `//!` module doc explaining purpose and integration with the Python side
- PyO3-exposed types have doc comments that explain their Python-side equivalents
- Checker structs document which rule IDs they implement

**Failure criteria:**
- ANY public item without a doc comment = FAIL
- ANY `pub fn` returning `Result` without `# Errors` documentation = FAIL
- ANY module without a `//!` header = FAIL

---

## AUDIT CATEGORY 4: ERROR HANDLING

**Errors must be helpful, contextual, and match the diagnostic quality spec.**

**Check error type definitions:**
- All error types use `thiserror` derive macros
- Error messages include: WHAT went wrong, WHERE (file path, line/column), and HOW to fix it (suggestion)
- The `CheckDiagnostic` struct is always populated with:
  - `rule_id`: non-empty, matches `^[A-Z]{2,4}\d{3}$` pattern
  - `message`: specific and actionable (NOT "invalid SQL" or "check failed")
  - `severity`: correct per spec defaults
  - `file_path`: relative to project root
  - `line`: 1-based (0 only when not applicable, e.g., project-level checks)
  - `suggestion`: populated when the spec says "Fixable" or when fuzzy matching finds a close match

**Check diagnostic quality — UNACCEPTABLE messages:**
- "Error in SQL file" (no context)
- "Invalid header" (no specifics)
- "Check failed" (no details)
- "Bad reference" (no target name)

**Check diagnostic quality — ACCEPTABLE messages:**
- "Missing required field 'name' in SQL header. Every IronLayer model must declare a name."
- "Undefined ref: 'raw.orders_v2'. No model with this name exists. Did you mean 'raw_orders_v2'? (Levenshtein distance: 1)"
- "kind: MERGE_BY_KEY requires 'unique_key' header field. Add '-- unique_key: <column_name>' to the header."

**Failure criteria:**
- ANY generic/contextless error message = FAIL
- ANY `CheckDiagnostic` with empty `rule_id` or `message` = FAIL
- ANY error-severity diagnostic without a suggestion when one is feasible = HIGH (not blocking but tracked)

---

## AUDIT CATEGORY 5: TEST COVERAGE

**Minimum test counts by phase:**

| Phase | Minimum Tests | Required Coverage |
|-------|--------------|-------------------|
| 1 | 65 | HDR001-HDR013 (positive + negative each), config loading, cache, discovery, PyO3 smoke |
| 2 | 185 | + SQL lexer tokens, SQL001-SQL009, SAF001-SAF010, REF001-REF006, NAME001-NAME008, parallel execution, cache persistence |
| 3 | 285 | + YML001-YML009, DBT001-DBT006, CON001-CON005, SARIF output, git integration, per-path overrides, fixture projects |
| 4 | 330 | + display formatting, MCP tool, multi-platform smoke |

```bash
# Count total tests
cargo test --workspace -- --list 2>&1 | grep "test$" | wc -l

# Run all tests
cargo test --workspace

# Run with specific checker tests
cargo test --workspace -- sql_header
cargo test --workspace -- ref_resolver
cargo test --workspace -- sql_lexer
```

**Required test categories per checker:**
- **Positive tests**: Rule fires correctly on input that violates it
- **Negative tests**: Rule does NOT fire on valid input
- **Edge cases**: Empty files, files with only comments, Unicode content, very long lines
- **Config override tests**: Rule disabled via config doesn't fire; severity overridden correctly

**Required test categories for cross-cutting concerns:**
- **Cache tests**: Cache hit skips re-check; content change invalidates; config change invalidates whole cache; engine version change invalidates
- **Discovery tests**: Correct project type detection for ironlayer/dbt/raw_sql; .gitignore respected; exclude patterns work
- **Parallel tests** (Phase 2+): Results are deterministic regardless of thread scheduling
- **Config loading tests**: TOML file → struct; pyproject.toml section → struct; defaults; per-path overrides; rule severity overrides

**Failure criteria:**
- Below minimum test count for phase = FAIL
- ANY test failing = FAIL
- ANY rule ID without both positive and negative tests = FAIL
- Missing cache invalidation tests = FAIL
- Missing config loading tests = FAIL

---

## AUDIT CATEGORY 6: ARCHITECTURE & DESIGN

**Verify structural correctness and adherence to the spec.**

### 6A: Type Fidelity

Verify Rust types match Python equivalents exactly:
- `Dialect` enum has exactly 3 variants: `Databricks`, `DuckDB`, `Redshift` — serializes to lowercase
- `Severity` enum has exactly 3 variants: `Error`, `Warning`, `Info` — ordered (Error > Warning > Info)
- `CheckCategory` enum has exactly 10 variants matching the spec
- `ModelKind` validation accepts exactly: `FULL_REFRESH`, `INCREMENTAL_BY_TIME_RANGE`, `APPEND_ONLY`, `MERGE_BY_KEY`
- `Materialization` validation accepts exactly: `TABLE`, `VIEW`, `MERGE`, `INSERT_OVERWRITE`
- `SchemaContractMode` validation accepts exactly: `DISABLED`, `WARN`, `STRICT`

### 6B: PyO3 Module Structure

Verify the `ironlayer_check_engine` Python module exports exactly:
- `CheckEngine` class
- `CheckConfig` class
- `CheckResult` class with `to_json()` and `to_sarif_json()` methods
- `CheckDiagnostic` class with all fields as read-only properties
- `Severity` enum
- `CheckCategory` enum
- `Dialect` enum
- `quick_check()` function

### 6C: Checker Trait Compliance

- Every checker implements `Checker` trait
- Checkers are stateless (no mutable fields)
- Checkers are `Send + Sync` (required for `rayon`)
- `check_file()` returns `Vec<CheckDiagnostic>` (never panics)
- `check_project()` returns `Vec<CheckDiagnostic>` (only implemented where cross-file checks are needed)

### 6D: Crate Boundaries

- `check_engine` crate type is `["cdylib", "rlib"]`
- No dependencies on `ironlayer-core` Python package from Rust (one-way: Python calls Rust, not vice versa — exception: YML006 callback)
- `pyo3-log` bridges Rust `log` to Python `logging`

### 6E: File Structure

Verify the actual file layout matches the spec's monorepo layout. Every file listed in §3.4 of the spec must exist (for the current phase).

**Failure criteria:**
- ANY enum variant mismatch with Python equivalents = FAIL
- ANY missing PyO3 export = FAIL
- ANY checker that is not `Send + Sync` = FAIL
- ANY Rust → Python dependency (wrong direction) = FAIL
- File layout divergence from spec = FAIL

---

## AUDIT CATEGORY 7: PERFORMANCE & SAFETY

### 7A: Safety Scan

```bash
# Search for unsafe code
grep -rn "unsafe" check_engine/src/ | grep -v "test" | grep -v "//"

# Search for panic paths in library code
grep -rn "panic!\|\.unwrap()\|\.expect(" check_engine/src/ | grep -v "test" | grep -v "#\[cfg(test)\]"
```

- ANY `unsafe` block in library code = FAIL (must justify or eliminate)
- ANY `panic!()` in library code = FAIL (use `Result` instead)
- `.expect()` is allowed ONLY with clear invariant justification (e.g., compiled regex literals)

### 7B: Resource Safety

- File handles are closed (use RAII, no manual close needed in Rust — verify no `forget()`)
- No unbounded allocations: `Vec` growth is bounded by file count or `max_diagnostics`
- Cache file writes use atomic rename (write to temp file `.tmp.{pid}`, then rename) to prevent corruption
- Cache concurrency: last-writer-wins (no file locking needed — stale cache only causes redundant re-checking)
- Corrupt cache recovery: if cache fails JSON parse, log warning, proceed as `--no-cache`, delete corrupt file

### 7C: Panic Recovery (Appendix D.1)

```bash
# Verify catch_unwind is used in engine.rs for per-file check dispatch
grep -n "catch_unwind" check_engine/src/engine.rs
# Must find at least one occurrence wrapping per-file checks

# Verify INTERNAL diagnostic is emitted on panic, not a process crash
grep -n '"INTERNAL"' check_engine/src/engine.rs
# Must find the panic recovery diagnostic construction
```

- Per-file checks wrapped in `std::panic::catch_unwind(std::panic::AssertUnwindSafe(|| ...))` = REQUIRED
- Cross-file `check_project()` calls also wrapped = REQUIRED
- Panic in one checker must not prevent other checkers from running = REQUIRED
- On panic, emit `INTERNAL` diagnostic with file path and bug report URL = REQUIRED

### 7D: Platform Robustness (Appendix D.2 + D.3)

```bash
# Verify path normalization — forward slashes everywhere
grep -n "replace.*\\\\\\\\.*/" check_engine/src/
# Should find path normalization in discovery or engine

# Verify UTF-8 handling
grep -n "UTF-8\|utf8\|from_utf8\|read_to_string" check_engine/src/
```

- All `file_path` values in `CheckDiagnostic` and `CheckResult` use **forward slashes** regardless of platform = REQUIRED
- Cache keys also use forward-slash paths (cross-platform portable) = REQUIRED
- Non-UTF-8 files emit `SQL008` with message "File is not valid UTF-8" = REQUIRED
- SQL lexer operates on `&str` (guaranteed UTF-8), reports line/column in Unicode scalar values = REQUIRED

### 7C: Performance Verification (Phase 2+)

```bash
# Run Criterion benchmarks
cargo bench --bench check_benchmark

# Verify targets
# 500 models cold: < 500ms
# 500 models warm: < 50ms
```

**Failure criteria:**
- ANY unsafe block without justification = FAIL
- ANY panic path in library code = FAIL
- Missing `catch_unwind` in per-file check dispatch (Phase 3+) = FAIL
- Missing path normalization to forward slashes (Phase 3+) = FAIL
- Non-UTF-8 files not handled gracefully (Phase 3+) = FAIL
- Benchmarks exceeding targets by >2x = FAIL (Phase 2+)
- Non-atomic cache writes = HIGH
- Missing corrupt cache recovery = HIGH

---

## AUDIT CATEGORY 8: FUNCTIONAL CORRECTNESS

**Run these scenarios against real fixture projects.**

### Phase 1: Header Validation Scenarios

```bash
# Create test fixtures and run the engine against them

# Scenario 1: Valid IronLayer model with all required headers
cat > /tmp/test_valid.sql << 'EOF'
-- name: stg_orders
-- kind: FULL_REFRESH
-- materialization: TABLE
SELECT id, created_at FROM raw.orders
EOF

# Scenario 1b: Header with blank lines and bare comments inside (MUST still parse)
cat > /tmp/test_header_blanks.sql << 'EOF'
-- name: stg_orders
--
-- This model stages raw orders
-- kind: FULL_REFRESH

-- materialization: TABLE
SELECT id, created_at FROM raw.orders
EOF
# Must parse name, kind, materialization correctly — blank lines and bare comments do NOT terminate

# Scenario 1c: Header terminated by SQL (not by blank line)
cat > /tmp/test_header_termination.sql << 'EOF'
-- name: stg_events
-- kind: FULL_REFRESH
SELECT * FROM raw.events
EOF
# The SELECT line terminates the header. Must parse name and kind correctly.

# Scenario 2: Missing required 'name' field (should trigger HDR001)
cat > /tmp/test_no_name.sql << 'EOF'
-- kind: FULL_REFRESH
SELECT 1
EOF

# Scenario 3: Invalid kind value (should trigger HDR003)
cat > /tmp/test_bad_kind.sql << 'EOF'
-- name: test_model
-- kind: INVALID_KIND
SELECT 1
EOF

# Scenario 4: MERGE_BY_KEY without unique_key (should trigger HDR006)
cat > /tmp/test_merge_no_key.sql << 'EOF'
-- name: dim_customers
-- kind: MERGE_BY_KEY
-- materialization: MERGE
SELECT id, name FROM raw.customers
EOF

# Scenario 5: INCREMENTAL_BY_TIME_RANGE without time_column (should trigger HDR005)
cat > /tmp/test_incr_no_time.sql << 'EOF'
-- name: fct_events
-- kind: INCREMENTAL_BY_TIME_RANGE
SELECT event_id, event_ts FROM raw.events
EOF

# Scenario 6: Unrecognized header field (should NOT trigger HDR007 by default — it's disabled)
cat > /tmp/test_unknown_field.sql << 'EOF'
-- name: stg_test
-- kind: FULL_REFRESH
-- foobar: something
SELECT 1
EOF
# HDR007 is DISABLED by default to preserve forward-compatible header extensions.
# This model must produce ZERO diagnostics with default config.
# With config `HDR007 = "warning"`, it should fire as warning.
```

### Phase 2+: SQL & Ref Scenarios

```bash
# Unbalanced parentheses (SQL001)
echo "-- name: test\n-- kind: FULL_REFRESH\nSELECT (a + b FROM t" | ironlayer check /tmp/test_dir

# Undefined ref (REF001) — must include suggestion if close match exists
# Self-ref (REF003)
# SELECT * warning (SQL004)
# DROP TABLE detection (SAF001)
# DELETE without WHERE (SAF005)
# Naming violations (NAME001-NAME005)
```

### Phase 3+: YAML & dbt Scenarios

```bash
# Invalid YAML syntax (YML001)
# Missing dbt_project.yml fields (YML002, YML003)
# Model in YAML but no .sql file (YML004)
# .sql file with no YAML documentation (YML005)
# Duplicate model names (CON001)
# dbt project structure violations (DBT001-DBT006)
```

### Phase 3+: --fix Mechanics Verification

```bash
# Create a file with fixable issues (SQL007 trailing semicolon, SQL009 tabs)
# Run: ironlayer check /tmp/test_dir --fix
# Verify: trailing semicolons removed, tabs replaced with 4 spaces
# Verify: fixes applied in reverse line order (bottom-up)
# Verify: atomic write (temp file then rename, not in-place)
# Verify: re-check runs after fix (no regressions introduced)
# Verify: fix report shows rule ID, action, and line numbers
# Verify: non-fixable rules are NOT modified
# Verify: HDR013 (duplicate headers) keeps first occurrence, removes subsequent
# Verify: REF004 replaces FQ name with short name only when unambiguous
```

### Phase 3+: SARIF Output Verification

```bash
# Run: ironlayer check /tmp/test_dir --sarif > result.sarif
# Verify: valid SARIF v2.1.0 JSON schema
# Verify: tool.driver.name = "ironlayer-check", version = "0.3.0"
# Verify field mapping:
#   rule_id → result.ruleId
#   message → result.message.text
#   severity Error → level "error", Warning → "warning", Info → "note"
#   file_path → locations[0].physicalLocation.artifactLocation.uri
#   line → locations[0].physicalLocation.region.startLine
#   column → locations[0].physicalLocation.region.startColumn
#   suggestion → fixes[0].description.text (omitted if None)
#   snippet → contextRegion.snippet.text (omitted if None)
```

### Phase 3+: YML006 Python Callback Verification

```bash
# Verify YML006 runs in check_project() (sequential), NOT check_file() (parallel)
# Verify GIL acquisition is scoped to the Python call only
# Verify graceful degradation when core_engine is not importable (info diagnostic emitted)
# Verify 5-second timeout per file for Python calls
```

### Cross-Cutting Scenarios (All Phases)

```bash
# Empty project directory — should detect as raw_sql with zero diagnostics
# Project with only .gitignore'd files — should report zero files checked
# Config with rule disabled — disabled rule should NOT fire
# Config with severity override — warning upgraded to error changes exit code
# --json flag — output is valid JSON matching CheckResult schema
# Exit code 0 on clean project
# Exit code 1 on project with errors
```

### Exclusion Precedence Scenarios (Phase 3+)

```bash
# .ironlayerignore file present — excluded files should not be checked
# .gitignore patterns respected — files in .gitignore should not be checked
# Hardcoded exclusions (target/, dbt_packages/, .venv/) always applied
# Config exclude list applies on top of above
# Precedence order: hardcoded → .gitignore → .ironlayerignore → config exclude
# All 4 levels of exclusion are cumulative (not first-match)
```

### Cache Scenarios (Phase 1+)

```bash
# First run: all files checked, cache populated
# Second run (no changes): all files skipped from cache, zero elapsed checking time
# Modify one file: only that file re-checked
# Change config: entire cache invalidated, all files re-checked
```

**Failure criteria:**
- ANY scenario producing wrong diagnostics = FAIL
- ANY crash/panic on valid input = FAIL
- ANY false negative (missed rule violation) = FAIL
- ANY exit code mismatch = FAIL
- JSON output not valid JSON = FAIL
- SARIF output not valid SARIF v2.1.0 (Phase 3+) = FAIL
- SARIF field mapping incorrect (Phase 3+) = FAIL
- Cache not invalidating on config change = FAIL
- `--json` flag not working = FAIL
- `--fix` not applying fixes atomically (Phase 3+) = FAIL
- `--fix` modifying non-fixable rules (Phase 3+) = FAIL
- YML006 crashing when core_engine unavailable (Phase 3+) = FAIL
- Non-forward-slash paths in diagnostics on any platform (Phase 3+) = FAIL

---

## AUDIT SEVERITY LEVELS

- **CRITICAL** — Must fix before proceeding. Compilation failure, missing rule IDs, wrong diagnostics, panic in library code, PyO3 binding failure.
- **HIGH** — Must fix before proceeding. Missing tests, undocumented public API, generic error messages, missing suggestions.
- **MEDIUM** — Should fix before proceeding. Excessive cloning, missing edge case tests, suboptimal error suggestions, cache not using atomic writes.
- **LOW** — Track for later. Minor style issues, optional performance improvements.

Only CRITICAL and HIGH block phase progression.

---

## AUDIT REPORT FORMAT

After running all 8 categories, produce a report in this EXACT format:

```
=============================================
  IRONLAYER CHECK ENGINE AUDIT — Phase $ARGUMENTS
  Date: [YYYY-MM-DD]
=============================================

1. COMPILATION & TOOLCHAIN
   Status: PASS / FAIL
   Warnings: [count]
   Clippy lints: [count]
   PyO3 import: PASS / FAIL
   Details: [if FAIL, list each issue]

2. CODE COMPLETENESS & INTEGRITY
   Status: PASS / FAIL
   todo!()/unimplemented!() found: [count]
   unwrap() in lib code: [count justified / count unjustified]
   Dead code blocks: [count]
   Catch-all match arms: [count]
   Truncation comments: [count]
   Rule IDs implemented: [count] / [count required for this phase]
   Missing rule IDs: [list]
   TokenKind variants: [count] / 19 required (Phase 2+)
   Levenshtein correct: YES / NO / N/A
   Config resolution order: YES / NO
   Details: [if FAIL, list each issue with file:line]

3. DOCUMENTATION
   Status: PASS / FAIL
   Undocumented public items: [count]
   Missing module headers: [count]
   Details: [if FAIL, list each item]

4. ERROR HANDLING
   Status: PASS / FAIL
   Generic diagnostic messages: [count]
   Diagnostics missing suggestions: [count]
   Empty rule_id fields: [count]
   Details: [if FAIL, list each issue]

5. TEST COVERAGE
   Status: PASS / FAIL
   Total tests: [count] (minimum required: [count])
   Tests passing: [count]
   Tests failing: [count]
   Rules without positive test: [list]
   Rules without negative test: [list]
   Details: [if FAIL, list gaps]

6. ARCHITECTURE & DESIGN
   Status: PASS / FAIL
   Dialect enum variants: [count] / 3
   Severity enum variants: [count] / 3
   CheckCategory enum variants: [count] / 10
   PyO3 exports complete: YES / NO
   Checkers are Send+Sync: YES / NO
   File structure matches spec: YES / NO
   Crate type correct (cdylib+rlib): YES / NO
   Details: [if FAIL, list each violation]

7. PERFORMANCE & SAFETY
   Status: PASS / FAIL
   Unsafe blocks: [count]
   Panics in lib code: [count]
   Unbounded allocations: [count]
   catch_unwind in engine.rs (Phase 3+): YES / NO / N/A
   Path normalization (forward slashes) (Phase 3+): YES / NO / N/A
   UTF-8 handling (Phase 3+): YES / NO / N/A
   Criterion benchmarks exist (Phase 2+): YES / NO
   500-model cold < 500ms (Phase 2+): YES / NO / N/A
   500-model warm < 50ms (Phase 2+): YES / NO / N/A
   Atomic cache writes: YES / NO
   Corrupt cache recovery: YES / NO
   Details: [if FAIL, list each issue]

8. FUNCTIONAL CORRECTNESS
   Status: PASS / FAIL
   Scenarios tested: [count]
   Scenarios passing: [count]
   Scenarios failing: [count]
   Exit codes correct (0/1/3): YES / NO
   JSON output valid: YES / NO
   SARIF output valid (Phase 3+): YES / NO / N/A
   SARIF field mapping correct (Phase 3+): YES / NO / N/A
   --fix mechanics correct (Phase 3+): YES / NO / N/A
   YML006 graceful degradation (Phase 3+): YES / NO / N/A
   Cache invalidation correct: YES / NO
   Project type detection correct: YES / NO
   Header parser termination logic correct: YES / NO
   Disabled-by-default rules verified: YES / NO
   Rule-specific findings: [list any rule that fires incorrectly or fails to fire]
   Details: [if FAIL, list each failing scenario with expected vs actual]

=============================================
  OVERALL: PASS / FAIL
  Critical issues: [count]
  High issues: [count]
  Medium issues: [count]
  Low issues: [count]

  PROCEED TO PHASE [next]: YES / NO
=============================================
```

Begin the audit of Phase $ARGUMENTS now. Start with the TodoWrite list, then execute each category systematically.

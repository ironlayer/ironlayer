---
description: Build a phase of the IronLayer Check Engine following strict quality standards. Use this skill when building any implementation phase of the Rust-powered ironlayer check subcommand — including the Rust crate, PyO3 bindings, CLI integration, checkers, SQL lexer, caching, or configuration. Trigger whenever the user mentions building, implementing, or coding a check engine phase, Rust checker, or PyO3 binding.
argument-hint: [phase-number]
---

# IronLayer Check Engine — Build Phase $ARGUMENTS

You are building **Phase $ARGUMENTS** of the IronLayer Check Engine, a Rust-powered `ironlayer check` subcommand that validates SQL models, YAML schemas, naming conventions, ref() integrity, and dbt project structure in under 1 second for 500+ model projects. The Rust engine compiles into a native Python extension via PyO3/maturin, bundled inside the existing `ironlayer-core` wheel.

## Codebase Integration Notes

Before building, know these directory mappings (spec uses different names than actual repo):
- **Spec says `ironlayer-core/`** → actual directory is **`core_engine/`** (PyPI name: `ironlayer-core`)
- **Spec says `poetry-core`** → actual build backend is **`hatchling`**
- **CLI source:** `cli/cli/app.py` (Typer app, `console = Console(stderr=True)`)
- **Display functions:** `cli/cli/display.py` (add `display_check_results()` alongside existing functions)
- **Core engine source:** `core_engine/core_engine/` (loader/, parser/, contracts/, sql_toolkit/, models/)

## Project Overview

The Check Engine replaces slow Python-based pre-commit validation (SQLFluff: 47s for 500 models) with a parallel Rust engine (<1s). It is the viral entry point that drives discovery of IronLayer's plan/apply/lineage capabilities.

**Key principle:** Zero-config useful, infinitely configurable. Running `ironlayer check .` with no config must produce useful results by auto-detecting project type (IronLayer native, dbt, or raw SQL).

---

## CRITICAL BUILD RULES — NO EXCEPTIONS

1. **NO stubs, NO placeholders, NO `todo!()`, NO `unimplemented!()`** — Every function must be fully implemented with production logic.
2. **NO code softening** — If the correct implementation is 100 lines, write 100 lines. Never simplify for brevity.
3. **All error paths must be handled explicitly** — No `.unwrap()` in library code. Use `?` operator with proper error types via `thiserror`.
4. **Every public function gets a doc comment** — `///` with description, `# Errors` section if it returns `Result`, `# Panics` if any panic path exists.
5. **Every module gets a module-level doc comment** — `//!` explaining purpose, design decisions, and integration with the Python side.
6. **Tests are NOT optional** — Every checker gets at least 5 unit tests. Every rule ID must have a test proving it fires correctly AND a test proving it doesn't false-positive.
7. **Use `#[must_use]` on functions returning Results/Options** where callers should handle the return value.
8. **No dead code** — No commented-out code blocks. No unused imports. `cargo clippy` must pass clean.
9. **PyO3 types must mirror Python exactly** — Rust enums, structs, and field names must match the existing Pydantic models in `ironlayer-core` (ModelDefinition, SQLGuardViolation, ContractViolation, ViolationSeverity, etc.).
10. **Diagnostics must be actionable** — Every `CheckDiagnostic` must have a specific message, file path, line number (where applicable), and a suggestion when one exists.

---

## CODE INTEGRITY RULES — ANTI-SOFTENING ENFORCEMENT

**This section exists because AI code generation has a strong tendency to "soften" implementations — producing code that compiles but is incomplete. Every pattern below is BANNED.**

### BANNED PATTERNS — Immediate audit failure if found:

1. **Catch-all match arms that discard data:**
   ```rust
   // BANNED — handles 2 of 4 ModelKind variants, discards the rest
   match kind {
       ModelKind::FullRefresh => { /* real logic */ },
       ModelKind::IncrementalByTimeRange => { /* real logic */ },
       _ => Ok(vec![]),  // ← BANNED: silently skips APPEND_ONLY and MERGE_BY_KEY
   }
   ```
   **REQUIRED:** Every match on ModelKind, Materialization, Dialect, Severity, CheckCategory, or TokenKind must explicitly handle ALL variants with correct logic. If a variant is genuinely not applicable, return an empty `Vec<CheckDiagnostic>` with a comment explaining why.

2. **Partial checker implementations:**
   ```rust
   // BANNED — implements 3 of 13 HDR rules
   fn check_file(&self, ...) -> Vec<CheckDiagnostic> {
       let mut diags = vec![];
       // HDR001: missing name
       // HDR002: missing kind
       // HDR003: invalid kind
       // ... remaining rules follow same pattern  ← BANNED
       diags
   }
   ```
   **REQUIRED:** If the spec says HDR001-HDR013, implement ALL 13 rules. Each has unique validation logic (HDR005 requires `time_column` only for `INCREMENTAL_BY_TIME_RANGE`, HDR006 requires `unique_key` only for `MERGE_BY_KEY`). These are NOT "the same pattern."

3. **Placeholder returns:**
   ```rust
   // BANNED — compiles but does nothing
   fn check_project(&self, models: &[DiscoveredModel], config: &CheckConfig) -> Vec<CheckDiagnostic> {
       Vec::new()  // ← BANNED: placeholder when cross-file checks are required
   }
   ```

4. **Incomplete token handling in the SQL lexer:**
   ```rust
   // BANNED — handles 3 token kinds, catch-all for the rest
   match ch {
       '\'' => self.lex_string(),
       '-' if self.peek() == '-' => self.lex_line_comment(),
       '{' if self.peek() == '{' => self.lex_jinja_open(),
       _ => Token { kind: TokenKind::Unknown, .. },  // ← BANNED: lazy fallthrough
   }
   ```
   **REQUIRED:** The lexer must handle ALL token kinds: keywords, identifiers, quoted identifiers (backtick and double-quote), string literals (with `''` escaping), number literals, operators, all punctuation (parens, comma, semicolon, dot), line comments, block comments (including nested), Jinja templates (`{{ }}`, `{% %}`, `{# #}`), whitespace, and newlines.

5. **Simplified Levenshtein for REF001 suggestions:**
   ```rust
   // BANNED
   fn levenshtein(a: &str, b: &str) -> usize {
       if a == b { 0 } else { 1 }
   }
   ```
   **REQUIRED:** Full Wagner-Fischer dynamic programming algorithm. The spec requires Levenshtein distance ≤ 3 for suggestions on undefined refs.

6. **Incomplete safety rule keyword detection:**
   ```rust
   // BANNED — checks for DROP TABLE but ignores the other 9 safety rules
   fn check_safety(&self, tokens: &[Token]) -> Vec<CheckDiagnostic> {
       // SAF001 only, rest "follow the same pattern"
   }
   ```
   **REQUIRED:** SAF001-SAF010 each have unique keyword sequences. `SAF005` (DELETE without WHERE) requires scanning forward for a WHERE keyword. `SAF010` (INSERT OVERWRITE without PARTITION) requires checking for a PARTITION clause. These are fundamentally different algorithms.

7. **Hardcoded config instead of loading from TOML:**
   ```rust
   // BANNED
   let config = CheckConfig {
       fail_on_warnings: false,
       max_diagnostics: 200,
       // ... hardcoded defaults
   };
   ```
   **REQUIRED:** Config must be loaded via the resolution order: `ironlayer.check.toml` → `pyproject.toml [tool.ironlayer.check]` → `ironlayer.yaml [check]` → built-in defaults. Per-path overrides must work.

8. **Ignoring the cache invalidation contract:**
   ```rust
   // BANNED — cache that never invalidates
   fn is_cached(&self, path: &str, hash: &str) -> bool {
       self.entries.contains_key(path)  // ← BANNED: ignores hash comparison
   }
   ```
   **REQUIRED:** Cache checks content hash, config hash, and engine version. All three must match for a cache hit.

### THE RULE OF COMPLETENESS

**If the spec defines a rule ID, it must be fully implemented with correct detection logic, a specific diagnostic message, and a test proving it fires.** Not partial. Not simplified. The audit will verify every rule ID, every checker, every token kind, every config field.

---

## Rust Style

- **Edition 2021**, MSRV 1.75.0
- **Format with `rustfmt`** — standard config
- **Clippy clean** — `cargo clippy --workspace -- -D warnings` must pass
- **Naming**: snake_case for functions/variables, CamelCase for types, SCREAMING_SNAKE for constants
- **Error types**: `thiserror` for all error types
- **Imports**: Group by std, external crates, internal modules, separated by blank lines
- **PyO3 conventions**: `#[pyclass]`, `#[pymethods]`, `#[pyfunction]` with proper `get_all`/`set_all` as needed

---

## Workspace Architecture

```
ironlayer/                              (existing repo root)
├── core_engine/                        (existing Python package — pkg name: ironlayer-core)
│   ├── core_engine/                    (Python source modules — UNCHANGED)
│   └── pyproject.toml                  (MODIFIED — hatchling → maturin build-backend)
├── check_engine/                       (NEW — Rust crate)
│   ├── Cargo.toml
│   ├── src/
│   │   ├── lib.rs                      PyO3 module entry point
│   │   ├── engine.rs                   CheckEngine struct (orchestrator)
│   │   ├── config.rs                   CheckConfig, RuleConfig, NamingConfig
│   │   ├── discovery.rs                File walker + project type detection
│   │   ├── cache.rs                    Content-addressable check cache
│   │   ├── checkers/
│   │   │   ├── mod.rs                  Checker trait + registry
│   │   │   ├── sql_header.rs           HDR001-HDR013
│   │   │   ├── sql_syntax.rs           SQL001-SQL009
│   │   │   ├── sql_safety.rs           SAF001-SAF010
│   │   │   ├── ref_resolver.rs         REF001-REF006
│   │   │   ├── yaml_schema.rs          YML001-YML009
│   │   │   ├── naming.rs              NAME001-NAME008
│   │   │   ├── dbt_project.rs          DBT001-DBT006
│   │   │   └── model_consistency.rs    CON001-CON005
│   │   ├── sql_lexer.rs                Lightweight SQL tokenizer
│   │   ├── types.rs                    CheckResult, CheckDiagnostic, Severity, etc.
│   │   ├── reporter.rs                 JSON + SARIF output generation
│   │   └── pyo3_bindings.rs            PyO3 class/function definitions
│   ├── tests/
│   │   ├── fixtures/                   Test SQL files, YAML configs
│   │   ├── test_sql_header.rs
│   │   ├── test_ref_resolver.rs
│   │   ├── test_sql_lexer.rs
│   │   ├── test_naming.rs
│   │   ├── test_yaml_schema.rs
│   │   └── test_integration.rs
│   └── benches/
│       └── check_benchmark.rs          Criterion benchmarks
├── Cargo.toml                          (workspace root)
└── .cargo/config.toml                  (cross-compilation settings)
```

---

## Dependencies (Cargo.toml)

```toml
[dependencies]
pyo3 = { version = "0.22", features = ["extension-module", "abi3-py311"] }
rayon = "1.10"
serde = { version = "1", features = ["derive"] }
serde_json = "1"
serde_yaml = "0.9"
regex = "1"
walkdir = "2"
sha2 = "0.10"
hex = "0.4"
globset = "0.4"
ignore = "0.4"
thiserror = "2"
log = "0.4"
pyo3-log = "0.11"
memchr = "2"
unicode-segmentation = "1"
dirs = "6"
chrono = { version = "0.4", features = ["serde"] }

[dev-dependencies]
criterion = { version = "0.5", features = ["html_reports"] }
tempfile = "3"
indoc = "2"
```

---

## Existing Python Integration Points — MUST MATCH EXACTLY

The Rust engine must produce output compatible with these existing Pydantic models:

| Python Type | Source File | Rust Mirror | Critical Fields |
|---|---|---|---|
| `ModelKind` | `core_engine/core_engine/models/model_definition.py` | `enum ModelKind` | `FULL_REFRESH`, `INCREMENTAL_BY_TIME_RANGE`, `APPEND_ONLY`, `MERGE_BY_KEY` |
| `Materialization` | `core_engine/core_engine/models/model_definition.py` | `enum Materialization` | `TABLE`, `VIEW`, `MERGE`, `INSERT_OVERWRITE` |
| `SchemaContractMode` | `core_engine/core_engine/models/model_definition.py` | `enum SchemaContractMode` | `DISABLED`, `WARN`, `STRICT` |
| `Dialect` | `core_engine/core_engine/sql_toolkit/_types.py` | `enum Dialect` | `DATABRICKS="databricks"`, `DUCKDB="duckdb"`, `REDSHIFT="redshift"` (serializes lowercase) |
| `ViolationSeverity` | `core_engine/core_engine/contracts/schema_validator.py` | `enum Severity` | `BREAKING`→Error, `WARNING`→Warning, `INFO`→Info |
| `DangerousOperation` | `core_engine/core_engine/parser/sql_guard.py` | maps to SAF rules | 11 variants + `_DEFAULT_SEVERITY` mapping |
| `sql_guard.Severity` | `core_engine/core_engine/parser/sql_guard.py` | maps to Rust Severity | `CRITICAL`→Error, `HIGH`→Warning, `MEDIUM`→Warning |
| `_REF_PATTERN` | `core_engine/core_engine/loader/ref_resolver.py` | Rust `regex` crate | `r"\{\{\s*ref\s*\(\s*(?:'([^']+)'\|\"([^\"]+)\")\s*\)\s*\}\}"` |
| `_REQUIRED_FIELDS` | `core_engine/core_engine/loader/model_loader.py` | hardcoded set | `frozenset({"name", "kind"})` |
| `_KNOWN_FIELDS` | `core_engine/core_engine/loader/model_loader.py` | hardcoded set | 13 fields (name, kind, materialization, time_column, unique_key, partition_by, incremental_strategy, owner, tags, dependencies, contract_mode, contract_columns, tests) |

**CLI patterns to replicate exactly (from `cli/cli/app.py`):**
- `@app.command()` decorator — Typer command with `repo: Path` argument (exists=True, file_okay=False, resolve_path=True)
- `console = Console(stderr=True)` — all Rich output goes to stderr
- `_json_output` global — `--json`/`--no-json` flag set in `_global_options()` callback
- `_emit_metrics(event: str, data: dict[str, Any])` — telemetry emission (line 109)
- `_load_stored_token() -> str | None` — cloud upsell check (line 145)
- `raise typer.Exit(code=N)` — exit codes: 0=success, 1=failures, 3=internal error
- `display_check_results()` added to `cli/cli/display.py` following same `(console: Console, ...)` pattern

---

## Performance Requirements

| Scenario | Target |
|---|---|
| 100 SQL models, cold | < 200ms |
| 500 SQL models, cold | < 500ms |
| 500 SQL models, warm (cached) | < 50ms |
| 1000 SQL models, cold | < 1s |
| Single file (incremental) | < 20ms |

**Strategies:** `rayon` parallelism, SHA-256 content-addressable cache, zero-copy lexer (`&str` slices), `ignore` crate for .gitignore-aware walking, lazy YAML parsing, early termination at `max_diagnostics`.

---

## Rule ID Registry — Complete Reference

Every rule the engine must implement:

**SQL Header (HDR001-HDR013):** 9 enabled errors/warnings + 4 disabled. Validates `-- key: value` header block. Only fires for `project_type == "ironlayer"`. Note: HDR007 (unrecognized header field) is **disabled by default** to preserve forward-compatible header extensions (per `model_loader.py` design).

**SQL Syntax (SQL001-SQL009):** 7 enabled + 2 disabled. Uses lightweight lexer token stream (NOT full AST). Covers bracket balance, string balance, SELECT *, missing WHERE on DELETE, empty body.

**SQL Safety (SAF001-SAF010):** 10 rules mirroring `sql_guard.py` DangerousOperation enum. Keyword-sequence detection outside string literals/comments. Fast pre-filter (false positives acceptable).

**Ref Resolution (REF001-REF006):** 4 enabled + 2 disabled. Regex extraction identical to `ref_resolver._REF_PATTERN`. Cross-file resolution via model registry.

**YAML Schema (YML001-YML009):** 8 enabled + 1 disabled. Covers parse errors, dbt_project.yml required fields, model/SQL correspondence, test coverage.

**Naming Convention (NAME001-NAME008):** 6 enabled + 2 disabled. Regex-based. Layer detection from directory structure. All patterns configurable in TOML.

**dbt Project (DBT001-DBT006):** 4 enabled + 2 disabled. Only fires for `project_type == "dbt"`.

**Model Consistency (CON001-CON005):** 3 enabled + 2 disabled. Cross-file analysis in `check_project()` phase. Note: CON004 (orphan model) is **disabled by default** because terminal mart models consumed by BI tools are legitimately never referenced within the project.

**Total: 66 rules across 8 categories.**

---

## Build System Migration Context

> **Note:** The spec uses `ironlayer-core/` as the directory name. The actual on-disk directory is **`core_engine/`** (the PyPI package name is `ironlayer-core`). The spec says `poetry-core` — the actual current build backend is **`hatchling`**.

`ironlayer-core` (directory: `core_engine/`) switches from `hatchling` (pure-Python, `py3-none-any` wheels) to `maturin` (Rust+Python, platform-specific wheels). Key implications:
- `core_engine/pyproject.toml` build-system changes from `hatchling` to `maturin>=1.7,<2.0`
- `[tool.hatch.build]` sections replaced with `[tool.maturin]` configuration
- Resulting wheel changes from `py3-none-any` to platform-specific (e.g., `cp311-abi3-manylinux_2_17_x86_64`)
- `ironlayer` (CLI package at `cli/`) remains pure-Python with hatchling
- CI must build platform-specific wheels where it previously built a single universal wheel

---

## Implementation Details — Spec-Critical Behaviors

### Header Parser Termination Logic (§5.1)

The Rust header parser MUST replicate this exact logic from `model_loader.parse_yaml_header()`:

A line is part of the header if it matches ANY of:
1. `-- key: value` — a metadata declaration (only `_KNOWN_FIELDS` keys are stored; unknown keys are silently skipped)
2. `--` followed by text without a colon — a plain comment (skipped, does NOT terminate the header)
3. `--` alone — a bare comment separator (skipped, does NOT terminate the header)
4. An empty/whitespace-only line — skipped, does NOT terminate the header

The first line that is **both non-empty AND not a comment** terminates the header block. Blank lines and bare `--` comments inside the header block are allowed and do NOT end it.

### Severity Dual-System Mapping (§4.3)

IronLayer has TWO separate severity systems. The check engine unifies them:

| Source System | Source Level | Check Engine Severity |
|---|---|---|
| `sql_guard.Severity` | CRITICAL (DROP_TABLE, DROP_VIEW, DROP_SCHEMA, TRUNCATE, GRANT, REVOKE, CREATE_USER, RAW_EXEC) | Error |
| `sql_guard.Severity` | HIGH (DELETE_WITHOUT_WHERE, ALTER_DROP_COLUMN, INSERT_OVERWRITE_ALL) | Warning |
| `sql_guard.Severity` | MEDIUM (reserved for future) | Warning |
| `schema_validator.ViolationSeverity` | BREAKING | Error |
| `schema_validator.ViolationSeverity` | WARNING | Warning |
| `schema_validator.ViolationSeverity` | INFO | Info |

### YML006 Python Callback + GIL Handling (§5.5)

YML006 (column listed in YAML not matching SQL output columns) requires full AST analysis via Python's `sql_toolkit.scope_analyzer.extract_columns()`. The Rust engine calls into Python via `Python::with_gil()`.

**GIL rules:**
- GIL is acquired only for the duration of the Python call, not the entire check run
- YML006 runs in the **sequential** `check_project()` phase, NOT the parallel per-file phase, to avoid GIL contention
- If `core_engine` import fails, YML006 is silently skipped with an info diagnostic: "YML006 skipped: Python SQL toolkit unavailable."
- Python call has a 5-second timeout per file; if exceeded, skip with warning

### --fix Mechanics (§7.4)

When `--fix` is passed, the engine modifies files in place for fixable rules only:

1. **Dry-run first:** Run all checks normally, collect diagnostics
2. **Filter fixable:** Only rules marked fixable AND with severity ≤ configured level
3. **Apply per-file:** Read content → apply fixes in **reverse line order** (bottom-up to avoid line shift) → atomic write (`.tmp` then rename)
4. **Re-check:** Re-run checks on modified files to confirm no regressions
5. **Report:** Show which fixes were applied with rule ID, action, and line numbers

**Fixable rules and their fix actions:**
| Rule | Fix Action |
|------|-----------|
| `SQL007` | Remove trailing semicolons from SQL body |
| `SQL009` | Replace tab characters with 4 spaces |
| `HDR013` | Remove duplicate header lines (keep first occurrence) |
| `REF004` | Replace fully-qualified ref name with short name where unambiguous |

No backups are created — assumes files are under version control.

### Cache Concurrency (§11.3)

Two concurrent `ironlayer check` processes may race on the cache file. Handle with:
1. **Atomic writes:** Write to `.ironlayer/check_cache.json.tmp.{pid}` then rename via `std::fs::rename()`. On POSIX rename is atomic; on Windows use `ReplaceFile`.
2. **Last writer wins:** No file locking. Stale cache only causes redundant re-checking (correctness is never affected).
3. **Corrupt cache recovery:** If cache fails to parse as JSON, log warning, proceed as `--no-cache`, delete and rebuild the corrupt file.

### .ironlayerignore + Exclusion Precedence (§10.2)

Exclusion precedence (all applied, not first-match):
1. Hardcoded exclusions (target/, dbt_packages/, .venv/, etc.) — always applied
2. `.gitignore` — if present in repo
3. `.ironlayerignore` — gitignore-compatible syntax, present in repo root or any subdirectory
4. `exclude` list from `ironlayer.check.toml` config

### SARIF Field Mapping (§8.3)

| CheckDiagnostic field | SARIF location |
|---|---|
| `rule_id` | `result.ruleId` |
| `message` | `result.message.text` |
| `severity` | `result.level` (Error→error, Warning→warning, Info→note) |
| `file_path` | `result.locations[0].physicalLocation.artifactLocation.uri` |
| `line` | `result.locations[0].physicalLocation.region.startLine` |
| `column` | `result.locations[0].physicalLocation.region.startColumn` |
| `suggestion` | `result.fixes[0].description.text` (omitted if None) |
| `snippet` | `result.locations[0].physicalLocation.contextRegion.snippet.text` (omitted if None) |

### Platform Robustness (Appendix D)

**D.1 Panic Recovery:** Every per-file check in `engine.rs` must be wrapped in `std::panic::catch_unwind(std::panic::AssertUnwindSafe(|| ...))`. If a checker panics, emit a single `INTERNAL` diagnostic instead of crashing the Python process. Cross-file checks (`check_project()`) are also wrapped. A panic in one checker does not prevent other checkers from running.

**D.2 Windows Path Normalization:** All `file_path` values in `CheckDiagnostic` and `CheckResult` use **forward slashes** regardless of platform. After file discovery, normalize via `path.replace('\\', "/")`. The cache file also uses forward-slash keys for cross-platform portability.

**D.3 Unicode/UTF-8:** Read all files as UTF-8. Non-UTF-8 files emit `SQL008` with message "File is not valid UTF-8." The SQL lexer operates on `&str` (guaranteed UTF-8), using byte offsets internally but reporting line/column in Unicode scalar values.

---

## PHASE-SPECIFIC BUILD INSTRUCTIONS

### Phase 1: Foundation (Week 1-2)

**Goal:** Rust crate builds, PyO3 bindings work, one checker runs end-to-end.

**Build order:**
1. Workspace `Cargo.toml` + `check_engine/Cargo.toml` with all dependencies
2. `types.rs`: All type definitions (Dialect, Severity, CheckCategory, CheckDiagnostic, CheckResult, DiscoveredModel)
3. `config.rs`: CheckConfig struct + TOML loading with resolution order
4. `discovery.rs`: File walker via `ignore` crate + `detect_project_type()` (IronLayer → dbt → RawSql)
5. `cache.rs`: Content-addressable cache with SHA-256 hashing, config hash invalidation, engine version check
6. `checkers/mod.rs`: Checker trait definition + checker registry
7. `checkers/sql_header.rs`: HDR001-HDR013 (all 13 rules, fully implemented). **Critical:** Header parser must follow the exact 4-point termination rule from §5.1 — blank lines and bare `--` comments inside the header block do NOT terminate it. Only the first non-empty, non-comment line terminates. HDR007 is disabled by default.
8. `engine.rs`: Sequential orchestrator (no parallelism yet) — discover → cache check → parse headers → run checkers → build result
9. `pyo3_bindings.rs`: Module definition, CheckEngine/CheckConfig/CheckResult classes, `quick_check()` function
10. `lib.rs`: Wire up PyO3 module
11. Integration: `cli/cli/app.py` check command wired up with Typer (add `@app.command()`, use existing globals/helpers)
12. Maturin build produces working wheel
13. Minimum 65 tests (5+ per HDR rule, integration smoke tests)

**Deliverable:** `ironlayer check path/to/project` runs, detects project type, validates SQL headers, returns structured CheckResult via PyO3.

### Phase 2: Core Checkers (Week 3-4)

**Goal:** All high-value checks working. Ready for internal dogfooding.

**Build order:**
1. `sql_lexer.rs`: Full token stream — all TokenKind variants (Keyword, Identifier, QuotedIdent, StringLiteral, NumberLiteral, Operator, all Punctuation, LineComment, BlockComment with nesting, JinjaOpen/Close/Block, Whitespace, Newline, Unknown). Correct string escape handling. Jinja template awareness. Databricks backtick support.
2. `checkers/sql_syntax.rs`: SQL001-SQL009 using token stream
3. `checkers/sql_safety.rs`: SAF001-SAF010 keyword-sequence detection (each rule has unique logic)
4. `checkers/ref_resolver.rs`: REF001-REF006 with regex extraction + model registry + Levenshtein suggestions (full Wagner-Fischer)
5. `checkers/naming.rs`: NAME001-NAME008 with configurable regex patterns + layer detection from directory structure
6. `engine.rs`: Switch to `rayon` parallel execution (`par_iter` for per-file checks)
7. `reporter.rs`: JSON output via `serde_json`, `to_json()` and `to_sarif_json()` methods
8. `cache.rs`: Persistence to `.ironlayer/check_cache.json` + all invalidation triggers. **Implement atomic writes** (temp file + rename), last-writer-wins concurrency, and corrupt cache recovery (log warning, delete, rebuild).
9. Criterion benchmark: confirm <500ms on synthetic 500-model project
10. Minimum 120 additional tests (total ~185)

**Deliverable:** All SQL, safety, ref, and naming checks operational. Parallel execution. Cache working. Benchmark passing.

### Phase 3: YAML & dbt (Week 5-6)

**Goal:** Full dbt project support. Ready for public beta.

**Build order:**
1. `checkers/yaml_schema.rs`: YML001-YML009 using `serde_yaml` parsing. **YML006 requires Python callback** — implement `Python::with_gil()` call to `core_engine.sql_toolkit` for column extraction. Must run in sequential `check_project()` phase (not parallel) to avoid GIL contention. Handle import failure gracefully (skip with info diagnostic). 5-second timeout per file.
2. `checkers/dbt_project.rs`: DBT001-DBT006 (parse `dbt_project.yml` for model-paths, sources)
3. `checkers/model_consistency.rs`: CON001-CON005 cross-file analysis (duplicate names, orphan models, dependency mismatches). Note: CON004 is disabled by default.
4. `reporter.rs`: SARIF v2.1.0 output for GitHub Code Scanning integration. **Map CheckDiagnostic fields to SARIF per the field mapping table in §8.3** — severity maps to level (Error→error, Warning→warning, Info→note), suggestion maps to fixes[0].description.text, snippet maps to contextRegion.
5. `config.rs`: Per-path rule overrides (`[[check.per_path]]` with glob matching via `globset`)
6. `discovery.rs`: `--changed-only` git integration (`git diff --name-only HEAD` + `--staged`). Also implement `.ironlayerignore` support (gitignore-compatible syntax via `ignore` crate, follows 4-level exclusion precedence: hardcoded → .gitignore → .ironlayerignore → config exclude).
7. `engine.rs`: `--fix` support for fixable rules (SQL007, SQL009, HDR013, REF004). **Follow the 5-step workflow:** dry-run → filter fixable → apply reverse-line-order with atomic write → re-check → report. No backups created (assumes git). Also implement `catch_unwind` panic recovery — wrap every per-file check dispatch and cross-file `check_project()` call.
8. Platform robustness: Windows path normalization (forward slashes always in diagnostics and cache keys), UTF-8 validation (non-UTF-8 files → SQL008 diagnostic).
9. Python fallback: pure Python check implementation using existing `model_loader`, `ref_resolver`, `sql_guard`, `schema_validator`
10. pre-commit hook configuration and testing
11. Full integration test suite with fixture projects (ironlayer_project, dbt_project, empty_project)
12. Minimum 100 additional tests (total ~285)

**Deliverable:** Complete check engine with all 66 rules. SARIF output. Git integration. Fixable rules. Python fallback.

### Phase 4: Polish & Launch (Week 7-8)

**Goal:** PyPI release, multi-platform wheels, documentation.

**Build order:**
1. CI/CD: GitHub Actions workflow building wheels for 5 platforms (Linux x86_64/aarch64, macOS x86_64/aarch64, Windows x86_64)
2. Type stubs: `ironlayer_check_engine.pyi` with full type annotations
3. `display.py`: Rich-formatted check results (grouped by file, severity icons, suggestion rendering)
4. Documentation: Rule reference pages for all 66 rules with examples
5. `ironlayer init`: Generate `ironlayer.check.toml` template
6. MCP tool: `ironlayer_check` tool exposed via existing MCP server
7. Final benchmark: 500 models in <500ms confirmed on CI
8. Package `ironlayer-core` v0.3.0 wheel with bundled Rust extension
9. Package `ironlayer` v0.3.0 CLI with check command
10. pre-commit integration documented and tested

**Deliverable:** Published PyPI packages. Multi-platform wheels. Full documentation. Ready for launch.

---

## Testing Strategy

- **Unit tests**: In `check_engine/tests/` with fixture files. Every rule ID has positive and negative tests.
- **Integration tests**: End-to-end with real project fixtures (ironlayer_project with intentional errors, dbt_project, empty_project).
- **Python integration tests**: Test PyO3 bridge from Python (`quick_check()`, `CheckEngine(config).check()`).
- **Benchmark tests**: Criterion benchmarks for 100/500/1000 model projects, cold and warm.
- **Round-trip tests**: Config load → serialize → load produces identical config. Cache write → read produces identical entries.

---

## BUILD EXECUTION INSTRUCTIONS

1. **Create a TodoWrite list** breaking the phase into specific tasks
2. **Build incrementally** — compile and test after each major component
3. **Run `cargo clippy --workspace -- -D warnings`** after each component
4. **Run `cargo fmt --all`** before moving on
5. **Write tests alongside implementation** — not after
6. **Verify PyO3 bindings work** — `python -c "from ironlayer_check_engine import CheckEngine"` must succeed
7. **Verify the phase deliverable works end-to-end** before declaring the phase complete
8. **Do NOT proceed to the next phase** — run the check-audit first

Begin building Phase $ARGUMENTS now. Start with the TodoWrite list, then implement systematically.

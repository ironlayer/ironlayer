# IronLayer — Claude Code Operating Instructions

## Project Overview

IronLayer is an AI-native Databricks transformation control plane. This is the public OSS repo (`ironlayer/ironlayer`) containing the core engine, CLI, API, and AI engine packages.

### Repository Structure

- **Workspace members:** `core_engine`, `cli`, `api`, `ai_engine` (Python, managed by `uv`)
- **Build system:** hatchling (Python packages), maturin (Rust extension — check engine only)
- **Python:** >=3.11, <3.13
- **Code quality:** ruff, mypy, pytest (90%+ coverage targets for CLI and API)

### Key Architecture Patterns

- **Protocol-based SQL toolkit:** All sqlglot imports isolated in `sqlglot_impl.py`, consumers use protocols only
- **Model files use `-- key: value` comment headers** (NOT YAML `---` delimiters)
- **Dual canonicalization:** V1 (stable hashes), V2 (opt-in with schema, qualify+simplify)
- **MCP server:** stdio (Claude Code/Cursor) + SSE transport, default bind 127.0.0.1

### Existing CLI Patterns (check command MUST follow these)

The CLI lives at `cli/cli/app.py` (~2200 lines). The `check` command is added as a new `@app.command()`.

**Key patterns the check command must replicate exactly:**
- `app = typer.Typer(...)` — commands register via `@app.command()`
- `console = Console(stderr=True)` — all Rich output to stderr, JSON to stdout
- `_json_output`, `_metrics_file`, `_env` globals set by `_global_options()` callback
- `_emit_metrics(event: str, data: dict[str, Any])` — telemetry emission
- `_load_stored_token() -> str | None` — cloud upsell check
- `models_dir = repo / "models"; if not models_dir.is_dir(): models_dir = repo` — directory resolution
- `raise typer.Exit(code=N)` — exit codes 0/1/3

**Existing commands:** `plan`, `show`, `apply`, `backfill`, `backfill-chunked`, `backfill-resume`, `backfill-history`, `models`, `lineage`, `login`, `logout`, `whoami`, `init`, `dev`, `migrate` (from-dbt, from-sql, from-sqlmesh), `mcp` (serve).

**Display functions** live at `cli/cli/display.py` — `display_check_results()` is added alongside existing `display_plan_summary()`, `display_model_list()`, `display_lineage()`, etc. All take `console: Console` as first param.

### Code Quality Standards

- "The hard way is better if it's right" — no shortcuts, no happy-path-only code
- Verify subagent work thoroughly
- Test coverage targets: CLI 90%+, API 90%+

---

# IronLayer Check Engine — Build Instructions

You are building the **IronLayer Check Engine**, a Rust-powered `ironlayer check` subcommand that validates SQL models, YAML schemas, naming conventions, ref() integrity, and dbt project structure in under 1 second for 500+ model projects. The Rust engine compiles into a native Python extension via PyO3/maturin, bundled inside the existing `ironlayer-core` wheel.

> **Codebase integration note:** The spec (`ironlayer_check_engine_spec.md`) uses the directory name `ironlayer-core/` in its layout diagrams. In the actual repo, this directory is called **`core_engine/`** (the PyPI package name is `ironlayer-core`, but the on-disk directory is `core_engine/`). The current build system is **hatchling** (not poetry-core) — the maturin migration replaces hatchling, not poetry-core. Wherever the spec says `ironlayer-core/`, read `core_engine/`.

## Read Before Every Session

Before writing ANY code, determine which phase you're working on and read the relevant context:

1. **Always read first:** `ironlayer_check_engine_spec.md` — the single source of truth for the entire implementation
2. **Read for builds:** Use the `check-build` skill with the phase number
3. **Read for audits:** Use the `check-audit` skill with the phase number
4. **Read when touching PyO3:** Spec §9 (PyO3 Bindings) — Python module surface, type stubs, build integration
5. **Read when touching checkers:** Spec §5 (Check Rules Specification) — every rule ID, severity, description, fixability
6. **Read when touching config:** Spec §6 (Configuration Format) — TOML schema, resolution order, per-path overrides
7. **Read when touching CLI:** Spec §7 (CLI Integration) — Typer patterns, exit codes, display formatting

## Project Identity

- **Rust crate name:** `ironlayer-check-engine`
- **Python module name:** `ironlayer_check_engine`
- **Bundled inside:** `ironlayer-core` v0.3.0 wheel (existing Python package)
- **CLI entry point:** `ironlayer check` (added to existing `ironlayer` CLI via Typer)
- **Rust edition:** 2021
- **MSRV:** 1.75.0
- **Python compatibility:** 3.11, 3.12
- **ABI:** `abi3-py311` (stable ABI, single wheel per platform)
- **Build tool:** maturin (latest stable 1.x)
- **License:** Apache-2.0

## Production-Grade Code Philosophy

This engine must be fast, correct, and production-real. Every line of Rust must be fully implemented. Every checker must handle all variants. Every diagnostic must be actionable.

### The Cardinal Rules

1. **Never stub, placeholder, or `todo!()`.** If a function exists, it must be fully implemented. If a checker exists, every rule ID it covers must fire correctly.

2. **Always build the complete solution.** If `HDR001-HDR013` is spec'd, implement all 13 rules. If `TokenKind` has 19 variants, handle all 19 in the lexer. Never leave `_ => Vec::new()` catch-alls on enums.

3. **Never simplify for convenience.** Don't use `.unwrap()` in library code. Don't skip cache invalidation edge cases. Don't hardcode what should be configurable. Don't return empty diagnostics from a checker that has rules to enforce.

4. **Never leave comments that describe missing work.** No `// TODO`, no `// FIXME`, no `// handle remaining rules`, no `// similar pattern for the rest`. If you identify work that needs doing, do it.

5. **Build for the actual scale.** This engine must check 500+ models in <500ms. Every function must handle: empty projects, massive projects (1000+ files), deeply nested directories, Unicode filenames, files with no headers, files with only comments.

6. **Prefer explicit over implicit.** Explicit error types via `thiserror`. Explicit variant handling in every `match`. Explicit doc comments on every public item. Explicit test for every rule ID.

7. **Every diagnostic earns its existence.** If a `CheckDiagnostic` is constructed, it must have a specific `rule_id`, an actionable `message`, the correct `severity`, and a `suggestion` when one is feasible.

### Anti-Patterns — NEVER Do These

```rust
// ❌ NEVER: Stub implementations
fn check_project(&self, _models: &[DiscoveredModel], _config: &CheckConfig) -> Vec<CheckDiagnostic> {
    Vec::new() // placeholder
}

// ❌ NEVER: Catch-all match arms discarding variants
match model_kind {
    "FULL_REFRESH" => { /* validate */ },
    "INCREMENTAL_BY_TIME_RANGE" => { /* validate */ },
    _ => Ok(()),  // Silently ignores APPEND_ONLY and MERGE_BY_KEY

// ❌ NEVER: Partial rule implementation
// Implements HDR001-HDR003, "rest follow the same pattern"

// ❌ NEVER: Simplified algorithm
fn levenshtein(a: &str, b: &str) -> usize {
    if a == b { 0 } else { 1 }
}

// ❌ NEVER: unwrap in library code
let content = std::fs::read_to_string(path).unwrap();

// ❌ NEVER: Generic diagnostic messages
CheckDiagnostic { message: "Invalid SQL".into(), .. }

// ❌ NEVER: Hardcoded config
let max_diagnostics = 200; // Should come from CheckConfig
```

```rust
// ✅ ALWAYS: Complete implementation with all variants
match kind_str {
    "FULL_REFRESH" => {
        // No additional required fields
    }
    "INCREMENTAL_BY_TIME_RANGE" => {
        if !header.contains_key("time_column") {
            diags.push(CheckDiagnostic {
                rule_id: "HDR005".into(),
                message: "kind: INCREMENTAL_BY_TIME_RANGE requires 'time_column' header field. \
                          Add '-- time_column: <column_name>' to the header.".into(),
                severity: Severity::Error,
                category: CheckCategory::SqlHeader,
                file_path: file_path.into(),
                line: kind_line,
                column: 0,
                snippet: Some(format!("-- kind: {}", kind_str)),
                suggestion: Some("Add '-- time_column: created_at' (or your timestamp column)".into()),
                doc_url: Some("https://docs.ironlayer.app/check/rules/HDR005".into()),
            });
        }
    }
    "APPEND_ONLY" => {
        // No additional required fields
    }
    "MERGE_BY_KEY" => {
        if !header.contains_key("unique_key") {
            diags.push(CheckDiagnostic {
                rule_id: "HDR006".into(),
                message: "kind: MERGE_BY_KEY requires 'unique_key' header field. \
                          Add '-- unique_key: <column_name>' to the header.".into(),
                severity: Severity::Error,
                // ... full diagnostic construction
            });
        }
    }
    other => {
        diags.push(CheckDiagnostic {
            rule_id: "HDR003".into(),
            message: format!(
                "Invalid kind value '{}'. Must be one of: FULL_REFRESH, \
                 INCREMENTAL_BY_TIME_RANGE, APPEND_ONLY, MERGE_BY_KEY.",
                other
            ),
            // ... full diagnostic construction
        });
    }
}
```

## Rust ↔ Python Boundary

**Rust owns the hot path:** File I/O, SQL lexing, header parsing, ref extraction, parallel validation, caching, content hashing.

**Python keeps the complex path:** Full AST analysis (SQLGlot), DAG building (NetworkX), plan generation, schema introspection, Rich console formatting.

**The handoff:** Rust's `CheckEngine` is called from Python via PyO3. It returns a `CheckResult` struct that Python formats for display or serializes to JSON.

```
ironlayer CLI (Python/Typer)
    → from ironlayer_check_engine import CheckEngine
    → engine = CheckEngine(config)
    → result = engine.check(str(repo))    # FFI boundary
    → display_check_results(console, result)  # Back in Python
```

**Never rebuild what Python already does:**
- ❌ Don't build a full SQL parser — use the lightweight lexer for token-based checks
- ❌ Don't build column resolution — that's SQLGlot's job via `sql_toolkit`
- ❌ Don't build DAG analysis — that's NetworkX's job
- ❌ Don't build Rich output formatting — that stays in `cli/cli/display.py`
- ✅ DO build: file discovery, content hashing, header parsing, ref extraction, safety pre-screening, naming validation, YAML schema validation, parallel orchestration, caching

## Existing IronLayer Integration Points — MUST MATCH

**Source file locations (verified against codebase):**

| Existing Component | Source File | What Check Engine Uses | How |
|---|---|---|---|
| `ref_resolver._REF_PATTERN` | `core_engine/core_engine/loader/ref_resolver.py` | Exact regex: `r"\{\{\s*ref\s*\(\s*(?:'([^']+)'\|\"([^\"]+)\")\s*\)\s*\}\}"` | Rust re-implements via `regex` crate |
| `model_loader._REQUIRED_FIELDS` | `core_engine/core_engine/loader/model_loader.py` | `frozenset({"name", "kind"})` | Rust header parser enforces same set |
| `model_loader._KNOWN_FIELDS` | `core_engine/core_engine/loader/model_loader.py` | 13 fields: name, kind, materialization, time_column, unique_key, partition_by, incremental_strategy, owner, tags, dependencies, contract_mode, contract_columns, tests | Rust parser validates against same set |
| `sql_guard.DangerousOperation` | `core_engine/core_engine/parser/sql_guard.py` | 11 variants (DROP_TABLE, DROP_VIEW, DROP_SCHEMA, TRUNCATE, DELETE_WITHOUT_WHERE, ALTER_DROP_COLUMN, GRANT, REVOKE, CREATE_USER, RAW_EXEC, INSERT_OVERWRITE_ALL) | Rust SAF rules mirror these |
| `sql_guard.Severity` | `core_engine/core_engine/parser/sql_guard.py` | CRITICAL/HIGH/MEDIUM + `_DEFAULT_SEVERITY` mapping | Maps to Rust Severity enum |
| `sql_toolkit.Dialect` | `core_engine/core_engine/sql_toolkit/_types.py` | 3 variants: DATABRICKS="databricks", DUCKDB="duckdb", REDSHIFT="redshift" | Rust enum serializes lowercase |
| `schema_validator.ViolationSeverity` | `core_engine/core_engine/contracts/schema_validator.py` | BREAKING/WARNING/INFO | Mapped to Rust Severity enum |
| `ModelKind` | `core_engine/core_engine/models/model_definition.py` | FULL_REFRESH, INCREMENTAL_BY_TIME_RANGE, APPEND_ONLY, MERGE_BY_KEY | Rust validates kind-specific required fields |
| `Materialization` | `core_engine/core_engine/models/model_definition.py` | TABLE, VIEW, MERGE, INSERT_OVERWRITE | Rust validates materialization compatibility |
| `SchemaContractMode` | `core_engine/core_engine/models/model_definition.py` | DISABLED, WARN, STRICT | Rust respects per-model setting |
| CLI globals | `cli/cli/app.py` | `_json_output`, `_metrics_file`, `_env` (set in `_global_options()` callback) | Check command uses same globals |
| `console` | `cli/cli/app.py:43` | `Console(stderr=True)` — all Rich output goes to stderr | Check display uses same console |
| `_emit_metrics()` | `cli/cli/app.py:109` | `_emit_metrics(event: str, data: dict[str, Any])` | Check command emits same pattern |
| `_load_stored_token()` | `cli/cli/app.py:145` | Returns `str \| None` from `~/.ironlayer/credentials.json` | Cloud upsell check |
| CLI exit codes | `cli/cli/app.py` | `raise typer.Exit(code=N)` — 0=success, 1=failures, 3=internal error | Check command uses same codes |
| `display_*` functions | `cli/cli/display.py` | `display_check_results()` added alongside existing `display_plan_summary()`, `display_model_list()`, etc. | Same `console: Console` first-param pattern |

## The 4 Phases

| Phase | Name | Duration | Key Deliverable |
|-------|------|----------|-----------------|
| 1 | Foundation | Week 1-2 | Rust crate builds, PyO3 works, HDR001-HDR013, sequential orchestrator |
| 2 | Core Checkers | Week 3-4 | SQL lexer, SQL/SAF/REF/NAME rules, rayon parallelism, cache, benchmarks |
| 3 | YAML & dbt | Week 5-6 | YML/DBT/CON rules, SARIF, git integration, --fix, Python fallback |
| 4 | Polish & Launch | Week 7-8 | Multi-platform wheels, type stubs, docs, MCP tool, PyPI release |

## Rule ID Registry (66 total)

| Category | Prefix | Count | Phase |
|----------|--------|-------|-------|
| SQL Header | HDR | 13 | 1 |
| SQL Syntax | SQL | 9 | 2 |
| SQL Safety | SAF | 10 | 2 |
| Ref Resolution | REF | 6 | 2 |
| Naming Convention | NAME | 8 | 2 |
| YAML Schema | YML | 9 | 3 |
| dbt Project | DBT | 6 | 3 |
| Model Consistency | CON | 5 | 3 |

Rule IDs are permanent — once assigned, never reused or reassigned.

## Tech Stack (Non-Negotiable)

| Component | Tool | Why |
|-----------|------|-----|
| Build system | maturin 1.x | PyO3 Python extension packaging |
| Parallelism | rayon | Data parallelism for file checking |
| Serialization | serde + serde_json + serde_yaml | Config and output serialization |
| Regex | regex crate | ref pattern matching, naming patterns |
| File walking | ignore crate | .gitignore-aware (same as ripgrep) |
| Hashing | sha2 | Content-addressable cache |
| Error types | thiserror | Structured errors |
| Logging | log + pyo3-log | Bridge to Python logging |
| Glob matching | globset | Per-path config overrides |
| Benchmarks | criterion | Performance regression detection |
| Test fixtures | indoc + tempfile | Inline SQL fixtures, temp directories |

## File Size Guidelines

- **Max 500 lines per `.rs` file** — split into submodules if larger
- **Max 50 lines per function** — extract helpers
- **Checkers**: One file per checker, one checker per category (sql_header.rs handles all HDR rules)

## Workspace Layout

```
ironlayer/
├── Cargo.toml                          # Workspace root: members = ["check_engine"]
├── check_engine/
│   ├── Cargo.toml                      # Crate config: cdylib + rlib
│   ├── src/
│   │   ├── lib.rs                      # PyO3 module entry
│   │   ├── engine.rs                   # CheckEngine orchestrator
│   │   ├── config.rs                   # CheckConfig + TOML loading
│   │   ├── discovery.rs                # File walker + project type detection
│   │   ├── cache.rs                    # SHA-256 content cache
│   │   ├── sql_lexer.rs                # Token stream (19 token kinds)
│   │   ├── types.rs                    # CheckResult, CheckDiagnostic, enums
│   │   ├── reporter.rs                 # JSON + SARIF output
│   │   ├── pyo3_bindings.rs            # PyO3 exports
│   │   └── checkers/
│   │       ├── mod.rs                  # Checker trait + registry
│   │       ├── sql_header.rs           # HDR001-HDR013
│   │       ├── sql_syntax.rs           # SQL001-SQL009
│   │       ├── sql_safety.rs           # SAF001-SAF010
│   │       ├── ref_resolver.rs         # REF001-REF006
│   │       ├── yaml_schema.rs          # YML001-YML009
│   │       ├── naming.rs              # NAME001-NAME008
│   │       ├── dbt_project.rs          # DBT001-DBT006
│   │       └── model_consistency.rs    # CON001-CON005
│   ├── tests/
│   │   ├── fixtures/
│   │   ├── test_sql_header.rs
│   │   ├── test_sql_lexer.rs
│   │   ├── test_ref_resolver.rs
│   │   ├── test_naming.rs
│   │   ├── test_yaml_schema.rs
│   │   └── test_integration.rs
│   └── benches/
│       └── check_benchmark.rs
├── core_engine/                        # Existing Python package (pyproject.toml MODIFIED for maturin)
│   ├── core_engine/                    # Python source — UNCHANGED
│   └── pyproject.toml                  # MODIFIED: hatchling → maturin build-backend
└── .cargo/config.toml                  # Cross-compilation settings
```

## Testing Commands

```bash
# Build the workspace
cargo build --workspace

# Run all Rust tests
cargo test --workspace

# Run specific checker tests
cargo test --workspace -- sql_header
cargo test --workspace -- ref_resolver
cargo test --workspace -- sql_lexer
cargo test --workspace -- naming

# Clippy (must be clean)
cargo clippy --workspace -- -D warnings

# Format check
cargo fmt --all -- --check

# Benchmarks
cargo bench --bench check_benchmark

# PyO3 smoke test (after maturin build)
python -c "from ironlayer_check_engine import CheckEngine, quick_check; print('OK')"

# Python integration tests
pytest tests/test_check_engine.py -v

# Full maturin build
cd core_engine && maturin build --release
```

## Phase Completion Checklist

Before marking ANY phase complete, run the `check-audit` skill:

```bash
# 1. No forbidden patterns
grep -rn "todo!\|unimplemented!\|FIXME\|HACK\|XXX\|PLACEHOLDER" check_engine/src/
# Must return zero results

# 2. No unjustified unwrap in library code
grep -rn "\.unwrap()" check_engine/src/ | grep -v "#\[cfg(test)\]" | grep -v "\.expect("
# Must return zero results

# 3. Clippy clean
cargo clippy --workspace -- -D warnings

# 4. All tests pass
cargo test --workspace

# 5. Formatted
cargo fmt --all -- --check

# 6. PyO3 imports work
python -c "from ironlayer_check_engine import CheckEngine, CheckConfig, CheckResult, Severity, CheckCategory, Dialect, quick_check"

# 7. Rule ID count matches phase requirement
grep -roh '"[A-Z]\{2,4\}[0-9]\{3\}"' check_engine/src/checkers/ | sort -u | wc -l
# Phase 1: >= 13, Phase 2: >= 46, Phase 3: >= 66, Phase 4: >= 66
```

## Performance Targets

| Scenario | Target | Strategy |
|---|---|---|
| 100 models cold | < 200ms | rayon parallelism |
| 500 models cold | < 500ms | rayon + zero-copy lexer |
| 500 models warm | < 50ms | SHA-256 content cache |
| 1000 models cold | < 1s | Early termination at max_diagnostics |
| Single file | < 20ms | Cache hit path |

## What Phase Am I In?

Check which modules exist in `check_engine/src/` to determine current progress:
- Phase 1: `types.rs`, `config.rs`, `discovery.rs`, `cache.rs`, `engine.rs`, `checkers/sql_header.rs`, `pyo3_bindings.rs`, `lib.rs`
- Phase 2: + `sql_lexer.rs`, `checkers/sql_syntax.rs`, `checkers/sql_safety.rs`, `checkers/ref_resolver.rs`, `checkers/naming.rs`, `reporter.rs`
- Phase 3: + `checkers/yaml_schema.rs`, `checkers/dbt_project.rs`, `checkers/model_consistency.rs`
- Phase 4: All files present + type stubs, CI/CD, documentation

If unsure, ask the user which phase to work on.

## Critical Implementation Behaviors (from spec updates)

### Header Parser Termination (§5.1)
The header block does NOT end on blank lines or bare `--` comments. Only the first line that is **both non-empty AND not a comment** terminates it. This matches `model_loader.parse_yaml_header()`.

### Disabled-by-Default Rules
These rules are intentionally disabled. Never enable them by default:
- **HDR007** — preserves forward-compatible header extensions per `model_loader.py` design
- **CON004** — terminal mart models are legitimate leaf nodes (consumed by BI tools, not other models)

### Panic Recovery (Appendix D.1)
Every per-file check dispatch in `engine.rs` MUST be wrapped in `catch_unwind`. A panic in one checker emits an `INTERNAL` diagnostic instead of crashing the Python process. Cross-file `check_project()` calls are also wrapped.

### Windows Paths (Appendix D.2)
All `file_path` values use **forward slashes** regardless of platform. Cache keys also use forward slashes for cross-platform portability.

### Cache Concurrency (§11.3)
Atomic writes via temp file + rename. Last-writer-wins (no locking). Corrupt cache → log warning, delete, rebuild.

### YML006 GIL (§5.5)
YML006 calls Python via `Python::with_gil()` for column extraction. Runs in sequential `check_project()` phase only. Gracefully degrades if `core_engine` is unavailable.

## Expanded Rule Categories (Post-Phase 4)

Beyond the original 66 rules, the check engine now includes 4 additional categories
targeting Databricks-specific validation, incremental model logic, performance
anti-patterns, and test adequacy. These are **additive** — they don't modify any
existing rule IDs or checker behavior.

| Category | Prefix | Count | Checker File |
|----------|--------|-------|-------------|
| Databricks SQL | DBK | 7 | `checkers/databricks_sql.rs` |
| Incremental Logic | INC | 5 | `checkers/incremental_logic.rs` |
| Performance | PERF | 7 | `checkers/performance.rs` |
| Test Adequacy | TST | 5 | `checkers/test_adequacy.rs` |

**Total rules: 90** (66 original + 24 new)

### DBK Rules (Databricks SQL)

| Rule | Description | Default Severity | Default Enabled |
|------|-------------|-----------------|-----------------|
| DBK001 | Hardcoded catalog/schema in table references (use ref() or config) | Warning | yes |
| DBK002 | Non-deterministic MERGE (MERGE INTO without deterministic match) | Error | yes |
| DBK003 | OPTIMIZE/VACUUM in model SQL (should be maintenance ops) | Error | yes |
| DBK004 | COPY INTO in model SQL (should be ingestion, not transformation) | Warning | yes |
| DBK005 | Dialect-incompatible function (ISNULL, DATEADD SQL Server syntax, TOP) | Warning | yes |
| DBK006 | CREATE OR REPLACE in incremental model (defeats incrementality) | Warning | yes |
| DBK007 | Non-standard MERGE syntax (missing MATCHED clauses) | Warning | yes |

### INC Rules (Incremental Logic)

| Rule | Description | Default Severity | Default Enabled |
|------|-------------|-----------------|-----------------|
| INC001 | INCREMENTAL_BY_TIME_RANGE model doesn't reference time_column in WHERE | Error | yes |
| INC002 | MERGE_BY_KEY model doesn't reference unique_key in SQL body | Error | yes |
| INC003 | Incremental model with no WHERE clause | Warning | yes |
| INC004 | time_column referenced in SELECT but not in WHERE filter | Warning | yes |
| INC005 | MERGE_BY_KEY with incompatible materialization | Warning | yes |

### PERF Rules (Performance Anti-Patterns)

| Rule | Description | Default Severity | Default Enabled |
|------|-------------|-----------------|-----------------|
| PERF001 | CROSS JOIN detected (potential cartesian product) | Warning | yes |
| PERF002 | ORDER BY in subquery or CTE (unnecessary sorting) | Warning | yes |
| PERF003 | NOT IN with subquery (prefer NOT EXISTS) | Info | yes |
| PERF004 | SELECT * usage (prefer explicit columns) | Info | yes |
| PERF005 | Correlated subquery in SELECT list (potential N+1) | Warning | yes |
| PERF006 | DISTINCT on entire SELECT (may indicate join issue) | Info | yes |
| PERF007 | UNION instead of UNION ALL (unnecessary dedup overhead) | Info | yes |

### TST Rules (Test Adequacy)

| Rule | Description | Default Severity | Default Enabled |
|------|-------------|-----------------|-----------------|
| TST001 | Model with unique_key but no unique() test declared | Warning | yes |
| TST002 | Model with unique_key but no not_null() test on key column | Warning | yes |
| TST003 | Incremental model with no row_count test | Info | yes |
| TST004 | Model with contract_mode STRICT but zero tests declared | Warning | yes |
| TST005 | Model with no tests declared at all | Info | no |

**Design rules for new categories:**
- New rule prefixes are 3-4 uppercase letters (DBK, INC, PERF, TST) — never conflicts with existing 2-3 letter prefixes (HDR, SQL, SAF, REF, NAME, YML, DBT, CON)
- New `CheckCategory` enum variants are additive — never modify existing variant names or serialized values
- New checkers registered at the end of `build_checker_registry()` vector — order doesn't affect correctness
- TST005 is disabled by default (some projects legitimately have models without tests)

## Lessons Learned (Implementation Notes)

### Non-Deterministic HashMap Serialization
Rust's `HashMap` iteration order varies between process runs. Using `serde_json::to_string()` on structs containing `HashMap` fields produces different JSON on each run, causing cache invalidation. **Fix:** Implement `canonical_json()` that recursively sorts object keys before serialization. This is used in `config_hash()` for cache key computation.

### `ignore` Crate Walk Overhead
The `ignore` crate (same as ripgrep) provides .gitignore-aware file walking but is expensive (~200ms for 500 files). On warm cache runs where we only need to verify file existence/mtime, bypass the walker and use `stat_known_files()` which directly `stat()` only the cached paths.

### Stat-Based Cache Fast Path
The mtime + size fast-path check (`is_fast_cached()`) is ~1000x cheaper than read + SHA-256. When all files are cache hits, we can early-return from `check()` without reading any file content, building the model registry, or running cross-file checks. This brings warm cache from ~218ms to ~52ms for 500 models.

### O(n²) Partition Trap
When partitioning files into cached vs uncached sets, using `.iter().any()` inside a loop creates O(n²) behavior. Use a `HashSet` for O(1) lookups. This matters at 500+ files.

### Cache Entry Completeness
Cache entries must store not just content_hash but also file_size, mtime_secs, per-file diagnostics, and model metadata (CachedModel). This enables both the mtime fast-path and replaying cached diagnostics/model data for cross-file checks without re-reading files.

## Key Spec References (by section)

> **Reminder:** The spec says `ironlayer-core/` — the actual directory is `core_engine/`. The spec says `poetry-core` — the actual build system is `hatchling`.

| Topic | Spec Section |
|-------|-------------|
| Architecture diagram | §3.1 |
| Rust vs Python ownership | §3.2 |
| Cargo.toml dependencies | §4.2 |
| Core types (Rust structs) | §4.3 |
| Checker trait | §4.4 |
| Engine orchestrator | §4.5 |
| All rule IDs + descriptions | §5.1 – §5.8 |
| Config TOML schema | §6.2 |
| Config Rust struct | §6.3 |
| CLI command signature | §7.1 |
| Display function | §7.2 |
| Exit code contract | §7.3 |
| --fix mechanics (5-step workflow) | §7.4 |
| JSON output format | §8.2 |
| SARIF output + field mapping | §8.3 |
| PyO3 module definition | §9.1 |
| Python API surface | §9.2 |
| maturin build config | §9.3 |
| Project type detection | §10.1 |
| File walking + .ironlayerignore | §10.2 |
| --changed-only mode | §10.3 |
| Performance targets | §11.1 |
| Cache format + concurrency | §11.3 |
| SQL lexer token types | Appendix A |
| Compatibility matrix | Appendix B |
| Glossary | Appendix C |
| Panic recovery (catch_unwind) | Appendix D.1 |
| Windows path normalization | Appendix D.2 |
| Unicode/UTF-8 handling | Appendix D.3 |

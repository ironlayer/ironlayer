# IronLayer Check Engine — Complete Technical Specification

**Version:** 1.1.0
**Date:** 2026-02-28
**Status:** Ready for Implementation (Audited)
**Target Package:** `ironlayer-core` v0.3.0 (Rust extension), `ironlayer` v0.3.0 (CLI integration)
**Implementation Tool:** Claude Code

---

## Table of Contents

1. [Executive Summary](#1-executive-summary)
2. [Existing Codebase Integration Map](#2-existing-codebase-integration-map)
3. [Architecture & Build System](#3-architecture--build-system)
4. [Rust Crate Structure](#4-rust-crate-structure)
5. [Check Rules Specification](#5-check-rules-specification)
6. [Configuration Format](#6-configuration-format)
7. [CLI Integration](#7-cli-integration)
8. [Output Format](#8-output-format)
9. [PyO3 Bindings](#9-pyo3-bindings)
10. [File Discovery & Git Integration](#10-file-discovery--git-integration)
11. [Performance Requirements](#11-performance-requirements)
12. [Error Taxonomy](#12-error-taxonomy)
13. [Testing Strategy](#13-testing-strategy)
14. [Packaging & Distribution](#14-packaging--distribution)
15. [Migration Path from Existing Tools](#15-migration-path-from-existing-tools)
16. [Future: IronLayer Cloud Integration](#16-future-ironlayer-cloud-integration)
17. [Implementation Phases](#17-implementation-phases)

---

## 1. Executive Summary

### What We're Building

A Rust-powered `ironlayer check` subcommand that validates SQL models, YAML schemas, naming conventions, ref() integrity, and dbt project structure in under 1 second for projects with 500+ models. The Rust engine is compiled into a native Python extension via PyO3/maturin, bundled inside the existing `ironlayer-core` wheel. Zero additional install steps for users.

### Why It Matters

- **Current state:** Data engineers have no unified fast pre-commit validation tool. SQLFluff (Python) takes 47s+ for 500 models. pre-commit (Python) spawns separate processes per hook.
- **After this:** `ironlayer check .` validates everything in parallel in <1s. It becomes the viral entry point that drives discovery of IronLayer's plan/apply/lineage capabilities.

### Design Principles

1. **Zero-config useful, infinitely configurable.** Running `ironlayer check .` with no config file must produce useful results by auto-detecting project type (IronLayer native, dbt, or raw SQL).
2. **Existing IronLayer data models are the source of truth.** The Rust engine must produce output compatible with `ModelDefinition`, `SQLGuardViolation`, `ContractViolation`, and other existing Pydantic models.
3. **Never duplicate what Python already does well.** The Rust engine handles the hot path (file I/O, SQL lexing/parsing, parallel validation, caching). Complex operations (full AST analysis via SQLGlot, DAG building via NetworkX, plan generation) stay in Python.
4. **Content-addressable caching.** Skip files whose SHA-256 content hash hasn't changed since last check.

---

## 2. Existing Codebase Integration Map

This section maps every touchpoint between the new Rust check engine and the existing IronLayer Python codebase. Every reference here was verified against the installed `ironlayer==0.2.0` and `ironlayer-core==0.2.0` packages.

### 2.1 Package Structure (Current)

```
ironlayer (v0.2.0) — CLI package
├── cli/
│   ├── __main__.py          → entry point: main()
│   ├── app.py               → Typer app, 14 top-level commands + 4 subcommands
│   │                           Top-level: plan, show, apply, backfill, backfill-chunked,
│   │                           backfill-resume, backfill-history, models, lineage,
│   │                           login, logout, whoami, init, dev
│   │                           Subcommands: migrate (from-dbt, from-sql, from-sqlmesh), mcp (serve)
│   ├── display.py           → Rich console formatters
│   ├── cloud.py             → Cloud auth helpers
│   ├── commands/
│   │   ├── init.py          → ironlayer init
│   │   └── dev.py           → ironlayer dev
│   ├── mcp/
│   │   ├── server.py        → MCP server
│   │   └── tools.py         → MCP tool definitions
│   └── templates/
│       ├── config.yaml.j2
│       ├── env.j2
│       └── gitignore.j2
└── entry_points.txt         → ironlayer=cli.__main__:main

ironlayer-core (v0.2.0) — Engine package
├── core_engine/
│   ├── config.py            → Settings (Pydantic, PLATFORM_ prefix)
│   ├── models/
│   │   ├── model_definition.py  → ModelDefinition, ModelKind, Materialization,
│   │   │                           SchemaContractMode, ColumnContract, ModelTestDefinition
│   │   ├── plan.py              → ExecutionPlan, PlanStep, PlanSummary
│   │   ├── diff.py              → DiffResult, DiffEntry
│   │   ├── run.py               → RunResult, StepResult
│   │   ├── snapshot.py          → ModelSnapshot
│   │   └── telemetry.py         → TelemetryEvent
│   ├── parser/
│   │   ├── ast_parser.py        → parse_sql(), ModelASTMetadata
│   │   ├── normalizer.py        → canonicalize_sql(), CanonicalizerVersion
│   │   └── sql_guard.py         → check_sql_safety(), SQLGuardViolation, SQLGuardConfig
│   ├── loader/
│   │   ├── model_loader.py      → load_models_from_directory(), parse -- headers
│   │   ├── ref_resolver.py      → resolve_refs(), extract_ref_names(), _REF_PATTERN
│   │   ├── dbt_loader.py        → load_models_from_dbt_manifest()
│   │   └── sqlmesh_loader.py    → load_models_from_sqlmesh()
│   ├── contracts/
│   │   └── schema_validator.py  → validate_contracts(), ContractViolation, ViolationSeverity
│   ├── graph/
│   │   ├── dag_builder.py       → build_dag() (NetworkX)
│   │   └── column_lineage.py    → trace_column_lineage()
│   ├── diff/
│   │   ├── ast_diff.py          → compute_ast_diff()
│   │   └── structural_diff.py   → compute_structural_diff()
│   ├── executor/                → Databricks + DuckDB execution backends
│   ├── planner/                 → Interval planner + plan serializer
│   ├── sql_toolkit/             → Protocol-based SQL parsing abstraction
│   │   ├── _protocols.py        → SqlParser, SqlRenderer, SqlScopeAnalyzer, etc.
│   │   ├── _types.py            → Dialect (DATABRICKS|DUCKDB|REDSHIFT), TableRef, SqlNode
│   │   └── impl/sqlglot_impl.py → ~2K LOC (67KB) SQLGlot implementation
│   ├── state/                   → Alembic migrations (24 versions), repository.py (155K)
│   ├── testing/                 → test_runner.py
│   ├── telemetry/               → collector, emitter, profiling, spark_metrics
│   ├── simulation/              → impact_analyzer.py
│   ├── license/                 → keygen, feature_flags, license_manager
│   ├── metering/                → collector, events
│   └── benchmarks/              → graph_generator, profiler
```

### 2.2 Critical Integration Points

| Existing Component | What Check Engine Uses | How |
|---|---|---|
| `ModelDefinition` (Pydantic model) | Field names, enum values, validation rules | Rust structs mirror these exactly; PyO3 converts to/from Python objects |
| `ref_resolver._REF_PATTERN` | Regex `\{\{\s*ref\s*\(\s*(?:'([^']+)'\|"([^"]+)")\s*\)\s*\}\}` | Rust re-implements this exact regex via the `regex` crate |
| `model_loader._REQUIRED_FIELDS` | `{"name", "kind"}` | Rust header parser enforces these same required fields |
| `model_loader._KNOWN_FIELDS` | 13 known header fields | Rust parser validates against this same set |
| `sql_guard.DangerousOperation` | 11 dangerous operations enum | Rust check mirrors these for fast pre-screening |
| `sql_toolkit.Dialect` | `DATABRICKS`, `DUCKDB`, `REDSHIFT` | Rust enum with same variants |
| `sql_guard.Severity` | `CRITICAL`, `HIGH`, `MEDIUM` | Mapped to check engine: CRITICAL→Error, HIGH→Warning, MEDIUM→Warning |
| `schema_validator.ViolationSeverity` | `BREAKING`, `WARNING`, `INFO` | Mapped to check engine: BREAKING→Error, WARNING→Warning, INFO→Info |
| `SchemaContractMode` | `DISABLED`, `WARN`, `STRICT` | Rust respects this per-model setting |
| `ModelKind` | `FULL_REFRESH`, `INCREMENTAL_BY_TIME_RANGE`, `APPEND_ONLY`, `MERGE_BY_KEY` | Rust validates kind-specific required fields |
| `Materialization` | `TABLE`, `VIEW`, `MERGE`, `INSERT_OVERWRITE` | Rust validates materialization compatibility |
| `config.Settings` | `PLATFORM_` env prefix, `.env` file loading | Rust reads same env vars for config |
| CLI `--json/--no-json` flag | Global option on all commands | Check command respects this existing pattern |
| CLI `--env` flag | `dev`, `staging`, `prod` | Check rules can vary by environment |

### 2.3 Existing Patterns the Check Command MUST Follow

These patterns are established in `cli/app.py` and must be replicated exactly:

```python
# Pattern 1: Typer command with repo path argument
@app.command()
def check(
    repo: Path = typer.Argument(
        ...,
        help="Path to the repository containing SQL models.",
        exists=True,
        file_okay=False,
        resolve_path=True,
    ),
    # ... more options
) -> None:

# Pattern 2: Model directory resolution (from models command, line 1127)
models_dir = repo / "models"
if not models_dir.is_dir():
    models_dir = repo  # Fall back to repo root

# Pattern 3: JSON output mode (from models command, line 1143)
if _json_output:
    sys.stdout.write(json.dumps(result, indent=2) + "\n")
else:
    display_check_results(console, result)

# Pattern 4: Exit codes (from plan command)
# 0 = success (all checks pass)
# 1 = check failures found
# 3 = internal error

# Pattern 5: Metrics emission (from plan command, line 368)
_emit_metrics("check.completed", {"errors": n_errors, "warnings": n_warnings, ...})

# Pattern 6: Cloud upsell (from plan command, line 382)
if not _load_stored_token():
    console.print("[dim]Tip: ...[/dim]")
```

---

## 3. Architecture & Build System

### 3.1 High-Level Architecture

```
┌──────────────────────────────────────────────────────────────┐
│                     ironlayer CLI (Python)                     │
│  cli/app.py → @app.command() def check(...)                   │
│         │                                                     │
│         ▼                                                     │
│  ┌─────────────────────────────────────────────────────────┐ │
│  │           PyO3 Bridge Layer (check_engine Python module)  │ │
│  │  from ironlayer_check_engine import CheckEngine           │ │
│  │  engine = CheckEngine(config)                             │ │
│  │  result = engine.check(paths, options)                    │ │
│  └──────────────┬──────────────────────────────────────────┘ │
└─────────────────┼────────────────────────────────────────────┘
                  │ FFI boundary (PyO3)
┌─────────────────▼────────────────────────────────────────────┐
│              Rust Check Engine (ironlayer_check_engine)        │
│                                                               │
│  ┌───────────┐  ┌────────────┐  ┌──────────────┐            │
│  │ Discovery │→│  Parallel   │→│   Reporter    │            │
│  │ & Caching │  │  Checkers   │  │ (JSON/Human) │            │
│  └───────────┘  └────────────┘  └──────────────┘            │
│                  │                                            │
│    ┌─────────────┼─────────────────────────────────┐         │
│    │             │             │           │        │         │
│    ▼             ▼             ▼           ▼        ▼         │
│  ┌─────┐  ┌──────────┐  ┌────────┐  ┌────────┐  ┌────┐     │
│  │ SQL │  │ Header   │  │  Ref   │  │  YAML  │  │Name│     │
│  │Lexer│  │ Validator│  │Resolver│  │Validate│  │Conv│     │
│  └─────┘  └──────────┘  └────────┘  └────────┘  └────┘     │
└───────────────────────────────────────────────────────────────┘
```

### 3.2 What Rust Does vs. What Python Keeps

| Operation | Owner | Rationale |
|---|---|---|
| File discovery (walk directory, filter .sql/.yml) | **Rust** | `walkdir` crate is 10-50x faster than `pathlib.glob` |
| Content hashing (SHA-256) | **Rust** | Ring/sha2 crate, parallelized across files |
| Cache check (has file changed?) | **Rust** | Content-addressable cache in `.ironlayer/check_cache.json` |
| SQL header parsing (`-- key: value`) | **Rust** | Simple regex, no AST needed, pure string ops |
| SQL lexing (keyword detection, bracket matching) | **Rust** | Custom lexer sufficient for safety checks + basic lint |
| `{{ ref('...') }}` extraction | **Rust** | Regex-based, identical to `ref_resolver._REF_PATTERN` |
| Ref resolution (does ref target exist?) | **Rust** | Build registry from discovered model names, check membership |
| YAML parsing + schema validation | **Rust** | `serde_yaml` + custom schema validation |
| Naming convention enforcement | **Rust** | Regex-based pattern matching |
| Parallel orchestration (check all files concurrently) | **Rust** | `rayon` crate for data parallelism |
| JSON/human-readable output formatting | **Rust** | Generate output structs; Python does Rich formatting |
| Full AST analysis (output columns, CTEs, aggregation) | **Python** | SQLGlot (~2K LOC / 67KB impl) is a complex abstraction layer; rewriting gains nothing |
| DAG building | **Python** | NetworkX, needed for plan/lineage, not check |
| Plan generation | **Python** | Complex interval planning logic |
| Schema introspection (actual warehouse columns) | **Python** | Requires Databricks/DuckDB connection |

### 3.3 Build System

**Current state:** Both `ironlayer` and `ironlayer-core` v0.2.0 are pure-Python wheels built with `poetry-core 2.3.1` (tag: `py3-none-any`). Neither package contains any compiled extensions today.

**Migration:** `ironlayer-core` switches its build backend from poetry-core to maturin. This is a **build system migration** with these implications:
- `pyproject.toml` changes from `[build-system] requires = ["poetry-core"]` to `requires = ["maturin>=1.7,<2.0"]`
- The `[tool.poetry]` sections are replaced with `[tool.maturin]` configuration
- The resulting wheel changes from `py3-none-any` to platform-specific (e.g., `cp311-abi3-manylinux_2_17_x86_64`)
- `ironlayer` (the CLI package) remains pure-Python and keeps poetry-core as its build backend
- CI must build platform-specific wheels where it previously built a single universal wheel

**Build tool:** maturin (latest stable, currently 1.x)
**Rust edition:** 2021
**MSRV (minimum supported Rust version):** 1.75.0
**Python compatibility:** 3.11, 3.12 (matching existing `ironlayer-core` requirement: `>=3.11,<3.13`)
**ABI:** `abi3-py311` (stable ABI, single wheel per platform per Python major version)

The Rust crate compiles into a native extension module named `ironlayer_check_engine` that is bundled inside the `ironlayer-core` wheel. Users never interact with the Rust build system.

### 3.4 Monorepo Layout (New Files Only)

```
ironlayer/                              (existing repo root)
├── ironlayer-core/                     (existing Python package)
│   ├── core_engine/                    (existing Python modules — UNCHANGED)
│   ├── pyproject.toml                  (MODIFIED — add maturin build-backend)
│   └── Cargo.toml                      (NEW — Rust workspace member)
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
│   │   │   ├── sql_header.rs           SQL comment header validation
│   │   │   ├── sql_syntax.rs           SQL lexer + basic syntax checks
│   │   │   ├── sql_safety.rs           Dangerous operation pre-screen
│   │   │   ├── ref_resolver.rs         {{ ref('...') }} extraction + resolution
│   │   │   ├── yaml_schema.rs          YAML structure validation
│   │   │   ├── naming.rs               Naming convention enforcement
│   │   │   ├── dbt_project.rs          dbt-specific project validation
│   │   │   └── model_consistency.rs    Cross-model consistency checks
│   │   ├── sql_lexer.rs                Lightweight SQL tokenizer (NOT a full parser)
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
├── Cargo.toml                          (NEW — workspace root)
└── .cargo/
    └── config.toml                     (NEW — cross-compilation settings)
```

---

## 4. Rust Crate Structure

### 4.1 Cargo.toml (Workspace Root)

```toml
[workspace]
members = ["check_engine"]
resolver = "2"
```

### 4.2 Cargo.toml (check_engine)

```toml
[package]
name = "ironlayer-check-engine"
version = "0.3.0"
edition = "2021"
rust-version = "1.75.0"
license = "Apache-2.0"
description = "Rust-powered validation engine for IronLayer"

[lib]
name = "ironlayer_check_engine"
crate-type = ["cdylib", "rlib"]
# cdylib = Python extension module via PyO3
# rlib = standalone Rust library for testing

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
ignore = "0.4"                # .gitignore-aware file walking
thiserror = "2"
log = "0.4"
pyo3-log = "0.11"             # Bridge Rust log → Python logging
memchr = "2"                  # Fast byte searching for lexer
unicode-segmentation = "1"    # Proper Unicode handling
dirs = "6"                    # Cross-platform cache directory
chrono = { version = "0.4", features = ["serde"] }

[dev-dependencies]
criterion = { version = "0.5", features = ["html_reports"] }
tempfile = "3"
indoc = "2"

[[bench]]
name = "check_benchmark"
harness = false
```

### 4.3 Core Types (`types.rs`)

These types are the contract between Rust and Python. They mirror existing IronLayer Pydantic models exactly where applicable.

```rust
use pyo3::prelude::*;
use serde::{Deserialize, Serialize};

/// Mirrors core_engine.sql_toolkit._types.Dialect
/// Python values are lowercase strings: "databricks", "duckdb", "redshift"
/// The PyO3 enum exposes PascalCase variants but serializes to lowercase.
#[pyclass(eq, eq_int)]
#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
#[serde(rename_all = "lowercase")]
pub enum Dialect {
    Databricks,
    DuckDB,
    Redshift,
}

/// Check engine unified severity — maps FROM two different existing enums.
///
/// Existing IronLayer has TWO separate severity systems:
///   1. sql_guard.Severity:              CRITICAL, HIGH, MEDIUM
///   2. schema_validator.ViolationSeverity: BREAKING, WARNING, INFO
///
/// The check engine unifies these into a single 3-level system:
///   Error   ← sql_guard.CRITICAL + schema_validator.BREAKING
///   Warning ← sql_guard.HIGH + schema_validator.WARNING + sql_guard.MEDIUM
///   Info    ← schema_validator.INFO
///
/// When the check engine pre-screens for dangerous SQL (SAF rules), the
/// mapping from sql_guard._DEFAULT_SEVERITY is:
///   CRITICAL → Error  (DROP_TABLE, DROP_VIEW, DROP_SCHEMA, TRUNCATE, GRANT, REVOKE, CREATE_USER, RAW_EXEC)
///   HIGH     → Warning (DELETE_WITHOUT_WHERE, ALTER_DROP_COLUMN, INSERT_OVERWRITE_ALL)
///   MEDIUM   → Warning (no current operations map here, reserved for future)
#[pyclass(eq, eq_int)]
#[derive(Debug, Clone, Copy, PartialEq, Eq, PartialOrd, Ord, Serialize, Deserialize)]
pub enum Severity {
    Error,
    Warning,
    Info,
}

/// What kind of check produced this diagnostic
#[pyclass(eq, eq_int)]
#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
pub enum CheckCategory {
    SqlSyntax,          // SQL lexing/parsing issues
    SqlSafety,          // Dangerous SQL operations (mirrors sql_guard.py)
    SqlHeader,          // Model header validation (mirrors model_loader.py)
    RefResolution,      // {{ ref('...') }} issues (mirrors ref_resolver.py)
    SchemaContract,     // Column contract violations (mirrors schema_validator.py)
    YamlSchema,         // YAML structure issues
    NamingConvention,   // Naming pattern violations
    DbtProject,         // dbt-specific project structure issues
    ModelConsistency,   // Cross-model consistency issues
    FileStructure,      // File/directory organization issues
}

/// A single diagnostic (error, warning, or info) from a check.
/// This is the atomic unit of check output.
#[pyclass(get_all)]
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct CheckDiagnostic {
    /// Rule identifier, e.g. "SQL001", "REF002", "NAME003"
    pub rule_id: String,

    /// Human-readable message
    pub message: String,

    /// Severity level
    pub severity: Severity,

    /// Check category
    pub category: CheckCategory,

    /// File path relative to project root
    pub file_path: String,

    /// 1-based line number (0 if not applicable)
    pub line: u32,

    /// 1-based column number (0 if not applicable)
    pub column: u32,

    /// Optional: the offending text snippet (max 120 chars)
    pub snippet: Option<String>,

    /// Optional: suggested fix
    pub suggestion: Option<String>,

    /// Optional: URL to documentation for this rule
    pub doc_url: Option<String>,
}

/// Aggregate result of running all checks
#[pyclass(get_all)]
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct CheckResult {
    /// All diagnostics, sorted by (file_path, line, column)
    pub diagnostics: Vec<CheckDiagnostic>,

    /// Summary counts
    pub total_files_checked: u32,
    pub total_files_skipped_cache: u32,
    pub total_errors: u32,
    pub total_warnings: u32,
    pub total_infos: u32,

    /// Timing
    pub elapsed_ms: u64,

    /// Project type that was auto-detected
    pub project_type: String, // "ironlayer" | "dbt" | "raw_sql"

    /// Whether the check passed (zero errors)
    pub passed: bool,
}

/// Discovered model metadata (lightweight, no full AST)
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct DiscoveredModel {
    /// Model name from header or filename
    pub name: String,
    /// Relative file path
    pub file_path: String,
    /// SHA-256 of file content
    pub content_hash: String,
    /// Names referenced via {{ ref('...') }}
    pub ref_names: Vec<String>,
    /// Header fields parsed from -- comments
    pub header: std::collections::HashMap<String, String>,
}
```

### 4.4 Checker Trait (`checkers/mod.rs`)

```rust
use crate::types::{CheckDiagnostic, DiscoveredModel};
use crate::config::CheckConfig;

/// Every checker implements this trait.
/// Checkers are stateless and receive all context via parameters.
pub trait Checker: Send + Sync {
    /// Unique name for this checker (used in config to enable/disable)
    fn name(&self) -> &'static str;

    /// Run checks against a single file.
    /// Returns diagnostics for this file only.
    fn check_file(
        &self,
        file_path: &str,
        content: &str,
        model: Option<&DiscoveredModel>,
        config: &CheckConfig,
    ) -> Vec<CheckDiagnostic>;

    /// Run checks that require cross-file context (e.g., ref resolution).
    /// Called once after all files have been individually checked.
    /// Default: no cross-file checks.
    fn check_project(
        &self,
        models: &[DiscoveredModel],
        config: &CheckConfig,
    ) -> Vec<CheckDiagnostic> {
        let _ = (models, config);
        Vec::new()
    }
}
```

### 4.5 Engine Orchestrator (`engine.rs`)

```rust
use rayon::prelude::*;

pub struct CheckEngine {
    config: CheckConfig,
    checkers: Vec<Box<dyn Checker>>,
    cache: CheckCache,
}

impl CheckEngine {
    pub fn new(config: CheckConfig) -> Self { /* ... */ }

    pub fn check(&self, root: &Path) -> CheckResult {
        // 1. Discover project type
        let project_type = discovery::detect_project_type(root);

        // 2. Walk files (respecting .gitignore, .ironlayerignore)
        let files = discovery::walk_files(root, &self.config);

        // 3. Hash files, check cache
        let (cached, uncached) = self.cache.partition(&files);

        // 4. Parse SQL headers + extract refs (parallel over uncached files)
        let models: Vec<DiscoveredModel> = uncached
            .par_iter()
            .filter(|f| f.path.ends_with(".sql"))
            .map(|f| discover_model(f))
            .collect();

        // 5. Run per-file checks in parallel
        let file_diags: Vec<CheckDiagnostic> = uncached
            .par_iter()
            .flat_map(|file| {
                let model = models.iter().find(|m| m.file_path == file.rel_path);
                self.checkers.iter()
                    .flat_map(|c| c.check_file(&file.rel_path, &file.content, model, &self.config))
                    .collect::<Vec<_>>()
            })
            .collect();

        // 6. Run cross-file checks (sequential, needs full model list)
        let project_diags: Vec<CheckDiagnostic> = self.checkers.iter()
            .flat_map(|c| c.check_project(&models, &self.config))
            .collect();

        // 7. Merge, sort, build result
        // 8. Update cache for files with zero errors
        // 9. Return CheckResult
    }
}
```

---

## 5. Check Rules Specification

Every rule has:
- A **Rule ID** (e.g., `SQL001`) — stable across versions, never reused
- A **Default severity** — can be overridden in config
- A **Category** — groups rules in output
- A **Default state** — enabled or disabled by default
- A **Fixer availability** — whether `--fix` can auto-correct it

### 5.1 SQL Header Rules (HDR)

These validate the `-- key: value` comment block at the top of IronLayer-native `.sql` files. Only active when `project_type == "ironlayer"`.

| Rule ID | Default | Severity | Description | Fixable |
|---------|---------|----------|-------------|---------|
| `HDR001` | enabled | error | Missing required field `name` in SQL header | no |
| `HDR002` | enabled | error | Missing required field `kind` in SQL header | no |
| `HDR003` | enabled | error | Invalid `kind` value (must be one of: `FULL_REFRESH`, `INCREMENTAL_BY_TIME_RANGE`, `APPEND_ONLY`, `MERGE_BY_KEY`) | no |
| `HDR004` | enabled | error | Invalid `materialization` value (must be one of: `TABLE`, `VIEW`, `MERGE`, `INSERT_OVERWRITE`) | no |
| `HDR005` | enabled | error | `kind: INCREMENTAL_BY_TIME_RANGE` requires `time_column` field | no |
| `HDR006` | enabled | error | `kind: MERGE_BY_KEY` requires `unique_key` field | no |
| `HDR007` | disabled | warning | Unrecognized header field (not in the 13 known fields) | no |

**Note on HDR007:** The existing `model_loader.py` (line 46) states: *"Unrecognised keys are silently ignored so that forward-compatible extensions can be added without breaking older loaders."* HDR007 is **disabled by default** to preserve this intentional design. Teams that want stricter header validation can enable it via config. When enabled, HDR007 fires only as a warning, never an error, to avoid breaking forward-compatible headers.
| `HDR008` | disabled | warning | Missing optional but recommended `owner` field | no |
| `HDR009` | disabled | warning | Missing optional but recommended `tags` field | no |
| `HDR010` | enabled | error | Invalid `contract_mode` value (must be one of: `DISABLED`, `WARN`, `STRICT`) | no |
| `HDR011` | enabled | error | Malformed `contract_columns` syntax (expected `name:TYPE` or `name:TYPE:NOT_NULL`) | no |
| `HDR012` | enabled | error | Malformed `tests` syntax | no |
| `HDR013` | enabled | warning | Duplicate header field detected | yes |

**Implementation detail:** The header parser reads lines sequentially from the top of the file. A line is part of the header if it matches any of:
- `-- key: value` (a metadata declaration — only `_KNOWN_FIELDS` keys are stored; unknown keys are silently skipped)
- `--` followed by text without a colon (a plain comment — skipped but does NOT terminate the header)
- `--` alone (a bare comment separator — skipped, does NOT terminate the header)
- An empty/whitespace-only line (skipped, does NOT terminate the header)

The first line that is **both non-empty AND not a comment** terminates the header block. This matches the behavior in `model_loader.parse_yaml_header()`. The Rust reimplementation MUST replicate this exact logic, including the fact that blank lines and bare `--` comments inside the header block are allowed.

### 5.2 SQL Syntax Rules (SQL)

These use the lightweight Rust SQL lexer (not a full parser). They detect issues that don't require full AST analysis.

| Rule ID | Default | Severity | Description | Fixable |
|---------|---------|----------|-------------|---------|
| `SQL001` | enabled | error | Unbalanced parentheses in SQL body | no |
| `SQL002` | enabled | error | Unbalanced single quotes (unclosed string literal) | no |
| `SQL003` | enabled | error | Unbalanced backtick quotes | no |
| `SQL004` | enabled | warning | `SELECT *` detected (non-terminal query) | no |
| `SQL005` | enabled | warning | Missing `WHERE` clause on `DELETE` statement | no |
| `SQL006` | disabled | info | SQL body exceeds configured max line count (default: 500) | no |
| `SQL007` | enabled | warning | Trailing semicolons in model SQL (IronLayer models should not have trailing semicolons) | yes |
| `SQL008` | enabled | error | Empty SQL body (no SQL after header) | no |
| `SQL009` | disabled | warning | Tab characters detected (prefer spaces) | yes |

**What the Rust lexer does NOT do:**
- No full AST construction (that's SQLGlot's job in Python)
- No type checking
- No join analysis
- No column resolution
- No dialect-specific keyword validation (except basic keyword recognition for safety checks)

The lexer produces a stream of tokens: `Keyword`, `Identifier`, `StringLiteral`, `NumberLiteral`, `Operator`, `Punctuation`, `Comment`, `Whitespace`, `Unknown`. This is sufficient for all SQL rules above.

### 5.3 SQL Safety Rules (SAF)

These pre-screen for dangerous operations, mirroring `sql_guard.py`'s `DangerousOperation` enum. The Rust lexer detects these via keyword sequences (not full AST), so they are a fast pre-filter. False positives are acceptable (Python's sql_guard runs the full AST check at plan time).

| Rule ID | Default | Severity | Maps to DangerousOperation | Description |
|---------|---------|----------|---------------------------|-------------|
| `SAF001` | enabled | error | `DROP_TABLE` | `DROP TABLE` keyword sequence detected |
| `SAF002` | enabled | error | `DROP_VIEW` | `DROP VIEW` keyword sequence detected |
| `SAF003` | enabled | error | `DROP_SCHEMA` | `DROP SCHEMA`/`DROP DATABASE` keyword sequence detected |
| `SAF004` | enabled | error | `TRUNCATE` | `TRUNCATE TABLE` keyword sequence detected |
| `SAF005` | enabled | warning | `DELETE_WITHOUT_WHERE` | `DELETE FROM` without subsequent `WHERE` keyword |
| `SAF006` | enabled | warning | `ALTER_DROP_COLUMN` | `ALTER TABLE ... DROP COLUMN` keyword sequence |
| `SAF007` | enabled | error | `GRANT` | `GRANT` keyword at statement start |
| `SAF008` | enabled | error | `REVOKE` | `REVOKE` keyword at statement start |
| `SAF009` | enabled | error | `CREATE_USER` | `CREATE USER`/`CREATE ROLE` keyword sequence |
| `SAF010` | enabled | warning | `INSERT_OVERWRITE_ALL` | `INSERT OVERWRITE` without `PARTITION` clause |

**Note on `RAW_EXEC`:** The 11th `DangerousOperation` variant (`RAW_EXEC`) is a catch-all for SQL that cannot be parsed at all. The Rust engine does NOT have a keyword-based rule for it. Instead, if the SQL lexer encounters a file it cannot tokenize at all, it emits `SQL008` (empty SQL body) or a general parse warning. The full `RAW_EXEC` detection happens at plan time in `sql_guard.py` via full AST analysis.

**Important:** Safety rules only fire on SQL outside of string literals and comments. The lexer's tokenization ensures this.

### 5.4 Ref Resolution Rules (REF)

These validate `{{ ref('...') }}` macro usage, reimplementing the logic in `ref_resolver.py`.

| Rule ID | Default | Severity | Description | Fixable |
|---------|---------|----------|-------------|---------|
| `REF001` | enabled | error | `{{ ref('model_name') }}` references a model that doesn't exist in the project | no |
| `REF002` | enabled | warning | Circular ref dependency detected (A→B→A) | no |
| `REF003` | enabled | warning | Self-referential ref (model references itself) | no |
| `REF004` | enabled | info | Ref uses fully-qualified name where short name would suffice | yes |
| `REF005` | enabled | warning | Ambiguous short name: two models share the same short name but different schemas | no |
| `REF006` | disabled | info | Direct table reference used instead of `{{ ref('...') }}` (hardcoded table name) | no |

**Resolution algorithm:**
1. Walk all `.sql` files, extract model names from `-- name:` header (or filename)
2. Build registry: `{short_name → canonical, canonical → canonical}` (same as `build_model_registry()`)
3. Walk all `.sql` files again, extract ref names via regex
4. For each ref name, check membership in registry

### 5.5 YAML Schema Rules (YML)

These validate YAML files commonly found in data projects.

| Rule ID | Default | Severity | Auto-detect applies to | Description |
|---------|---------|----------|----------------------|-------------|
| `YML001` | enabled | error | `*.yml`, `*.yaml` | Invalid YAML syntax (parse error) |
| `YML002` | enabled | error | `dbt_project.yml` | Missing required `name` field |
| `YML003` | enabled | error | `dbt_project.yml` | Missing required `version` field |
| `YML004` | enabled | warning | `schema.yml` / `*.yml` in models/ | Model listed in YAML but no corresponding `.sql` file found |
| `YML005` | enabled | warning | `schema.yml` / `*.yml` in models/ | `.sql` file exists but model not documented in any YAML file |
| `YML006` | enabled | error | `schema.yml` / `*.yml` in models/ | Column listed in YAML does not match any output column in SQL (requires Python AST, so this check calls into Python — see §9) |
| `YML007` | enabled | warning | `schema.yml` / `*.yml` in models/ | Model has zero tests defined in YAML |
| `YML008` | enabled | warning | `schema.yml` / `*.yml` in models/ | Model has zero column-level descriptions |
| `YML009` | disabled | info | `profiles.yml` | Profile references non-existent target |

**Note:** `YML006` requires full SQL AST analysis to extract output columns. This is one of the few checks that calls back into Python (via the `sql_toolkit.scope_analyzer.extract_columns()` pathway). If the Python bridge is unavailable (e.g., running the Rust binary standalone), this check is skipped with an info diagnostic.

**YML006 Python callback mechanism:** The Rust engine calls into Python via PyO3's GIL acquisition:

```rust
// In checkers/yaml_schema.rs — YML006 implementation
fn check_yaml_column_match(
    &self,
    yaml_columns: &[String],
    sql_file_path: &str,
    sql_content: &str,
) -> Vec<CheckDiagnostic> {
    // Acquire GIL and call into Python
    Python::with_gil(|py| {
        let toolkit = py.import("core_engine.sql_toolkit")?;
        let get_tk = toolkit.getattr("get_sql_toolkit")?;
        let tk = get_tk.call0()?;
        let scope = tk.getattr("scope_analyzer")?;
        let result = scope.call_method1(
            "extract_columns",
            (sql_content, "databricks"),
        )?;
        let output_columns: Vec<String> = result
            .getattr("output_columns")?
            .extract()?;
        // Compare yaml_columns against output_columns...
    })
}
```

**GIL considerations:**
- The GIL is acquired only for the duration of the Python call, not for the entire check run.
- YML006 runs in the **sequential** `check_project()` phase, not the parallel per-file phase, to avoid GIL contention.
- If the Python import fails (e.g., `core_engine` not installed), YML006 is silently skipped and an info diagnostic is emitted: "YML006 skipped: Python SQL toolkit unavailable."
- The Python call has a 5-second timeout per file. If it exceeds this, the check is skipped for that file with a warning.

### 5.6 Naming Convention Rules (NAME)

All patterns are configurable via `ironlayer.check.toml` or `[tool.ironlayer.check]` in `pyproject.toml`.

| Rule ID | Default | Severity | Applies to | Default Pattern | Description |
|---------|---------|----------|-----------|----------------|-------------|
| `NAME001` | enabled | warning | SQL files | `^(stg\|staging)_` | Staging models must start with `stg_` or `staging_` |
| `NAME002` | enabled | warning | SQL files | `^(int\|intermediate)_` | Intermediate models must start with `int_` or `intermediate_` |
| `NAME003` | enabled | warning | SQL files | `^(fct\|fact)_` | Fact models must start with `fct_` or `fact_` |
| `NAME004` | enabled | warning | SQL files | `^(dim\|dimension)_` | Dimension models must start with `dim_` or `dimension_` |
| `NAME005` | enabled | warning | SQL files | `^[a-z][a-z0-9_]*$` | Model names must be lowercase snake_case |
| `NAME006` | enabled | warning | SQL files | (directory-based) | Model file location must match its layer prefix (e.g., `stg_*` in `staging/`) |
| `NAME007` | disabled | warning | Columns | `^[a-z][a-z0-9_]*$` | Column names must be lowercase snake_case |
| `NAME008` | disabled | info | SQL files | (no `.sql` in model name) | Model `-- name:` should not include file extension |

**Layer detection:** The checker infers the model's layer from the file path directory structure:
- Files in `staging/`, `stg/` → expected prefix `stg_`
- Files in `intermediate/`, `int/` → expected prefix `int_`
- Files in `marts/`, `mart/` → expected prefix `fct_` or `dim_`
- Files in any other directory → NAME001-NAME004 do not fire

### 5.7 dbt Project Rules (DBT)

Active only when `project_type == "dbt"` (detected by presence of `dbt_project.yml`).

| Rule ID | Default | Severity | Description |
|---------|---------|----------|-------------|
| `DBT001` | enabled | error | `dbt_project.yml` not found in project root |
| `DBT002` | enabled | warning | Model file not in a configured model path (per `dbt_project.yml` model-paths) |
| `DBT003` | enabled | warning | Source referenced in SQL but not defined in any `sources.yml` |
| `DBT004` | enabled | warning | Model uses `{{ config(...) }}` with unrecognized materialization |
| `DBT005` | disabled | info | Model does not have a unique test on at least one column |
| `DBT006` | disabled | info | Model does not have a `not_null` test on its primary key |

### 5.8 Model Consistency Rules (CON)

These require cross-file analysis and run in the `check_project()` phase.

| Rule ID | Default | Severity | Description |
|---------|---------|----------|-------------|
| `CON001` | enabled | error | Two models have the same `-- name:` value (duplicate model name) |
| `CON002` | enabled | warning | Model has declared dependencies (in `-- dependencies:`) that are not in its `{{ ref() }}` calls |
| `CON003` | enabled | warning | Model uses `{{ ref() }}` calls not listed in `-- dependencies:` |
| `CON004` | disabled | info | Orphan model: no other model references it AND it has no downstream consumers |

**Note on CON004:** This rule is disabled by default because terminal mart models (consumed by BI tools, dashboards, or external systems) are legitimately never referenced by other models within the project. Enabling this rule would flag every leaf-node mart model as an error. Teams with strict internal-only DAGs can enable it via config.
| `CON005` | disabled | info | Model has no declared owner |

---

## 6. Configuration Format

### 6.1 Configuration File Resolution Order

The check engine looks for configuration in this order (first found wins):

1. `ironlayer.check.toml` (project root)
2. `[tool.ironlayer.check]` section in `pyproject.toml`
3. `[check]` section in `ironlayer.yaml` (existing IronLayer config)
4. Built-in defaults

### 6.2 Configuration Schema (`ironlayer.check.toml`)

```toml
# IronLayer Check Engine Configuration
# Full reference: https://docs.ironlayer.app/check/config

[check]
# Fail on warnings (treat warnings as errors)
fail_on_warnings = false

# Maximum number of diagnostics to report (0 = unlimited)
max_diagnostics = 200

# Dialect for SQL parsing (auto-detected from project config if not set)
# Valid: "databricks", "duckdb", "redshift"
dialect = "databricks"

# Files/directories to exclude (in addition to .gitignore)
exclude = [
    "target/",
    "dbt_packages/",
    "logs/",
    "macros/",
    ".venv/",
]

# Additional file extensions to check (beyond .sql, .yml, .yaml)
extra_extensions = []

[check.cache]
# Enable content-addressable caching
enabled = true
# Cache file location (relative to project root)
path = ".ironlayer/check_cache.json"

# ──────────────────────────────────────────────────────────────
# Per-rule overrides
# Each rule can be: "error", "warning", "info", "off"
# ──────────────────────────────────────────────────────────────
[check.rules]
# Disable a specific rule
SQL004 = "off"            # Allow SELECT *

# Upgrade a warning to an error
NAME005 = "error"         # Enforce snake_case as error

# Enable a normally-disabled rule
HDR008 = "warning"        # Require owner field
DBT005 = "warning"        # Require unique test

# ──────────────────────────────────────────────────────────────
# Naming convention patterns (regex)
# ──────────────────────────────────────────────────────────────
[check.naming]
# Override the default model name pattern
model_pattern = "^[a-z][a-z0-9_]*$"

# Layer prefix patterns (directory → required prefix)
[check.naming.layers]
staging = "^stg_"
intermediate = "^int_"
marts_fact = "^fct_"
marts_dimension = "^dim_"

# ──────────────────────────────────────────────────────────────
# dbt-specific settings
# ──────────────────────────────────────────────────────────────
[check.dbt]
# Path to dbt_project.yml (auto-detected if not set)
project_file = "dbt_project.yml"
# Require docs for every model
require_model_docs = false
# Require at least N tests per model
min_tests_per_model = 0

# ──────────────────────────────────────────────────────────────
# Per-path rule overrides (most specific path wins)
# ──────────────────────────────────────────────────────────────
[[check.per_path]]
path = "models/staging/**"
rules = { SQL004 = "off" }    # Allow SELECT * in staging models

[[check.per_path]]
path = "models/marts/**"
rules = { HDR008 = "error", SQL004 = "error" }   # Strict rules for marts
```

### 6.3 Configuration Struct (`config.rs`)

```rust
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct CheckConfig {
    pub fail_on_warnings: bool,
    pub max_diagnostics: usize,
    pub dialect: Dialect,
    pub exclude: Vec<String>,
    pub extra_extensions: Vec<String>,
    pub cache: CacheConfig,
    pub rules: HashMap<String, RuleSeverityOverride>,
    pub naming: NamingConfig,
    pub dbt: DbtConfig,
    pub per_path: Vec<PerPathOverride>,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub enum RuleSeverityOverride {
    Error,
    Warning,
    Info,
    Off,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct CacheConfig {
    pub enabled: bool,
    pub path: String,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct NamingConfig {
    pub model_pattern: String,
    pub layers: HashMap<String, String>, // directory_name → regex pattern
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct DbtConfig {
    pub project_file: Option<String>,
    pub require_model_docs: bool,
    pub min_tests_per_model: u32,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct PerPathOverride {
    pub path: String, // glob pattern
    pub rules: HashMap<String, RuleSeverityOverride>,
}
```

---

## 7. CLI Integration

### 7.1 New Command: `ironlayer check`

Added to `cli/app.py` following all existing patterns:

```python
@app.command()
def check(
    repo: Path = typer.Argument(
        ...,
        help="Path to the repository containing SQL models.",
        exists=True,
        file_okay=False,
        resolve_path=True,
    ),
    fix: bool = typer.Option(
        False,
        "--fix",
        help="Auto-fix issues where possible (modifies files in-place).",
    ),
    fail_on_warnings: bool = typer.Option(
        False,
        "--fail-on-warnings",
        help="Exit with code 1 if any warnings are found.",
    ),
    select: str | None = typer.Option(
        None,
        "--select",
        "-s",
        help="Comma-separated rule IDs or categories to run (e.g., 'SQL,REF001').",
    ),
    exclude_rules: str | None = typer.Option(
        None,
        "--exclude",
        "-e",
        help="Comma-separated rule IDs or categories to skip.",
    ),
    no_cache: bool = typer.Option(
        False,
        "--no-cache",
        help="Ignore the check cache and re-validate all files.",
    ),
    config_file: Path | None = typer.Option(
        None,
        "--config",
        help="Path to ironlayer.check.toml configuration file.",
    ),
    sarif: bool = typer.Option(
        False,
        "--sarif",
        help="Output results in SARIF format (for GitHub Code Scanning).",
    ),
    changed_only: bool = typer.Option(
        False,
        "--changed-only",
        help="Only check files changed in the current git working tree.",
    ),
) -> None:
    """Validate SQL models, YAML schemas, naming conventions, and project structure.

    Powered by a Rust engine for blazing-fast validation. Checks all discovered
    models in parallel and reports issues in order of severity.

    Exit codes: 0 = all checks pass, 1 = errors found, 3 = internal error.
    """
    try:
        from ironlayer_check_engine import CheckEngine, CheckConfig
    except ImportError:
        console.print(
            "[red]Check engine not available. Reinstall ironlayer:[/red]\n"
            "  pip install --force-reinstall ironlayer"
        )
        raise typer.Exit(code=3)

    # Build config from file + CLI overrides
    config = _build_check_config(
        repo, fix, fail_on_warnings, select, exclude_rules,
        no_cache, config_file, changed_only
    )

    # Run checks
    engine = CheckEngine(config)
    result = engine.check(str(repo))

    # Emit metrics
    _emit_metrics("check.completed", {
        "total_files": result.total_files_checked,
        "cached": result.total_files_skipped_cache,
        "errors": result.total_errors,
        "warnings": result.total_warnings,
        "elapsed_ms": result.elapsed_ms,
        "project_type": result.project_type,
    })

    # Output
    if sarif:
        sys.stdout.write(result.to_sarif_json() + "\n")
    elif _json_output:
        sys.stdout.write(result.to_json() + "\n")
    else:
        display_check_results(console, result)

        # Cloud upsell
        if not _load_stored_token() and result.total_errors > 0:
            console.print(
                "\n[dim]Tip: Get AI-powered fix suggestions -- run "
                "[bold]ironlayer login[/bold] to connect to IronLayer Cloud.[/dim]"
            )

    exit_code = 0 if result.passed else 1
    raise typer.Exit(code=exit_code)
```

### 7.2 Display Function (`cli/display.py` addition)

```python
def display_check_results(console: Console, result: CheckResult) -> None:
    """Rich-formatted check results display."""

    # Header
    status = "[green]PASSED[/green]" if result.passed else "[red]FAILED[/red]"
    console.print(f"\n⚡ IronLayer Check — {status}  ({result.elapsed_ms}ms)\n")

    # File summary
    console.print(
        f"  Files: {result.total_files_checked} checked, "
        f"{result.total_files_skipped_cache} cached  "
        f"({result.project_type} project)"
    )

    if not result.diagnostics:
        console.print("\n  [green]✓ No issues found.[/green]\n")
        return

    # Group by file
    by_file: dict[str, list] = {}
    for d in result.diagnostics:
        by_file.setdefault(d.file_path, []).append(d)

    for file_path, diags in sorted(by_file.items()):
        console.print(f"\n  [bold]{file_path}[/bold]")
        for d in diags:
            icon = {"error": "✗", "warning": "⚠", "info": "ℹ"}[d.severity]
            color = {"error": "red", "warning": "yellow", "info": "dim"}[d.severity]
            loc = f":{d.line}" if d.line > 0 else ""
            col = f":{d.column}" if d.column > 0 else ""
            console.print(
                f"    [{color}]{icon} {d.rule_id}[/{color}] "
                f"[dim]{file_path}{loc}{col}[/dim]  {d.message}"
            )
            if d.suggestion:
                console.print(f"      [dim]→ {d.suggestion}[/dim]")

    # Summary line
    console.print(
        f"\n── {result.total_errors} error(s), "
        f"{result.total_warnings} warning(s), "
        f"{result.total_infos} info(s)  "
        f"({result.elapsed_ms}ms)\n"
    )
```

### 7.3 Exit Code Contract

| Code | Meaning | When |
|------|---------|------|
| `0` | Success | Zero errors (warnings allowed unless `--fail-on-warnings`) |
| `1` | Check failures | One or more errors found (or warnings with `--fail-on-warnings`) |
| `3` | Internal error | Engine crash, missing dependency, I/O failure |

These match the existing exit code patterns in `cli/app.py`. The plan command uses 0 (success) and 3 (internal error). Exit code 1 is already used by other commands (backfill, apply) for user/validation errors, so the check command's use of code 1 for "errors found" is consistent with CLI precedent.

### 7.4 `--fix` Mechanics

When `--fix` is passed, the engine modifies files in place for rules marked "Fixable" in §5. The fix workflow is:

1. **Dry-run first:** The engine runs all checks normally and collects diagnostics.
2. **Filter fixable:** Only diagnostics for rules marked fixable AND with severity ≤ the rule's configured level are candidates.
3. **Apply fixes per-file:** For each file with fixable diagnostics, the engine:
   - Reads the file content
   - Applies fixes in **reverse line order** (bottom-up) to avoid line number shifting
   - Writes the modified content back to the same path via atomic write (write to `.tmp`, rename)
4. **Re-check:** After all fixes are applied, the engine re-runs checks on modified files to confirm fixes didn't introduce new issues.
5. **Report:** Output shows which fixes were applied:
   ```
   ⚡ IronLayer Check — 3 issues auto-fixed

     models/staging/stg_orders.sql
       ✓ SQL007  Removed trailing semicolon (line 45)
       ✓ SQL009  Replaced tabs with spaces (lines 12, 18, 22)

     models/marts/fct_revenue.sql
       ✓ HDR013  Removed duplicate 'owner' header field (line 5)
   ```

**No backups are created.** The assumption is that files are under version control (git). If `git` is available and the working tree is dirty for a file about to be fixed, the engine prints a warning but proceeds. If `git` is not available, fixes proceed without warning.

**Fixable rules and their fix behavior:**
| Rule | Fix Action |
|------|-----------|
| `SQL007` | Remove trailing semicolons from SQL body |
| `SQL009` | Replace tab characters with 4 spaces |
| `HDR013` | Remove duplicate header lines (keep first occurrence) |
| `REF004` | Replace fully-qualified ref name with short name where unambiguous |

---

## 8. Output Format

### 8.1 Human-Readable (default, to stderr via Rich)

```
⚡ IronLayer Check — FAILED  (247ms)

  Files: 142 checked, 38 cached  (ironlayer project)

  models/staging/stg_orders.sql
    ✗ REF001 :14  Undefined ref: 'raw.orders_v2'. No model with this name exists.
      → Did you mean 'raw_orders_v2'? (Levenshtein distance: 1)
    ⚠ SQL004 :22  SELECT * detected. Consider listing columns explicitly.

  models/marts/fct_revenue.sql
    ✗ HDR006 :3   kind: MERGE_BY_KEY requires 'unique_key' header field.
    ⚠ NAME003 :1  Fact model name 'revenue_summary' should start with 'fct_'.

  schema.yml
    ⚠ YML005       Model 'stg_payments' has a SQL file but is not documented in any YAML.
    ⚠ YML007       Model 'dim_customers' has zero tests defined.

── 2 error(s), 4 warning(s), 0 info(s)  (247ms)
```

### 8.2 JSON (via `--json` flag, to stdout)

```json
{
  "passed": false,
  "project_type": "ironlayer",
  "elapsed_ms": 247,
  "summary": {
    "total_files_checked": 142,
    "total_files_skipped_cache": 38,
    "total_errors": 2,
    "total_warnings": 4,
    "total_infos": 0
  },
  "diagnostics": [
    {
      "rule_id": "REF001",
      "message": "Undefined ref: 'raw.orders_v2'. No model with this name exists.",
      "severity": "error",
      "category": "RefResolution",
      "file_path": "models/staging/stg_orders.sql",
      "line": 14,
      "column": 18,
      "snippet": "FROM {{ ref('raw.orders_v2') }}",
      "suggestion": "Did you mean 'raw_orders_v2'? (Levenshtein distance: 1)",
      "doc_url": "https://docs.ironlayer.app/check/rules/REF001"
    }
  ]
}
```

### 8.3 SARIF (via `--sarif` flag, for GitHub Code Scanning)

The engine produces SARIF v2.1.0 compatible output so that `ironlayer check --sarif` can be piped directly into GitHub's `github/codeql-action/upload-sarif@v3` action.

**Severity mapping to SARIF levels:**
| Check Engine Severity | SARIF `level` |
|----------------------|--------------|
| `Error` | `error` |
| `Warning` | `warning` |
| `Info` | `note` |

**Structure:**

```json
{
  "$schema": "https://raw.githubusercontent.com/oasis-tcs/sarif-spec/main/sarif-2.1/schema/sarif-schema-2.1.0.json",
  "version": "2.1.0",
  "runs": [
    {
      "tool": {
        "driver": {
          "name": "ironlayer-check",
          "version": "0.3.0",
          "informationUri": "https://docs.ironlayer.app/check",
          "rules": [
            {
              "id": "REF001",
              "name": "UndefinedRef",
              "shortDescription": { "text": "Undefined model reference" },
              "helpUri": "https://docs.ironlayer.app/check/rules/REF001",
              "defaultConfiguration": { "level": "error" }
            }
          ]
        }
      },
      "results": [
        {
          "ruleId": "REF001",
          "level": "error",
          "message": { "text": "Undefined ref: 'raw.orders_v2'. No model with this name exists." },
          "locations": [
            {
              "physicalLocation": {
                "artifactLocation": { "uri": "models/staging/stg_orders.sql" },
                "region": { "startLine": 14, "startColumn": 18 }
              }
            }
          ],
          "fixes": [
            {
              "description": { "text": "Did you mean 'raw_orders_v2'?" }
            }
          ]
        }
      ]
    }
  ]
}
```

**Field mapping from `CheckDiagnostic` to SARIF `result`:**
| CheckDiagnostic field | SARIF location |
|----------------------|----------------|
| `rule_id` | `result.ruleId` |
| `message` | `result.message.text` |
| `severity` | `result.level` (mapped per table above) |
| `file_path` | `result.locations[0].physicalLocation.artifactLocation.uri` |
| `line` | `result.locations[0].physicalLocation.region.startLine` |
| `column` | `result.locations[0].physicalLocation.region.startColumn` |
| `suggestion` | `result.fixes[0].description.text` (omitted if None) |
| `snippet` | `result.locations[0].physicalLocation.contextRegion.snippet.text` (omitted if None) |

---

## 9. PyO3 Bindings

### 9.1 Python Module Definition (`pyo3_bindings.rs`)

```rust
use pyo3::prelude::*;

/// The Python module exposed by this crate.
/// Importable as: `from ironlayer_check_engine import CheckEngine`
#[pymodule]
fn ironlayer_check_engine(m: &Bound<'_, PyModule>) -> PyResult<()> {
    // Initialize Rust logging → Python logging bridge
    pyo3_log::init();

    m.add_class::<CheckEngine>()?;
    m.add_class::<CheckConfig>()?;
    m.add_class::<CheckResult>()?;
    m.add_class::<CheckDiagnostic>()?;
    m.add_class::<Severity>()?;
    m.add_class::<CheckCategory>()?;
    m.add_class::<Dialect>()?;

    // Convenience function for one-shot checks
    m.add_function(wrap_pyfunction!(quick_check, m)?)?;

    Ok(())
}

/// One-shot check function (no config required).
/// Equivalent to: CheckEngine(CheckConfig.default()).check(path)
#[pyfunction]
fn quick_check(path: &str) -> PyResult<CheckResult> {
    let config = CheckConfig::default();
    let engine = CheckEngine::new(config);
    Ok(engine.check(std::path::Path::new(path)))
}
```

### 9.2 Python API Surface

```python
# These are the ONLY public Python symbols exposed by the Rust extension.
# All types are fully typed (PyO3 generates __init__.pyi stubs).

from ironlayer_check_engine import (
    CheckEngine,        # Main orchestrator class
    CheckConfig,        # Configuration dataclass
    CheckResult,        # Aggregate result
    CheckDiagnostic,    # Single diagnostic
    Severity,           # Enum: Error, Warning, Info
    CheckCategory,      # Enum: SqlSyntax, SqlSafety, SqlHeader, ...
    Dialect,            # Enum: Databricks, DuckDB, Redshift
    quick_check,        # One-shot convenience function
)

# Usage:
config = CheckConfig()                    # All defaults
config.dialect = Dialect.Databricks
config.fail_on_warnings = True

engine = CheckEngine(config)
result = engine.check("/path/to/project")

assert isinstance(result.passed, bool)
assert isinstance(result.diagnostics, list)
for d in result.diagnostics:
    assert isinstance(d.rule_id, str)     # e.g., "REF001"
    assert isinstance(d.severity, Severity)
    assert isinstance(d.category, CheckCategory)

# JSON serialization (Rust-side, fast)
json_str = result.to_json()
sarif_str = result.to_sarif_json()
```

### 9.3 PyO3 Build Integration in `ironlayer-core`

The existing `ironlayer-core` package's `pyproject.toml` is updated:

```toml
[build-system]
requires = ["maturin>=1.7,<2.0"]
build-backend = "maturin"

[tool.maturin]
# Build the Rust crate and include it alongside the pure Python package
features = ["pyo3/extension-module", "pyo3/abi3-py311"]
python-source = "."
module-name = "ironlayer_check_engine"

# The Rust crate is in the sibling directory
manifest-path = "../check_engine/Cargo.toml"

# Include pure Python modules alongside the Rust extension
include = ["core_engine/**/*.py", "core_engine/py.typed"]
```

**Result:** After `maturin build --release`, the wheel contains:
- All existing `core_engine/` Python modules (unchanged)
- The compiled `ironlayer_check_engine.cpython-311-x86_64-linux-gnu.so` (or platform equivalent)
- Users import both: `from core_engine.models import ModelDefinition` and `from ironlayer_check_engine import CheckEngine`

---

## 10. File Discovery & Git Integration

### 10.1 Project Type Detection (`discovery.rs`)

```rust
pub enum ProjectType {
    IronLayer,  // Has ironlayer.yaml or models/ with -- headers
    Dbt,        // Has dbt_project.yml
    SqlMesh,    // Has config.yaml with sqlmesh markers
    RawSql,     // Just .sql files, no framework detected
}

pub fn detect_project_type(root: &Path) -> ProjectType {
    // Priority order (first match wins):
    if root.join("ironlayer.yaml").exists() || root.join("ironlayer.yml").exists() {
        return ProjectType::IronLayer;
    }
    if root.join("dbt_project.yml").exists() {
        return ProjectType::Dbt;
    }
    // Check if any .sql file has IronLayer-style headers
    // (sample first 5 .sql files for performance)
    if has_ironlayer_headers(root) {
        return ProjectType::IronLayer;
    }
    ProjectType::RawSql
}
```

### 10.2 File Walking

Uses the `ignore` crate (same library used by ripgrep) which natively respects `.gitignore`, `.ignore`, and `.ironlayerignore` files.

**`.ironlayerignore` format:** Identical to `.gitignore` syntax (gitignore-compatible glob patterns). The `ignore` crate handles this natively. Example:

```gitignore
# .ironlayerignore — additional exclusions for ironlayer check
snapshots/           # Snapshot models have different rules
legacy_models/       # Pre-migration models, not yet conforming
*_backup.sql         # Backup files
```

The precedence order for exclusion is:
1. Hardcoded exclusions (see below) — always applied
2. `.gitignore` — if present in repo
3. `.ironlayerignore` — if present in repo root or any subdirectory
4. `exclude` list from `ironlayer.check.toml` config

Default include patterns:
- `**/*.sql`
- `**/*.yml`
- `**/*.yaml`

Default exclude patterns (hardcoded, in addition to `.gitignore`):
- `target/`, `dbt_packages/`, `dbt_modules/`, `logs/`
- `.venv/`, `node_modules/`, `__pycache__/`
- `.git/`, `.ironlayer/` (cache directory)

### 10.3 `--changed-only` Mode

When `--changed-only` is passed:
1. Run `git diff --name-only HEAD` to get modified/untracked files
2. Run `git diff --name-only --staged` to get staged files
3. Union both sets
4. Filter to only `.sql`/`.yml`/`.yaml` files
5. Only check these files (but still build full model registry for REF checks)

This is implemented via `std::process::Command` calling `git`. If `git` is not available or the directory is not a git repo, fall back to checking all files with a warning.

---

## 11. Performance Requirements

### 11.1 Benchmarks (Target)

| Scenario | Target | Comparison |
|---|---|---|
| 100 SQL models, cold (no cache) | < 200ms | SQLFluff: ~10s |
| 500 SQL models, cold (no cache) | < 500ms | SQLFluff: ~47s |
| 500 SQL models, warm (all cached) | < 50ms | N/A |
| 1000 SQL models, cold | < 1s | SQLFluff: ~95s |
| Single file (incremental) | < 20ms | SQLFluff: ~1s |

### 11.2 Performance Strategies

1. **Parallel file I/O + checking** via `rayon`. Every file is read and checked independently.
2. **Content-addressable cache**: SHA-256 hash of file content → previous diagnostics. If hash matches, skip re-checking.
3. **Lazy loading**: YAML files are only parsed if YAML rules are enabled.
4. **Zero-copy string processing**: The SQL lexer operates on `&str` slices, never allocating new strings for tokens.
5. **Early termination**: If `max_diagnostics` is reached, stop checking remaining files.

### 11.3 Cache Format (`.ironlayer/check_cache.json`)

```json
{
  "version": "1",
  "engine_version": "0.3.0",
  "config_hash": "a1b2c3...",
  "entries": {
    "models/staging/stg_orders.sql": {
      "content_hash": "sha256:abc123...",
      "last_checked": "2026-02-27T10:30:00Z",
      "diagnostics": []
    },
    "models/marts/fct_revenue.sql": {
      "content_hash": "sha256:def456...",
      "last_checked": "2026-02-27T10:30:00Z",
      "diagnostics": [
        { "rule_id": "NAME003", "severity": "warning", "message": "..." }
      ]
    }
  }
}
```

**Cache invalidation triggers:**
- File content hash changes → re-check that file
- Config hash changes (any rule override, naming pattern, etc.) → invalidate entire cache
- Engine version changes → invalidate entire cache
- `--no-cache` flag → bypass entirely

**Cache concurrency:** Two concurrent `ironlayer check` processes (e.g., parallel CI jobs, or a user running check while pre-commit also runs it) may race on the cache file. The engine handles this with:
1. **Atomic writes:** Cache is written to a temporary file (`.ironlayer/check_cache.json.tmp.{pid}`) then renamed via `std::fs::rename()`. On POSIX systems, rename is atomic. On Windows, `ReplaceFile` is used.
2. **Last writer wins:** No file locking. If two processes write simultaneously, the last rename wins. This is safe because a stale cache only causes redundant re-checking (correctness is never affected — the cache is purely a performance optimization).
3. **Corrupt cache recovery:** If the cache file fails to parse as valid JSON (e.g., truncated write from a crash), the engine logs a warning and proceeds as if `--no-cache` was passed. The corrupt file is deleted and rebuilt.

---

## 12. Error Taxonomy

### 12.1 Rule ID Format

```
{CATEGORY}{NUMBER}
```

Categories:
- `HDR` — SQL header rules (001-099)
- `SQL` — SQL syntax rules (001-099)
- `SAF` — SQL safety rules (001-099)
- `REF` — Ref resolution rules (001-099)
- `YML` — YAML schema rules (001-099)
- `NAME` — Naming convention rules (001-099)
- `DBT` — dbt project rules (001-099)
- `CON` — Model consistency rules (001-099)

Rule IDs are **permanent**: once assigned, a rule ID is never reused or reassigned, even if the rule is deprecated.

### 12.2 Diagnostic Quality Requirements

Every diagnostic MUST have:
1. A specific, actionable message (not "invalid SQL")
2. The exact file path and line number (where applicable)
3. A suggestion when one exists (e.g., "Did you mean 'stg_orders'?")
4. A doc URL pointing to the rule's documentation page

Bad: `"Error in SQL file"`
Good: `"Undefined ref: 'raw.orders_v2'. No model with this name exists in the project. Did you mean 'raw_orders_v2'?"`

### 12.3 Fuzzy Matching for Suggestions

When `REF001` fires (undefined ref), the engine computes Levenshtein distance between the undefined name and all known model names. If any model name is within distance ≤ 3, it's suggested.

When `NAME003` fires (wrong prefix), the suggestion includes the expected prefix applied to the current name.

---

## 13. Testing Strategy

### 13.1 Rust Unit Tests

Every checker has dedicated tests with fixture files:

```rust
#[cfg(test)]
mod tests {
    use super::*;
    use indoc::indoc;

    #[test]
    fn test_hdr001_missing_name() {
        let sql = indoc! {"
            -- kind: FULL_REFRESH
            SELECT 1
        "};
        let diags = SqlHeaderChecker.check_file("test.sql", sql, None, &CheckConfig::default());
        assert_eq!(diags.len(), 1);
        assert_eq!(diags[0].rule_id, "HDR001");
        assert_eq!(diags[0].severity, Severity::Error);
    }

    #[test]
    fn test_ref001_undefined_ref() {
        let models = vec![
            DiscoveredModel { name: "stg_orders".into(), .. },
        ];
        let sql = "SELECT * FROM {{ ref('stg_nonexistent') }}";
        let diags = RefChecker.check_project(&models, &CheckConfig::default());
        assert_eq!(diags[0].rule_id, "REF001");
    }
}
```

### 13.2 Integration Tests

End-to-end tests using real project fixtures:

```
tests/fixtures/
├── ironlayer_project/        # Full IronLayer project with intentional errors
│   ├── ironlayer.yaml
│   ├── models/
│   │   ├── staging/
│   │   │   ├── stg_orders.sql        # Valid
│   │   │   └── stg_bad_ref.sql       # Has REF001 error
│   │   └── marts/
│   │       ├── fct_revenue.sql       # Missing unique_key (HDR006)
│   │       └── wrong_name.sql        # NAME003 violation
│   └── schema.yml                    # YML005 violation
├── dbt_project/              # Full dbt project
│   ├── dbt_project.yml
│   ├── models/
│   └── schema.yml
└── empty_project/            # Edge case: no files
```

### 13.3 Python Integration Tests

Test the PyO3 bridge from Python:

```python
def test_check_engine_basic():
    from ironlayer_check_engine import quick_check
    result = quick_check("tests/fixtures/ironlayer_project")
    assert not result.passed
    assert result.total_errors >= 2
    assert any(d.rule_id == "REF001" for d in result.diagnostics)

def test_check_engine_config():
    from ironlayer_check_engine import CheckEngine, CheckConfig
    config = CheckConfig()
    config.rules = {"SQL004": "off"}  # Disable SELECT * warning
    engine = CheckEngine(config)
    result = engine.check("tests/fixtures/ironlayer_project")
    assert not any(d.rule_id == "SQL004" for d in result.diagnostics)
```

### 13.4 Benchmark Tests

```rust
use criterion::{criterion_group, criterion_main, Criterion};

fn bench_500_models(c: &mut Criterion) {
    // Generate 500 synthetic SQL model files in a temp directory
    let dir = generate_test_project(500);
    let config = CheckConfig::default();
    let engine = CheckEngine::new(config);

    c.bench_function("check_500_models_cold", |b| {
        b.iter(|| {
            engine.clear_cache();
            engine.check(dir.path())
        })
    });

    // Warm cache
    engine.check(dir.path());
    c.bench_function("check_500_models_warm", |b| {
        b.iter(|| engine.check(dir.path()))
    });
}
```

---

## 14. Packaging & Distribution

### 14.1 Wheel Structure After Build

```
ironlayer_core-0.3.0-cp311-abi3-manylinux_2_17_x86_64.manylinux2014_x86_64.whl
├── core_engine/                    (existing Python modules, unchanged)
│   ├── __init__.py
│   ├── config.py
│   ├── models/
│   ├── parser/
│   ├── loader/
│   ├── ... (all existing modules)
├── ironlayer_check_engine.cpython-311-x86_64-linux-gnu.so  (NEW: Rust extension)
├── ironlayer_check_engine.pyi      (NEW: type stubs)
└── ironlayer_core-0.3.0.dist-info/
    ├── METADATA
    ├── WHEEL
    └── RECORD
```

### 14.2 Platform Wheels to Build

| Platform | Target | Notes |
|---|---|---|
| Linux x86_64 | `x86_64-unknown-linux-gnu` | manylinux2014 |
| Linux aarch64 | `aarch64-unknown-linux-gnu` | manylinux2014 |
| macOS x86_64 | `x86_64-apple-darwin` | Intel Macs |
| macOS aarch64 | `aarch64-apple-darwin` | Apple Silicon |
| Windows x86_64 | `x86_64-pc-windows-msvc` | MSVC toolchain |

### 14.3 CI/CD (GitHub Actions)

```yaml
# .github/workflows/build-wheels.yml
name: Build Wheels
on:
  push:
    tags: ['v*']

jobs:
  build:
    strategy:
      matrix:
        os: [ubuntu-latest, macos-latest, windows-latest]
        target: [x86_64, aarch64]
        exclude:
          - os: windows-latest
            target: aarch64
    runs-on: ${{ matrix.os }}
    steps:
      - uses: actions/checkout@v4
      - uses: PyO3/maturin-action@v1
        with:
          target: ${{ matrix.target }}
          args: --release --out dist -m check_engine/Cargo.toml
          manylinux: 2014
      - uses: actions/upload-artifact@v4
        with:
          name: wheels-${{ matrix.os }}-${{ matrix.target }}
          path: dist/*.whl
```

### 14.4 Fallback for Unsupported Platforms

If the Rust extension fails to import (e.g., user on an unsupported platform), the `ironlayer check` command gracefully falls back to a pure Python implementation using existing `core_engine` modules:

```python
try:
    from ironlayer_check_engine import CheckEngine
    _RUST_AVAILABLE = True
except ImportError:
    _RUST_AVAILABLE = False

# In the check command:
if _RUST_AVAILABLE:
    result = engine.check(str(repo))
else:
    console.print("[yellow]Note: Rust check engine unavailable, using Python fallback (slower).[/yellow]")
    result = _python_fallback_check(repo)
```

The Python fallback reuses existing modules (`model_loader`, `ref_resolver`, `sql_guard`, `schema_validator`) but runs sequentially. This is slower but ensures `ironlayer check` works everywhere.

---

## 15. Migration Path from Existing Tools

### 15.1 From SQLFluff

```bash
# Before:
sqlfluff lint models/ --dialect databricks    # 47 seconds

# After:
ironlayer check .                              # 0.3 seconds
```

`ironlayer check` is NOT a drop-in replacement for SQLFluff. SQLFluff does full SQL linting (indentation, aliasing, keyword casing, etc.). IronLayer check focuses on **correctness** (broken refs, invalid headers, missing tests, safety violations) rather than **style**. They are complementary.

For teams migrating from SQLFluff, the recommended setup is:
1. `ironlayer check` in pre-commit (fast, catches real bugs)
2. SQLFluff in CI (thorough, catches style issues)

### 15.2 From pre-commit

```yaml
# .pre-commit-config.yaml — BEFORE (slow, spawns Python processes)
repos:
  - repo: https://github.com/sqlfluff/sqlfluff
    rev: 3.0.0
    hooks:
      - id: sqlfluff-lint
  - repo: https://github.com/pre-commit/pre-commit-hooks
    rev: v4.5.0
    hooks:
      - id: check-yaml
      - id: trailing-whitespace

# AFTER (single fast binary)
repos:
  - repo: https://github.com/ironlayer/ironlayer
    rev: v0.3.0
    hooks:
      - id: ironlayer-check
        entry: ironlayer check --changed-only
        language: python
        types: [sql, yaml]
```

---

## 16. Future: IronLayer Cloud Integration

### 16.1 `--ironlayer` Flag (v0.4.0)

When authenticated via `ironlayer login`, the `--ironlayer` flag sends check results to the cloud API for enhanced diagnostics:

```bash
ironlayer check . --ironlayer

⚡ IronLayer Check — FAILED  (312ms, +1.2s cloud)

  models/staging/stg_orders.sql
    ✗ REF001 :14  Undefined ref: 'raw.orders_v2'
      → Did you mean 'raw_orders_v2'? (Levenshtein distance: 1)

  ⚡ Plan preview: 3 models + 7 downstream affected
  💰 Estimated cost: $1.24 (Databricks DBUs)
  ⚠️ Risk: medium (4 dashboards depend on changed models)
  💡 AI suggestion: Add WHERE clause to stg_orders to reduce scan 60%

── 1 error, 0 warnings  (312ms local + 1.2s cloud)
```

### 16.2 MCP Integration (v0.4.0)

The check engine results are exposed via the existing MCP server (`cli/mcp/tools.py`) as a new tool:

```python
# New MCP tool in cli/mcp/tools.py
@tool("ironlayer_check")
async def check_project(path: str, fix: bool = False) -> dict:
    """Run IronLayer check on a project directory."""
    from ironlayer_check_engine import quick_check
    result = quick_check(path)
    return result.to_dict()
```

This allows AI coding agents (Claude, Cursor, Copilot) to call `ironlayer_check` between code generation and commit.

---

## 17. Implementation Phases

### Phase 1: Foundation (Week 1-2)

**Goal:** Rust crate builds, PyO3 bindings work, one checker runs end-to-end.

- [ ] Workspace `Cargo.toml` + `check_engine/Cargo.toml`
- [ ] `types.rs`: All type definitions
- [ ] `discovery.rs`: File walker + project type detection
- [ ] `config.rs`: Config loading from TOML
- [ ] `cache.rs`: Content-addressable cache
- [ ] `checkers/sql_header.rs`: HDR001-HDR013
- [ ] `pyo3_bindings.rs`: Module definition + `CheckEngine` class
- [ ] `engine.rs`: Sequential orchestrator (no parallelism yet)
- [ ] Integration: `cli/app.py` `check` command wired up
- [ ] Maturin build produces working wheel
- [ ] 5 unit tests per checker

### Phase 2: Core Checkers (Week 3-4)

**Goal:** All high-value checks working. Ready for internal dogfooding on IronLayer's own repo.

- [ ] `sql_lexer.rs`: Token stream for SQL files
- [ ] `checkers/sql_syntax.rs`: SQL001-SQL009
- [ ] `checkers/sql_safety.rs`: SAF001-SAF010
- [ ] `checkers/ref_resolver.rs`: REF001-REF006
- [ ] `checkers/naming.rs`: NAME001-NAME008
- [ ] `engine.rs`: Switch to `rayon` parallel execution
- [ ] `reporter.rs`: JSON output
- [ ] `cache.rs`: Cache persistence + invalidation
- [ ] Benchmark: confirm <500ms on 500-model project

### Phase 3: YAML & dbt (Week 5-6)

**Goal:** Full dbt project support. Ready for public beta.

- [ ] `checkers/yaml_schema.rs`: YML001-YML009
- [ ] `checkers/dbt_project.rs`: DBT001-DBT006
- [ ] `checkers/model_consistency.rs`: CON001-CON005
- [ ] `reporter.rs`: SARIF output
- [ ] Per-path config overrides
- [ ] `--changed-only` git integration
- [ ] `--fix` for fixable rules (SQL007, SQL009, HDR013, REF004)
- [ ] Python fallback implementation
- [ ] pre-commit hook configuration
- [ ] Integration test suite with fixture projects

### Phase 4: Polish & Launch (Week 7-8)

**Goal:** PyPI release, GitHub Actions, documentation, launch post.

- [ ] CI/CD: Build wheels for all 5 platforms
- [ ] Type stubs (`ironlayer_check_engine.pyi`)
- [ ] Documentation site pages for every rule
- [ ] Benchmark blog post: "500 dbt models in 0.3s"
- [ ] GitHub Action: `ironlayer/check-action@v1`
- [ ] pre-commit integration tested
- [ ] `ironlayer-core` v0.3.0 published to PyPI
- [ ] `ironlayer` v0.3.0 published to PyPI
- [ ] HN/Twitter/Reddit launch

---

## Appendix A: SQL Lexer Token Types

```rust
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum TokenKind {
    // Keywords (uppercased for matching)
    Keyword,        // SELECT, FROM, WHERE, INSERT, DELETE, DROP, etc.

    // Identifiers
    Identifier,     // table_name, column_name
    QuotedIdent,    // `backtick_quoted` or "double_quoted"

    // Literals
    StringLiteral,  // 'single quoted string'
    NumberLiteral,  // 42, 3.14, 1e10

    // Operators
    Operator,       // =, <>, !=, >=, <=, +, -, *, /

    // Punctuation
    LeftParen,
    RightParen,
    Comma,
    Semicolon,
    Dot,

    // Comments
    LineComment,    // -- ...
    BlockComment,   // /* ... */

    // Templates
    JinjaOpen,      // {{
    JinjaClose,     // }}
    JinjaBlock,     // {% ... %}

    // Whitespace
    Whitespace,
    Newline,

    // Unknown
    Unknown,
}

pub struct Token<'a> {
    pub kind: TokenKind,
    pub text: &'a str,      // Zero-copy slice into source
    pub offset: usize,      // Byte offset in source
    pub line: u32,           // 1-based line number
    pub column: u32,         // 1-based column number
}
```

The lexer correctly handles:
- Nested `/* /* */ */` block comments
- String escaping: `'it''s'` (doubled single quote)
- Jinja templates: `{{ ... }}`, `{% ... %}`, `{# ... #}`
- Databricks-specific: backtick quoting, `$` in identifiers
- Unicode identifiers

---

## Appendix B: Compatibility Matrix

| IronLayer Feature | Check Engine Interaction |
|---|---|
| `ironlayer plan` | Check can run as a pre-step: `ironlayer check . && ironlayer plan ...` |
| `ironlayer apply` | No direct interaction |
| `ironlayer models` | Check uses same model discovery logic |
| `ironlayer lineage` | No direct interaction (lineage needs full AST) |
| `ironlayer dev` | Dev server could auto-run check on file save (future) |
| `ironlayer init` | Init generates `ironlayer.check.toml` template |
| `ironlayer migrate from-dbt` | After migration, `ironlayer check` validates migrated models |
| `ironlayer mcp serve` | Check exposed as MCP tool |
| Cloud login | Enables `--ironlayer` enhanced diagnostics |
| Schema contracts | Check validates contract headers (HDR010-HDR011), Python validates actual columns |
| SQL Guard | Check pre-screens (SAF rules), Python does full AST analysis at plan time |

---

## Appendix C: Glossary

| Term | Definition |
|---|---|
| **Check** | A validation pass that reports diagnostics without modifying files |
| **Diagnostic** | A single issue found by a checker (error, warning, or info) |
| **Checker** | A Rust struct implementing the `Checker` trait |
| **Rule** | A specific validation rule with a stable ID (e.g., REF001) |
| **Category** | A group of related rules (e.g., RefResolution) |
| **Project type** | Auto-detected framework: IronLayer, dbt, or raw SQL |
| **Content hash** | SHA-256 of file content, used for caching |
| **Model registry** | Map from model short/canonical names to canonical names |

---

## Appendix D: Platform & Robustness Concerns

### D.1 Rust Panic Recovery

The check engine uses `rayon` for parallel file checking. If a checker panics (e.g., regex compilation failure, unexpected input causing an index-out-of-bounds), rayon propagates the panic to the calling thread, which would crash the Python process.

**Mitigation:** Every per-file check is wrapped in `std::panic::catch_unwind`:

```rust
// In engine.rs — per-file check dispatch
let file_diags: Vec<CheckDiagnostic> = uncached
    .par_iter()
    .flat_map(|file| {
        match std::panic::catch_unwind(std::panic::AssertUnwindSafe(|| {
            self.run_file_checks(file)
        })) {
            Ok(diags) => diags,
            Err(_) => {
                // Panic caught — emit a single diagnostic instead of crashing
                vec![CheckDiagnostic {
                    rule_id: "INTERNAL".into(),
                    message: format!("Internal error: checker panicked on '{}'", file.rel_path),
                    severity: Severity::Error,
                    category: CheckCategory::FileStructure,
                    file_path: file.rel_path.clone(),
                    line: 0,
                    column: 0,
                    snippet: None,
                    suggestion: Some("Please report this as a bug at https://github.com/ironlayer/ironlayer/issues".into()),
                    doc_url: None,
                }]
            }
        }
    })
    .collect();
```

Cross-file checks (`check_project()`) run sequentially and are also wrapped in `catch_unwind`. A panic in one checker does not prevent other checkers from running.

### D.2 Windows Path Handling

All `file_path` values in `CheckDiagnostic` and `CheckResult` use **forward slashes** regardless of platform. This ensures:
- JSON and SARIF output is consistent across platforms
- GitHub Code Scanning (SARIF) expects forward-slash paths
- Rich console output on Windows still renders correctly (Windows APIs accept forward slashes)

Implementation: After file discovery, all paths are normalized via:
```rust
fn normalize_path(path: &Path, root: &Path) -> String {
    path.strip_prefix(root)
        .unwrap_or(path)
        .to_string_lossy()
        .replace('\\', "/")
}
```

The cache file (`.ironlayer/check_cache.json`) also uses forward-slash keys. This means a cache generated on Windows is valid on macOS/Linux and vice versa.

### D.3 Unicode File Content

SQL files may contain Unicode characters in comments, string literals, or identifiers (especially Databricks backtick-quoted identifiers). The engine:
- Reads all files as UTF-8. Non-UTF-8 files emit `SQL008` (empty SQL body) with a message: "File is not valid UTF-8."
- The SQL lexer operates on `&str` (guaranteed UTF-8 in Rust), using byte offsets internally but reporting line/column in terms of Unicode scalar values.
- File paths with Unicode characters are supported on all platforms via `std::path::Path`.

---

*End of specification. This document is the single source of truth for the IronLayer Check Engine implementation. All implementation decisions not covered here should be escalated before coding.*

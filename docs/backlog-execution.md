# Backlog Execution — ironlayer_oss

Ordered list of PR-sized work items. Status key: `[ ]` not started · `[~]` in progress · `[x]` merged · `[-]` cancelled

---

### OSS-01: Add SQLMesh model loader to core_engine
- **Branch:** `feat/sqlmesh-loader`
- **What:** Implement a SQLMesh model file parser in core_engine that reads SQLMesh Python and SQL model definitions, extracts table references and column lineage, and feeds them into the existing DAG builder. This enables IronLayer to generate execution plans for SQLMesh projects. Part of I-24 (SQLMesh parity).
- **Key files:** `core_engine/core_engine/loaders/sqlmesh_loader.py`, `core_engine/core_engine/loaders/__init__.py`, `tests/test_sqlmesh_loader.py`
- **Acceptance:** Loader parses SQLMesh `model()` definitions and `@model` decorators; extracted tables appear in DAG; unit tests with sample SQLMesh models pass
- **Depends on:** None
- **Status:** [ ]

### OSS-02: Implement transformation framework auto-detector
- **Branch:** `feat/framework-auto-detect`
- **What:** Create a utility that inspects a project directory and detects whether it uses dbt Core, SQLMesh, or raw SQL based on config files (`dbt_project.yml`, `config.yaml` with gateway, `*.sql` patterns). Returns framework enum. Part of I-34 (Transformation Framework Expansion).
- **Key files:** `core_engine/core_engine/detect.py`, `tests/test_framework_detection.py`
- **Acceptance:** Detects dbt (`dbt_project.yml`), SQLMesh (`config.yaml` with gateway key), and raw SQL (fallback); 100% test coverage on detection logic
- **Depends on:** None
- **Status:** [ ]

### OSS-03: Add data diff CLI command
- **Branch:** `feat/data-diff-cli`
- **What:** Add `ironlayer diff` CLI command that compares two table snapshots (before/after a plan) and outputs row-level and schema-level differences. Uses SQLAlchemy async to query both states. Part of I-19 (Data Diff Engine — Datafold parity).
- **Key files:** `cli/cli/commands/diff.py`, `core_engine/core_engine/diff/table_diff.py`, `tests/test_diff_command.py`
- **Acceptance:** `ironlayer diff --table X --before Y --after Z` outputs schema changes and row count delta; supports Databricks and Postgres backends; unit tests pass
- **Depends on:** None
- **Status:** [ ]

### OSS-04: SQLMesh SQL rewrite via SQLGlot in check_engine
- **Branch:** `feat/sqlmesh-check-rules`
- **What:** Extend the Rust check_engine with SQLMesh-aware validation rules. SQLMesh models use SQLGlot transpilation — add rules that validate SQLMesh-specific patterns (incremental_by_time_range, SCD Type 2, forward-only changes). Part of I-24 Epic 24.2.
- **Key files:** `check_engine/src/rules/sqlmesh.rs`, `check_engine/src/rules/mod.rs`, `check_engine/tests/test_sqlmesh_rules.rs`
- **Acceptance:** At least 5 SQLMesh-specific rules implemented; `cargo test` passes; rules produce WARN/BLOCK severity output
- **Depends on:** OSS-01
- **Status:** [ ]

### OSS-05: Complete remaining CLI commands (plan, apply, check, lineage)
- **Branch:** `feat/cli-completion`
- **What:** Audit the CLI for stub or incomplete commands and implement the missing logic. Per I-34, 9 commands should be fully functional: plan, apply, diff, check, lineage, status, config, init, version. Fill in any that return NotImplementedError or placeholder output.
- **Key files:** `cli/cli/commands/plan.py`, `cli/cli/commands/apply.py`, `cli/cli/commands/check.py`, `cli/cli/commands/lineage.py`, `tests/test_cli_commands.py`
- **Acceptance:** All 9 CLI commands return real output (not stubs); `ironlayer --help` lists all commands; integration tests cover each command's happy path
- **Depends on:** OSS-01, OSS-02
- **Status:** [ ]

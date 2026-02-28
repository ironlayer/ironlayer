# Skill: Audit Check Engine

## When to Use

Use this skill when auditing the check engine implementation for correctness, completeness, security, and adherence to IronLayer's architectural patterns.

## Audit Checklist

### 1. Determinism Audit

- [ ] All check results sorted deterministically (by model_name, then check_type, then column_name)
- [ ] No use of `random`, `uuid4()`, or non-deterministic timestamps in core logic
- [ ] Content-based IDs use `compute_deterministic_id()` from `core_engine.models.plan`
- [ ] Collections use `sorted()` with explicit key functions
- [ ] JSON serialization uses `sort_keys=True` where applicable

### 2. Security Audit

- [ ] SQL identifiers validated against `_SAFE_IDENTIFIER_RE` allowlist before interpolation
- [ ] No raw string formatting of user input into SQL queries
- [ ] RBAC permissions enforced on all API endpoints (`Permission.RUN_CHECKS`, `Permission.READ_CHECK_RESULTS`)
- [ ] Feature gating applied (`Feature.CHECK_ENGINE`) for billing tier control
- [ ] Multi-tenant RLS: all database queries scoped to `tenant_id`
- [ ] No secrets or credentials in check results or logs

### 3. Architecture Audit

- [ ] Check engine lives in `core_engine/core_engine/checks/` (not in api/ or cli/)
- [ ] API service layer in `api/api/services/check_service.py` delegates to core engine
- [ ] Router in `api/api/routers/checks.py` handles HTTP concerns only
- [ ] CLI command in `cli/cli/commands/check.py` handles terminal I/O only
- [ ] No circular imports between modules
- [ ] `BaseCheck` abstract class properly defines the check protocol
- [ ] `CheckRegistry` allows runtime registration of check types
- [ ] `CheckEngine` orchestrates without knowledge of specific check implementations

### 4. Data Model Audit

- [ ] `CheckType` enum covers all check categories
- [ ] `CheckStatus` enum has PASS, FAIL, WARN, ERROR, SKIP values
- [ ] `CheckSeverity` enum has CRITICAL, HIGH, MEDIUM, LOW values
- [ ] `CheckResult` model has: check_type, model_name, status, severity, message, duration_ms
- [ ] `CheckSummary` model aggregates total, passed, failed, warned, errored, skipped counts
- [ ] All Pydantic models use `Field()` with descriptions

### 5. Integration Audit

- [ ] Built-in `ModelTestCheck` correctly wraps `ModelTestRunner`
- [ ] Built-in `SchemaContractCheck` correctly wraps `validate_schema_contract()`
- [ ] Check results are compatible with existing `test_results` table schema
- [ ] API response format consistent with existing `/tests/` endpoints
- [ ] CLI output follows Rich console patterns (stderr for humans, files for machines)

### 6. Test Coverage Audit

- [ ] Unit tests exist in `core_engine/tests/unit/test_check_engine.py`
- [ ] Tests cover: check registration, execution, result aggregation, error handling
- [ ] Tests verify deterministic ordering of results
- [ ] Tests verify all check statuses (PASS, FAIL, WARN, ERROR, SKIP)
- [ ] Tests verify severity levels are respected
- [ ] Edge cases: empty model list, no checks registered, all checks fail, mixed results

### 7. API Completeness Audit

Verify these endpoints exist and work correctly:

- [ ] `POST /checks/run` — Run checks for specified models/check types
- [ ] `GET /checks/results/{plan_id}` — Get check results for a plan
- [ ] `GET /checks/summary` — Get aggregate check statistics
- [ ] `GET /checks/types` — List available check types

### 8. CLI Completeness Audit

Verify these commands work:

- [ ] `ironlayer check` — Run all checks
- [ ] `ironlayer check --model <name>` — Run checks for a specific model
- [ ] `ironlayer check --type <type>` — Run a specific check type
- [ ] `ironlayer check --severity <level>` — Filter by minimum severity

## How to Run the Audit

1. Read all files in `core_engine/core_engine/checks/`
2. Read `api/api/routers/checks.py` and `api/api/services/check_service.py`
3. Read `cli/cli/commands/check.py`
4. Read `core_engine/tests/unit/test_check_engine.py`
5. Run through each section of the checklist above
6. Report findings with file paths and line numbers
7. Categorize issues as: CRITICAL (must fix), WARNING (should fix), INFO (nice to have)

## Common Issues to Watch For

1. **Mutable default arguments** in Pydantic models — use `default_factory`
2. **Missing `await`** on async calls in check implementations
3. **Unsorted results** — every list of results must be sorted deterministically
4. **Missing error handling** — checks that raise should be caught and return `ERROR` status
5. **Tight coupling** — check implementations should not import from `api/` or `cli/`
6. **Missing tenant scoping** — all database queries must include `tenant_id` filter

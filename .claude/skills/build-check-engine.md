# Skill: Build Check Engine

## When to Use

Use this skill when building new check engine components, adding check types, or extending the check engine framework.

## Context

The Check Engine is a unified quality and validation framework in IronLayer. It lives at `core_engine/core_engine/checks/` and orchestrates all data quality checks through a single interface.

## Architecture

```
core_engine/core_engine/checks/
├── __init__.py          # Public API exports
├── models.py            # CheckType, CheckStatus, CheckSeverity, CheckResult, CheckSummary
├── base.py              # BaseCheck abstract class
├── registry.py          # CheckRegistry for check type registration
├── engine.py            # CheckEngine orchestrator
└── builtin/             # Built-in check implementations
    ├── __init__.py
    ├── model_tests.py   # Wraps ModelTestRunner
    └── schema_contracts.py  # Wraps validate_schema_contract()
```

## Patterns to Follow

### Creating a New Check Type

1. Create a new file in `core_engine/core_engine/checks/builtin/<check_name>.py`
2. Subclass `BaseCheck` from `core_engine.checks.base`
3. Implement `check_type` property returning a `CheckType` enum value
4. Implement `async execute(self, context: CheckContext) -> list[CheckResult]`
5. Register the check in `CheckRegistry` via `registry.register()`
6. Add the `CheckType` enum value to `core_engine/core_engine/checks/models.py`
7. Add unit tests in `core_engine/tests/unit/test_check_<name>.py`

### Check Implementation Template

```python
from __future__ import annotations

from core_engine.checks.base import BaseCheck, CheckContext
from core_engine.checks.models import CheckResult, CheckSeverity, CheckStatus, CheckType


class MyNewCheck(BaseCheck):
    """Description of what this check validates."""

    @property
    def check_type(self) -> CheckType:
        return CheckType.MY_CHECK_TYPE

    async def execute(self, context: CheckContext) -> list[CheckResult]:
        results: list[CheckResult] = []
        for model in sorted(context.models, key=lambda m: m.name):
            # Perform validation logic
            result = CheckResult(
                check_type=self.check_type,
                model_name=model.name,
                status=CheckStatus.PASS,
                severity=CheckSeverity.MEDIUM,
                message="Check passed",
            )
            results.append(result)
        return results
```

### Key Invariants

- All results sorted deterministically (by model_name, then check_type)
- Use `compute_deterministic_id()` for any generated IDs
- All methods are `async`
- Follow Pydantic `BaseModel` patterns with `Field()` descriptions
- Check implementations must be stateless — context passed via `CheckContext`
- Never mutate model definitions or plan state from within a check

### API Endpoint Pattern

```python
@router.post("/run")
async def run_checks(
    body: RunChecksRequest,
    session: SessionDep,
    tenant_id: TenantDep,
    _role: Role = Depends(require_permission(Permission.RUN_CHECKS)),
) -> CheckSummaryResponse:
    service = CheckService(session, tenant_id=tenant_id)
    return await service.run_checks(body.model_names, body.check_types)
```

### CLI Command Pattern

```python
@app.command()
def check(
    model_dir: Path = typer.Option(...),
    model_name: str | None = typer.Option(None),
    check_type: str | None = typer.Option(None),
):
    """Run quality checks against models."""
```

## Existing Infrastructure to Integrate

- `core_engine/testing/test_runner.py` — `ModelTestRunner` class (NOT_NULL, UNIQUE, ROW_COUNT, ACCEPTED_VALUES, CUSTOM_SQL)
- `core_engine/contracts/schema_validator.py` — `validate_schema_contract()` function
- `core_engine/executor/schema_introspector.py` — `compare_schemas()`, `compare_with_contracts()`
- `core_engine/models/model_definition.py` — `ModelTestType`, `ModelTestDefinition`, `SchemaContractMode`, `ColumnContract`

## Testing

- Unit tests go in `core_engine/tests/unit/test_check_engine.py`
- Follow existing test patterns: pytest fixtures, async test methods
- Test determinism: same input must produce identical output
- Test error handling: checks that fail to execute should return `CheckStatus.ERROR`
- Test sorting: results must be deterministically ordered

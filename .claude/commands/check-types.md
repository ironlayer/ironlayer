# Skill: Build Check Types

## When to Use

Use this skill when adding new check types to the check engine beyond the built-in Phase 1 types (model tests, schema contracts).

## Available Check Types by Phase

### Phase 1 (Built-in) — Already Implemented

| Check Type | File | Wraps |
|-----------|------|-------|
| `MODEL_TEST` | `checks/builtin/model_tests.py` | `ModelTestRunner` |
| `SCHEMA_CONTRACT` | `checks/builtin/schema_contracts.py` | `validate_schema_contract()` |

### Phase 2 (Extended) — To Build

| Check Type | File | Description |
|-----------|------|-------------|
| `SCHEMA_DRIFT` | `checks/builtin/schema_drift.py` | Compare expected vs actual warehouse schemas |
| `RECONCILIATION` | `checks/builtin/reconciliation.py` | Control-plane vs warehouse status |
| `DATA_FRESHNESS` | `checks/builtin/data_freshness.py` | Alert when data is stale beyond threshold |
| `CROSS_MODEL` | `checks/builtin/cross_model.py` | Validate referential integrity between models |
| `VOLUME_ANOMALY` | `checks/builtin/volume_anomaly.py` | Statistical row count deviation detection |
| `CUSTOM` | `checks/builtin/custom_sql.py` | User-defined SQL validation rules |

## Implementation Guide for Each Type

### SCHEMA_DRIFT Check

```python
# Wraps core_engine/executor/schema_introspector.py
# Uses compare_schemas() and compare_with_contracts()
# Requires actual warehouse schema (passed via CheckContext)
# Maps SchemaDrift results to CheckResult
```

Key integration:
- Import `compare_schemas`, `compare_with_contracts` from `core_engine.executor.schema_introspector`
- Each drift becomes a `CheckResult` with appropriate severity
- `COLUMN_REMOVED` → `CheckSeverity.CRITICAL`
- `TYPE_CHANGED` → `CheckSeverity.HIGH`
- `COLUMN_ADDED` → `CheckSeverity.LOW`

### DATA_FRESHNESS Check

```python
# Queries the watermark table for last-updated timestamps
# Compares against configurable staleness thresholds
# Default threshold: 24 hours for daily models, 1 hour for hourly
```

Config model:
```python
class FreshnessConfig(BaseModel):
    max_staleness_hours: int = 24
    time_column: str | None = None  # Falls back to model.time_column
```

### CROSS_MODEL Check

```python
# Uses the DAG to identify upstream dependencies
# Validates that referenced models exist and have recent successful runs
# Checks referential integrity between joined models
```

### VOLUME_ANOMALY Check

```python
# Compares current row count against historical average
# Uses standard deviation to detect anomalies
# Configurable sensitivity (default: 2 standard deviations)
```

Config model:
```python
class VolumeAnomalyConfig(BaseModel):
    lookback_days: int = 30
    std_dev_threshold: float = 2.0
    min_samples: int = 7  # Need at least 7 data points
```

## Adding a Check Type Step-by-Step

1. **Add enum value** to `CheckType` in `core_engine/checks/models.py`
2. **Create implementation** in `core_engine/checks/builtin/<name>.py`
3. **Register in engine** — Add to default registrations in `CheckEngine.__init__`
4. **Add unit tests** in `core_engine/tests/unit/test_check_<name>.py`
5. **Update CLI** — Add to `--type` choices in `cli/cli/commands/check.py`
6. **Update API** — Ensure `/checks/types` endpoint returns the new type
7. **Update CLAUDE.md** — Document the new check type

## Testing New Check Types

```python
import pytest
from core_engine.checks.builtin.my_check import MyCheck
from core_engine.checks.models import CheckContext, CheckStatus

@pytest.mark.asyncio
async def test_my_check_pass():
    check = MyCheck()
    context = CheckContext(models=[...])
    results = await check.execute(context)
    assert all(r.status == CheckStatus.PASS for r in results)

@pytest.mark.asyncio
async def test_my_check_fail():
    check = MyCheck()
    context = CheckContext(models=[...])  # with violations
    results = await check.execute(context)
    assert any(r.status == CheckStatus.FAIL for r in results)

@pytest.mark.asyncio
async def test_my_check_deterministic():
    check = MyCheck()
    context = CheckContext(models=[...])
    r1 = await check.execute(context)
    r2 = await check.execute(context)
    assert r1 == r2  # Exact same output
```

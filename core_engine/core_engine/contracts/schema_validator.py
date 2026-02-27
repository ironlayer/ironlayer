"""Schema contract validator for IronLayer model output columns.

Compares declared column contracts (from SQL model headers) against the
actual output columns produced by a model's SELECT statement.  Returns a
structured result containing any violations.

Violation types
---------------
* **COLUMN_REMOVED** — a contracted column is missing from the output.
  Severity: BREAKING.
* **TYPE_CHANGED** — a column exists but its data type doesn't match the
  contract.  Severity: BREAKING.
* **NULLABLE_TIGHTENED** — a column was declared NOT NULL in the contract but
  the output column allows NULLs (or vice-versa, the contract allows NULLs
  but the column became NOT NULL).  Severity: BREAKING when tightened.
* **COLUMN_ADDED** — a column not in the contract appeared in the output.
  Severity: INFO (additive changes are non-breaking).

All collections are sorted deterministically (by model_name, then column_name)
to maintain the plan determinism invariant.
"""

from __future__ import annotations

import logging
from enum import Enum

from pydantic import BaseModel, Field

from core_engine.models.model_definition import ModelDefinition, SchemaContractMode

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Violation models
# ---------------------------------------------------------------------------


class ViolationSeverity(str, Enum):
    """How critical a contract violation is."""

    BREAKING = "BREAKING"
    WARNING = "WARNING"
    INFO = "INFO"


class ContractViolation(BaseModel):
    """A single schema contract violation."""

    model_name: str = Field(..., description="Canonical model name where the violation was detected.")
    column_name: str = Field(..., description="Column involved in the violation.")
    violation_type: str = Field(
        ...,
        description="Type of violation: COLUMN_REMOVED, TYPE_CHANGED, NULLABLE_TIGHTENED, COLUMN_ADDED.",
    )
    severity: ViolationSeverity = Field(..., description="How critical this violation is.")
    expected: str = Field(
        default="",
        description="What the contract declared (type, nullability, or existence).",
    )
    actual: str = Field(
        default="",
        description="What was actually found in the output columns.",
    )
    message: str = Field(
        default="",
        description="Human-readable description of the violation.",
    )


class ContractValidationResult(BaseModel):
    """Result of validating schema contracts for one or more models."""

    violations: list[ContractViolation] = Field(
        default_factory=list,
        description="All detected violations, sorted deterministically.",
    )
    models_checked: int = Field(
        default=0,
        description="Number of models that had contracts checked.",
    )

    @property
    def has_breaking_violations(self) -> bool:
        """Return True if any violation is severity BREAKING."""
        return any(v.severity == ViolationSeverity.BREAKING for v in self.violations)

    @property
    def breaking_count(self) -> int:
        """Count of BREAKING violations."""
        return sum(1 for v in self.violations if v.severity == ViolationSeverity.BREAKING)

    @property
    def warning_count(self) -> int:
        """Count of WARNING violations."""
        return sum(1 for v in self.violations if v.severity == ViolationSeverity.WARNING)

    @property
    def info_count(self) -> int:
        """Count of INFO violations."""
        return sum(1 for v in self.violations if v.severity == ViolationSeverity.INFO)

    def violations_for_model(self, model_name: str) -> list[ContractViolation]:
        """Return violations filtered to a specific model."""
        return [v for v in self.violations if v.model_name == model_name]


# ---------------------------------------------------------------------------
# Type compatibility
# ---------------------------------------------------------------------------

# Canonical type aliases for normalization.
_TYPE_ALIASES: dict[str, str] = {
    "INTEGER": "INT",
    "BIGINTEGER": "BIGINT",
    "LONG": "BIGINT",
    "SHORT": "SMALLINT",
    "TINYINT": "SMALLINT",
    "REAL": "FLOAT",
    "DOUBLE PRECISION": "DOUBLE",
    "VARCHAR": "STRING",
    "TEXT": "STRING",
    "CHAR": "STRING",
    "NVARCHAR": "STRING",
    "DATETIME": "TIMESTAMP",
    "BOOL": "BOOLEAN",
    "NUMERIC": "DECIMAL",
    "NUMBER": "DECIMAL",
}


def _normalize_type(data_type: str) -> str:
    """Normalize a data type string for comparison.

    Strips whitespace, upper-cases, and applies canonical aliases so that
    ``VARCHAR`` and ``STRING`` (or ``INTEGER`` and ``INT``) compare as equal.
    """
    normalized = data_type.strip().upper()
    return _TYPE_ALIASES.get(normalized, normalized)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def validate_schema_contract(
    model: ModelDefinition,
    actual_columns: list[str] | None = None,
    actual_column_types: dict[str, str] | None = None,
    actual_column_nullability: dict[str, bool] | None = None,
) -> ContractValidationResult:
    """Validate a model's output against its declared schema contract.

    Parameters
    ----------
    model:
        The model definition containing ``contract_columns`` and
        ``contract_mode``.
    actual_columns:
        List of column names actually produced by the model's SELECT.
        When ``None``, falls back to ``model.output_columns``.
    actual_column_types:
        Optional mapping of ``column_name -> data_type``.  When provided,
        type-mismatch violations can be detected.  When ``None``, only
        column presence/absence is checked.
    actual_column_nullability:
        Optional mapping of ``column_name -> nullable``.  When provided,
        nullability violations can be detected.  When ``None``, nullability
        checks are skipped.

    Returns
    -------
    ContractValidationResult
        The validation result with any violations detected.
    """
    if model.contract_mode == SchemaContractMode.DISABLED:
        return ContractValidationResult(models_checked=0)

    if not model.contract_columns:
        return ContractValidationResult(models_checked=1)

    columns = actual_columns if actual_columns is not None else model.output_columns
    columns_lower = {c.lower() for c in columns}

    violations: list[ContractViolation] = []

    # Check each contracted column against actuals.
    for contract in model.contract_columns:
        col_lower = contract.name.lower()

        # 1. COLUMN_REMOVED — contracted column missing from output.
        if col_lower not in columns_lower:
            violations.append(
                ContractViolation(
                    model_name=model.name,
                    column_name=contract.name,
                    violation_type="COLUMN_REMOVED",
                    severity=ViolationSeverity.BREAKING,
                    expected=f"{contract.name}: {contract.data_type}",
                    actual="(missing)",
                    message=(
                        f"Contracted column '{contract.name}' "
                        f"(type: {contract.data_type}) is missing from model output."
                    ),
                )
            )
            continue

        # 2. TYPE_CHANGED — column exists but type doesn't match.
        if actual_column_types is not None:
            # Look up actual type case-insensitively.
            actual_type_raw = None
            for col_key, col_type in actual_column_types.items():
                if col_key.lower() == col_lower:
                    actual_type_raw = col_type
                    break

            if actual_type_raw is not None:
                expected_normalized = _normalize_type(contract.data_type)
                actual_normalized = _normalize_type(actual_type_raw)

                if expected_normalized != actual_normalized:
                    violations.append(
                        ContractViolation(
                            model_name=model.name,
                            column_name=contract.name,
                            violation_type="TYPE_CHANGED",
                            severity=ViolationSeverity.BREAKING,
                            expected=contract.data_type,
                            actual=actual_type_raw,
                            message=(
                                f"Column '{contract.name}' type changed: "
                                f"contract declares {contract.data_type}, "
                                f"actual is {actual_type_raw}."
                            ),
                        )
                    )

        # 3. NULLABLE_TIGHTENED — nullability mismatch.
        if actual_column_nullability is not None:
            actual_nullable = None
            for col_key, is_nullable in actual_column_nullability.items():
                if col_key.lower() == col_lower:
                    actual_nullable = is_nullable
                    break

            # Contract says NOT NULL but actual allows NULLs: that's OK
            # (looser is fine). Contract says nullable but actual is NOT
            # NULL: that's tightening (could break downstream).
            if actual_nullable is not None and not contract.nullable and actual_nullable:
                # Contract says NOT NULL, actual allows NULLs — violation.
                violations.append(
                    ContractViolation(
                        model_name=model.name,
                        column_name=contract.name,
                        violation_type="NULLABLE_TIGHTENED",
                        severity=ViolationSeverity.BREAKING,
                        expected="NOT NULL",
                        actual="NULLABLE",
                        message=(
                            f"Column '{contract.name}' is declared NOT NULL "
                            f"in contract but is nullable in actual output."
                        ),
                    )
                )

    # 4. COLUMN_ADDED — extra columns not in contract (informational).
    contracted_names_lower = {c.name.lower() for c in model.contract_columns}
    for actual_col in sorted(columns):
        if actual_col.lower() not in contracted_names_lower:
            violations.append(
                ContractViolation(
                    model_name=model.name,
                    column_name=actual_col,
                    violation_type="COLUMN_ADDED",
                    severity=ViolationSeverity.INFO,
                    expected="(not in contract)",
                    actual=actual_col,
                    message=(f"Column '{actual_col}' exists in output but is not declared in the schema contract."),
                )
            )

    # Sort violations deterministically: by model_name, then column_name,
    # then violation_type.
    violations.sort(key=lambda v: (v.model_name, v.column_name, v.violation_type))

    return ContractValidationResult(
        violations=violations,
        models_checked=1,
    )


def validate_schema_contracts_batch(
    models: list[ModelDefinition],
    actual_columns_map: dict[str, list[str]] | None = None,
    actual_types_map: dict[str, dict[str, str]] | None = None,
    actual_nullability_map: dict[str, dict[str, bool]] | None = None,
) -> ContractValidationResult:
    """Validate schema contracts across multiple models.

    This is a convenience wrapper that calls :func:`validate_schema_contract`
    for each model with an active contract and aggregates the results.

    Parameters
    ----------
    models:
        List of model definitions to check.
    actual_columns_map:
        Optional mapping of ``model_name -> [column_names]``.
    actual_types_map:
        Optional mapping of ``model_name -> {column: type}``.
    actual_nullability_map:
        Optional mapping of ``model_name -> {column: nullable}``.

    Returns
    -------
    ContractValidationResult
        Aggregated validation result across all models.
    """
    all_violations: list[ContractViolation] = []
    models_checked = 0

    for model in sorted(models, key=lambda m: m.name):
        if model.contract_mode == SchemaContractMode.DISABLED:
            continue

        actual_cols = actual_columns_map.get(model.name) if actual_columns_map else None
        actual_types = actual_types_map.get(model.name) if actual_types_map else None
        actual_nullability = actual_nullability_map.get(model.name) if actual_nullability_map else None

        result = validate_schema_contract(
            model=model,
            actual_columns=actual_cols,
            actual_column_types=actual_types,
            actual_column_nullability=actual_nullability,
        )

        all_violations.extend(result.violations)
        models_checked += result.models_checked

    # Re-sort all violations globally for determinism.
    all_violations.sort(key=lambda v: (v.model_name, v.column_name, v.violation_type))

    return ContractValidationResult(
        violations=all_violations,
        models_checked=models_checked,
    )

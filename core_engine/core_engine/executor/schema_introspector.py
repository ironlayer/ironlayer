"""Schema introspection and comparison for drift detection.

Provides utilities to parse ``DESCRIBE TABLE EXTENDED`` output from
Databricks, build normalised schema representations, and compare expected
vs. actual schemas to produce structured drift reports.

This module does **not** call Databricks directly -- it operates on
pre-fetched schema data.  The calling code is responsible for executing
the ``DESCRIBE TABLE EXTENDED`` query and passing the raw output rows.
"""

from __future__ import annotations

import logging

from pydantic import BaseModel, Field

from core_engine.contracts.schema_validator import _normalize_type
from core_engine.models.model_definition import ModelDefinition

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Schema models
# ---------------------------------------------------------------------------


class ColumnInfo(BaseModel):
    """Description of a single column within a table schema."""

    name: str = Field(..., description="Column name.")
    data_type: str = Field(..., description="Data type as reported by the warehouse.")
    nullable: bool = Field(default=True, description="Whether the column allows NULLs.")
    comment: str | None = Field(default=None, description="Column comment, if any.")


class TableSchema(BaseModel):
    """Full schema for a table: name and ordered list of columns."""

    table_name: str = Field(..., description="Fully-qualified table name.")
    columns: list[ColumnInfo] = Field(
        default_factory=list,
        description="Ordered list of columns in the table.",
    )


class SchemaDrift(BaseModel):
    """A single detected drift between expected and actual schemas."""

    model_name: str = Field(..., description="Model or table where drift was detected.")
    drift_type: str = Field(
        ...,
        description=("Classification of drift: COLUMN_ADDED, COLUMN_REMOVED, or TYPE_CHANGED."),
    )
    column_name: str = Field(..., description="Column involved in the drift.")
    expected: str = Field(default="", description="What was expected.")
    actual: str = Field(default="", description="What was actually found.")
    message: str = Field(default="", description="Human-readable description.")


# ---------------------------------------------------------------------------
# Parsing
# ---------------------------------------------------------------------------


def parse_describe_output(raw_output: list[dict[str, str]]) -> TableSchema:
    """Parse Databricks ``DESCRIBE TABLE EXTENDED`` output into a :class:`TableSchema`.

    Parameters
    ----------
    raw_output:
        A list of row-dicts with keys ``col_name``, ``data_type``, and
        ``comment``.  Rows after a separator (where ``col_name`` starts with
        ``#`` or is empty) are treated as metadata and skipped.

    Returns
    -------
    TableSchema
        A normalised schema with the table's columns.
    """
    columns: list[ColumnInfo] = []
    table_name = ""

    in_metadata = False

    for row in raw_output:
        col_name = (row.get("col_name") or "").strip()
        data_type = (row.get("data_type") or "").strip()
        comment = (row.get("comment") or "").strip() or None

        # Once we hit the metadata separator section, stop collecting columns.
        if not col_name or col_name.startswith("#"):
            in_metadata = True
            continue

        # After entering metadata, look for the table name but do not
        # add any more column entries.
        if in_metadata:
            if data_type and col_name.lower() in ("table", "name", "table_name"):
                table_name = data_type
            continue

        columns.append(
            ColumnInfo(
                name=col_name,
                data_type=data_type,
                nullable=True,  # DESCRIBE doesn't reliably report nullability.
                comment=comment,
            )
        )

    return TableSchema(table_name=table_name, columns=columns)


# ---------------------------------------------------------------------------
# Comparison
# ---------------------------------------------------------------------------


def compare_schemas(
    expected: TableSchema,
    actual: TableSchema,
) -> list[SchemaDrift]:
    """Compare two schemas and return a list of drifts.

    Drift types:
    * ``COLUMN_REMOVED`` -- column present in *expected* but absent in *actual*.
    * ``COLUMN_ADDED`` -- column present in *actual* but absent in *expected*.
    * ``TYPE_CHANGED`` -- column exists in both but its data type differs after
      normalisation.

    Column name matching is case-insensitive.  Results are sorted
    deterministically by ``(drift_type, column_name)``.

    Parameters
    ----------
    expected:
        The schema the model *should* have.
    actual:
        The schema the model *actually* has in the warehouse.

    Returns
    -------
    list[SchemaDrift]
        All detected drifts, sorted by ``(drift_type, column_name)``.
    """
    model_name = expected.table_name or actual.table_name or "unknown"

    expected_map: dict[str, ColumnInfo] = {col.name.lower(): col for col in expected.columns}
    actual_map: dict[str, ColumnInfo] = {col.name.lower(): col for col in actual.columns}

    drifts: list[SchemaDrift] = []

    # Columns removed (in expected but not in actual).
    for col_lower, exp_col in sorted(expected_map.items()):
        if col_lower not in actual_map:
            drifts.append(
                SchemaDrift(
                    model_name=model_name,
                    drift_type="COLUMN_REMOVED",
                    column_name=exp_col.name,
                    expected=f"{exp_col.name}: {exp_col.data_type}",
                    actual="(missing)",
                    message=(
                        f"Column '{exp_col.name}' (type: {exp_col.data_type}) "
                        f"exists in expected schema but is missing from actual."
                    ),
                )
            )

    # Columns added (in actual but not in expected).
    for col_lower, act_col in sorted(actual_map.items()):
        if col_lower not in expected_map:
            drifts.append(
                SchemaDrift(
                    model_name=model_name,
                    drift_type="COLUMN_ADDED",
                    column_name=act_col.name,
                    expected="(not expected)",
                    actual=f"{act_col.name}: {act_col.data_type}",
                    message=(
                        f"Column '{act_col.name}' (type: {act_col.data_type}) "
                        f"exists in actual schema but is not in the expected schema."
                    ),
                )
            )

    # Type changes (column exists in both but type differs).
    for col_lower in sorted(expected_map.keys() & actual_map.keys()):
        exp_col = expected_map[col_lower]
        act_col = actual_map[col_lower]

        exp_type = _normalize_type(exp_col.data_type)
        act_type = _normalize_type(act_col.data_type)

        if exp_type != act_type:
            drifts.append(
                SchemaDrift(
                    model_name=model_name,
                    drift_type="TYPE_CHANGED",
                    column_name=exp_col.name,
                    expected=exp_col.data_type,
                    actual=act_col.data_type,
                    message=(
                        f"Column '{exp_col.name}' type changed: "
                        f"expected {exp_col.data_type}, actual {act_col.data_type}."
                    ),
                )
            )

    # Sort deterministically.
    drifts.sort(key=lambda d: (d.drift_type, d.column_name.lower()))
    return drifts


def compare_with_contracts(
    model_def: ModelDefinition,
    actual: TableSchema,
) -> list[SchemaDrift]:
    """Compare a model's contract columns against an actual table schema.

    When the model has ``contract_columns`` defined, those are used as the
    expected schema.  Otherwise, falls back to ``output_columns`` (names
    only, no type information -- so only presence checks are performed).

    Parameters
    ----------
    model_def:
        The model definition containing optional ``contract_columns``.
    actual:
        The actual table schema from the warehouse.

    Returns
    -------
    list[SchemaDrift]
        All detected drifts, sorted deterministically.
    """
    if model_def.contract_columns:
        expected_columns = [
            ColumnInfo(
                name=cc.name,
                data_type=cc.data_type,
                nullable=cc.nullable,
            )
            for cc in sorted(model_def.contract_columns, key=lambda c: c.name.lower())
        ]
    elif model_def.output_columns:
        expected_columns = [
            ColumnInfo(
                name=col_name,
                data_type="UNKNOWN",
                nullable=True,
            )
            for col_name in sorted(model_def.output_columns, key=str.lower)
        ]
    else:
        return []

    expected_schema = TableSchema(
        table_name=model_def.name,
        columns=expected_columns,
    )

    return compare_schemas(expected_schema, actual)

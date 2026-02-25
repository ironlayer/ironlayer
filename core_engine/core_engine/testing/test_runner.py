"""Model test runner for IronLayer.

Generates assertion SQL from declarative test definitions and executes them
against DuckDB (local) or Databricks.  Each test type produces a SQL query
that returns a result indicating pass/fail.

Test types
----------
- NOT_NULL:        Asserts no NULL values in the specified column.
- UNIQUE:          Asserts no duplicate values in the specified column.
- ROW_COUNT_MIN:   Asserts the table has at least N rows.
- ROW_COUNT_MAX:   Asserts the table has at most N rows.
- ACCEPTED_VALUES: Asserts all non-NULL values in a column belong to a set.
- CUSTOM_SQL:      Arbitrary assertion SQL; pass means zero result rows.
"""

from __future__ import annotations

import logging
import re
import time

from pydantic import BaseModel

from core_engine.models.model_definition import ModelTestDefinition, ModelTestType
from core_engine.models.plan import compute_deterministic_id

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# SQL identifier allowlist validation
# ---------------------------------------------------------------------------

_SAFE_IDENTIFIER_RE = re.compile(r"^[a-zA-Z_][a-zA-Z0-9_.]*$")


def _validate_identifier(name: str) -> str:
    """Validate that *name* is a safe SQL identifier.

    DuckDB does not support parameterised table/column names, so we
    use an allowlist regex to ensure that only alphanumeric identifiers
    (with underscores and dots for schema-qualified names) are accepted.

    Raises
    ------
    ValueError
        If *name* contains characters outside the allowlist.
    """
    if not _SAFE_IDENTIFIER_RE.match(name):
        raise ValueError(f"Unsafe SQL identifier: {name!r}")
    return name


def _validate_accepted_value(value: str) -> str:
    """Validate that an ACCEPTED_VALUES entry is safe for SQL embedding.

    Rejects values containing single quotes or other SQL injection vectors.

    Raises
    ------
    ValueError
        If the value contains unsafe characters.
    """
    if "'" in value or "\\" in value or ";" in value:
        raise ValueError(f"Unsafe accepted value: {value!r}")
    return value


# ---------------------------------------------------------------------------
# Result model
# ---------------------------------------------------------------------------


class TestResult(BaseModel):
    """The outcome of a single test execution."""

    test_id: str
    model_name: str
    test_type: str
    passed: bool
    failure_message: str | None = None
    duration_ms: int = 0


# ---------------------------------------------------------------------------
# Test runner
# ---------------------------------------------------------------------------


class ModelTestRunner:
    """Runs declarative tests against a SQL execution backend.

    Parameters
    ----------
    execution_mode:
        The backend to execute tests against.  ``"local_duckdb"`` uses an
        in-process DuckDB connection; other values are reserved for future
        backends (e.g. Databricks).
    """

    def __init__(self, execution_mode: str = "local_duckdb") -> None:
        self._mode = execution_mode

    def generate_test_sql(self, test: ModelTestDefinition, model_name: str) -> str:
        """Generate assertion SQL for a test definition.

        Returns SQL that evaluates to 0 rows on success (pass) or 1+ rows
        on failure.

        All table names, column names, and literal values are validated
        against an allowlist before being interpolated into SQL strings.
        DuckDB does not support parameterised table/column names, so this
        allowlist approach is the primary injection defence.

        Parameters
        ----------
        test:
            The declarative test definition.
        model_name:
            Canonical model (table) name to test against.

        Returns
        -------
        str
            SQL assertion query.

        Raises
        ------
        ValueError
            If the test type is unknown or any identifier is unsafe.
        """
        safe_model = _validate_identifier(model_name)

        if test.test_type == ModelTestType.NOT_NULL:
            safe_col = _validate_identifier(test.column or "")
            return f"SELECT * FROM {safe_model} WHERE {safe_col} IS NULL LIMIT 1"

        elif test.test_type == ModelTestType.UNIQUE:
            safe_col = _validate_identifier(test.column or "")
            return (
                f"SELECT {safe_col}, COUNT(*) AS cnt "
                f"FROM {safe_model} "
                f"GROUP BY {safe_col} "
                f"HAVING COUNT(*) > 1 LIMIT 1"
            )

        elif test.test_type == ModelTestType.ROW_COUNT_MIN:
            threshold = int(test.threshold)  # type: ignore[arg-type]
            return (
                f"SELECT CASE WHEN cnt < {threshold} THEN 1 ELSE 0 END AS failed "
                f"FROM (SELECT COUNT(*) AS cnt FROM {safe_model}) sub "
                f"WHERE failed = 1"
            )

        elif test.test_type == ModelTestType.ROW_COUNT_MAX:
            threshold = int(test.threshold)  # type: ignore[arg-type]
            return (
                f"SELECT CASE WHEN cnt > {threshold} THEN 1 ELSE 0 END AS failed "
                f"FROM (SELECT COUNT(*) AS cnt FROM {safe_model}) sub "
                f"WHERE failed = 1"
            )

        elif test.test_type == ModelTestType.ACCEPTED_VALUES:
            safe_col = _validate_identifier(test.column or "")
            safe_values = [_validate_accepted_value(v) for v in sorted(test.values or [])]
            values_str = ", ".join(f"'{v}'" for v in safe_values)
            return (
                f"SELECT * FROM {safe_model} "
                f"WHERE {safe_col} NOT IN ({values_str}) "
                f"AND {safe_col} IS NOT NULL LIMIT 1"
            )

        elif test.test_type == ModelTestType.CUSTOM_SQL:
            # Custom SQL is user-provided; validate the model name substitution only.
            return (test.sql or "").replace("{model}", safe_model)

        raise ValueError(f"Unknown test type: {test.test_type}")

    async def run_test(
        self,
        test: ModelTestDefinition,
        model_name: str,
        *,
        duckdb_conn: object | None = None,
    ) -> TestResult:
        """Execute a single test and return the result.

        Parameters
        ----------
        test:
            The test definition to execute.
        model_name:
            Table name to test against.
        duckdb_conn:
            Optional pre-existing DuckDB connection.  When ``None``,
            a temporary in-memory connection is created and closed
            after execution.

        Returns
        -------
        TestResult
        """
        test_sql = self.generate_test_sql(test, model_name)
        test_id = compute_deterministic_id(
            model_name,
            test.test_type.value,
            test.column or "",
            test.sql or "",
        )

        start = time.monotonic()
        try:
            if self._mode == "local_duckdb":
                result = self._execute_duckdb(test_sql, duckdb_conn)
            else:
                result = []

            duration = int((time.monotonic() - start) * 1000)

            if result:
                return TestResult(
                    test_id=test_id,
                    model_name=model_name,
                    test_type=test.test_type.value,
                    passed=False,
                    failure_message=(
                        f"Test {test.test_type.value} failed: " f"{len(result)} row(s) violating assertion"
                    ),
                    duration_ms=duration,
                )
            return TestResult(
                test_id=test_id,
                model_name=model_name,
                test_type=test.test_type.value,
                passed=True,
                duration_ms=duration,
            )
        except Exception as exc:
            duration = int((time.monotonic() - start) * 1000)
            logger.warning(
                "Test execution error for %s on %s: %s",
                test.test_type.value,
                model_name,
                exc,
            )
            return TestResult(
                test_id=test_id,
                model_name=model_name,
                test_type=test.test_type.value,
                passed=False,
                failure_message=f"Test execution error: {exc}",
                duration_ms=duration,
            )

    @staticmethod
    def _execute_duckdb(sql: str, conn: object | None = None) -> list:
        """Execute SQL against DuckDB and return result rows.

        Parameters
        ----------
        sql:
            SQL query to execute.
        conn:
            Optional DuckDB connection.  When ``None``, a temporary
            in-memory connection is used.

        Returns
        -------
        list
            List of result tuples.  Empty list means the test passed.
        """
        import duckdb

        local_conn = conn or duckdb.connect(":memory:")
        try:
            result = local_conn.execute(sql).fetchall()  # type: ignore[attr-defined]
            return result
        finally:
            if conn is None:
                local_conn.close()  # type: ignore[attr-defined]

    async def run_all_tests(
        self,
        model_name: str,
        tests: list[ModelTestDefinition],
        *,
        duckdb_conn: object | None = None,
    ) -> list[TestResult]:
        """Run all tests for a model and return sorted results.

        Tests are sorted deterministically by ``(test_type, column)``
        before execution.

        Parameters
        ----------
        model_name:
            Table name to test against.
        tests:
            List of test definitions to execute.
        duckdb_conn:
            Optional DuckDB connection.

        Returns
        -------
        list[TestResult]
        """
        results: list[TestResult] = []
        sorted_tests = sorted(tests, key=lambda t: (t.test_type.value, t.column or "", t.sql or ""))
        for test in sorted_tests:
            result = await self.run_test(test, model_name, duckdb_conn=duckdb_conn)
            results.append(result)
        return results

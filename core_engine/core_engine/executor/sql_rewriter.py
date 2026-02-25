"""SQL rewriting for environment isolation.

Rewrites table references in SQL statements to point to environment-specific
catalogs and schemas.  Uses SQLGlot's AST manipulation (Databricks dialect)
rather than string replacement to ensure correctness for qualified names,
CTEs, subqueries, and aliases.

This is a pure function: same inputs = same output (maintains determinism).
Rewriting happens at execution time, NOT at plan time -- plans remain
deterministic and environment-agnostic.
"""

from __future__ import annotations

import logging

from core_engine.sql_toolkit import Dialect, RewriteRule, get_sql_toolkit
from core_engine.telemetry.profiling import profile_operation

logger = logging.getLogger(__name__)


class SQLRewriter:
    """Rewrites SQL table references for environment-specific execution.

    Parameters
    ----------
    source_catalog:
        The catalog name to match in existing table references (e.g. ``"main"``).
    source_schema:
        The schema/database name to match in existing table references.
    target_catalog:
        The catalog to rewrite matched references to.
    target_schema:
        The schema to rewrite matched references to.
    """

    def __init__(
        self,
        source_catalog: str,
        source_schema: str,
        target_catalog: str,
        target_schema: str,
    ) -> None:
        self._source_catalog = source_catalog
        self._source_schema = source_schema
        self._target_catalog = target_catalog
        self._target_schema = target_schema

    @property
    def is_noop(self) -> bool:
        """Return True if source and target are identical (no rewriting needed)."""
        return (
            self._source_catalog.lower() == self._target_catalog.lower()
            and self._source_schema.lower() == self._target_schema.lower()
        )

    @profile_operation("sql.rewrite")
    def rewrite(self, sql: str) -> str:
        """Rewrite all table references in a SQL statement.

        Delegates to the SQL toolkit's rewriter which uses AST-based mutation
        for correctness with CTEs, subqueries, and quoted identifiers.

        Parameters
        ----------
        sql:
            The SQL statement(s) to rewrite.  May contain multiple statements
            separated by semicolons.

        Returns
        -------
        str
            The rewritten SQL string.  If parsing fails, the original SQL is
            returned unchanged (conservative fallback).
        """
        if self.is_noop:
            return sql

        tk = get_sql_toolkit()
        rule = RewriteRule(
            source_catalog=self._source_catalog,
            source_schema=self._source_schema,
            target_catalog=self._target_catalog,
            target_schema=self._target_schema,
        )
        result = tk.rewriter.rewrite_tables(sql, [rule], Dialect.DATABRICKS)
        return result.rewritten_sql

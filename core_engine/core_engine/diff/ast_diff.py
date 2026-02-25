"""AST-level diff engine for semantic SQL model comparison.

Uses the SQL toolkit to parse both old and new SQL into abstract syntax trees,
then computes a fine-grained edit script.  The edit script is classified into
one of the :class:`ChangeType` categories so that downstream consumers (the
planner, the UI) can make informed decisions about whether a change is
cosmetic, structural, or behavioural.

All output lists are sorted deterministically.  If either SQL string fails to
parse, the function conservatively returns ``ChangeType.MODIFIED`` so that the
planner always errs on the side of rebuilding.

All SQL parsing is delegated to :mod:`core_engine.sql_toolkit`.
"""

from __future__ import annotations

import logging
from collections.abc import Sequence

from core_engine.models.diff import ASTDiffDetail, ChangeType
from core_engine.sql_toolkit import Dialect, get_sql_toolkit
from core_engine.telemetry.profiling import profile_operation

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


@profile_operation("sql.ast_diff")
def compute_ast_diff(old_sql: str, new_sql: str) -> ASTDiffDetail:
    """Compute a fine-grained, AST-level diff between two SQL statements.

    Parameters
    ----------
    old_sql:
        The SQL text of the *base* (previous) model version.
    new_sql:
        The SQL text of the *target* (current) model version.

    Returns
    -------
    ASTDiffDetail
        Classified change detail including affected columns and expressions.
    """
    tk = get_sql_toolkit()

    try:
        diff_result = tk.differ.diff(old_sql, new_sql, Dialect.DATABRICKS)
    except Exception:  # noqa: BLE001
        logger.warning("Toolkit diff failed; defaulting to MODIFIED.")
        return _modified_fallback()

    # Cosmetic-only: normalised forms match but raw SQL differs.
    if diff_result.is_cosmetic_only:
        return ASTDiffDetail(
            change_type=ChangeType.COSMETIC_ONLY,
            changed_columns=[],
            added_columns=[],
            removed_columns=[],
            changed_expressions=[],
        )

    # Semantically identical: AST diff produced zero non-Keep edits.
    if diff_result.is_identical:
        return ASTDiffDetail(
            change_type=ChangeType.NO_CHANGE,
            changed_columns=[],
            added_columns=[],
            removed_columns=[],
            changed_expressions=[],
        )

    # Semantic changes detected — compute column-level detail.
    try:
        column_changes = tk.differ.extract_column_changes(
            old_sql, new_sql, Dialect.DATABRICKS,
        )
    except Exception:  # noqa: BLE001
        column_changes = {}

    changed_cols = sorted(k for k, v in column_changes.items() if v == "modified")
    added_cols = sorted(k for k, v in column_changes.items() if v == "added")
    removed_cols = sorted(k for k, v in column_changes.items() if v == "removed")

    # Extract SQL fragments from edit operations.
    changed_expressions = _collect_changed_expressions(diff_result.edits)

    return ASTDiffDetail(
        change_type=ChangeType.MODIFIED,
        changed_columns=changed_cols,
        added_columns=added_cols,
        removed_columns=removed_cols,
        changed_expressions=changed_expressions,
    )


def is_cosmetic_only(old_sql: str, new_sql: str) -> bool:
    """Return ``True`` if the two SQL strings are semantically identical.

    Both strings are normalised through the SQL toolkit's differ.  If the
    normalised forms are equal, the difference is purely cosmetic
    (whitespace, casing, trailing semicolons, etc.).

    If parsing fails for either string, returns ``False`` so that the caller
    falls through to the full diff path and ultimately defaults to MODIFIED.
    """
    tk = get_sql_toolkit()
    try:
        result = tk.differ.diff(old_sql, new_sql, Dialect.DATABRICKS)
    except Exception:  # noqa: BLE001
        return False

    return result.is_cosmetic_only or result.is_identical


def extract_changed_columns(old_sql: str, new_sql: str) -> list[str]:
    """Return sorted column names whose SELECT expressions differ.

    Compares the top-level ``SELECT`` expressions of both SQL statements and
    returns the names of any columns whose SQL representation changed, was
    added, or was removed.

    Parameters
    ----------
    old_sql:
        The base SQL statement.
    new_sql:
        The target SQL statement.

    Returns
    -------
    list[str]
        Deterministically sorted list of affected column names.
    """
    tk = get_sql_toolkit()
    try:
        changes = tk.differ.extract_column_changes(
            old_sql, new_sql, Dialect.DATABRICKS,
        )
    except Exception:  # noqa: BLE001
        return []

    return sorted(changes.keys())


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _modified_fallback() -> ASTDiffDetail:
    """Construct a conservative MODIFIED detail when parsing/diff fails."""
    return ASTDiffDetail(
        change_type=ChangeType.MODIFIED,
        changed_columns=[],
        added_columns=[],
        removed_columns=[],
        changed_expressions=[],
    )


def _collect_changed_expressions(
    edits: Sequence[object],
    max_entries: int = 50,
) -> list[str]:
    """Extract a deterministic list of SQL fragments from DiffEdit objects.

    Each :class:`DiffEdit` carries ``source_sql`` and ``target_sql`` fields.
    We collect one representative fragment per edit and cap the total count
    at *max_entries* to prevent unbounded growth in pathological diffs.
    """
    fragments: list[str] = []
    for edit in edits:
        if len(fragments) >= max_entries:
            break
        sql_text = getattr(edit, "source_sql", "") or getattr(edit, "target_sql", "")
        if sql_text:
            fragments.append(sql_text)

    # Sort for determinism.
    return sorted(fragments)

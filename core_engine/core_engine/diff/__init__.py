"""Deterministic diff engine for SQL model comparison."""

from core_engine.diff.ast_diff import ASTDiffDetail, compute_ast_diff, extract_changed_columns, is_cosmetic_only
from core_engine.diff.structural_diff import compute_structural_diff

__all__ = [
    "ASTDiffDetail",
    "compute_ast_diff",
    "compute_structural_diff",
    "extract_changed_columns",
    "is_cosmetic_only",
]

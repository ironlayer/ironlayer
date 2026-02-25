"""Diff models for comparing model snapshots.

These models represent the output of comparing two snapshots (base vs. target)
and, optionally, performing a deeper AST-level comparison of individual SQL
model files.
"""

from __future__ import annotations

from enum import Enum

from pydantic import BaseModel, Field


class ChangeType(str, Enum):
    """Classification of a change detected between two versions of a model."""

    ADDED = "ADDED"
    REMOVED = "REMOVED"
    MODIFIED = "MODIFIED"
    COSMETIC_ONLY = "COSMETIC_ONLY"
    NO_CHANGE = "NO_CHANGE"


class HashChange(BaseModel):
    """Records the before/after content hashes for a single model."""

    old_hash: str = Field(
        ...,
        description="SHA-256 content hash in the base snapshot.",
    )
    new_hash: str = Field(
        ...,
        description="SHA-256 content hash in the target snapshot.",
    )


class DiffResult(BaseModel):
    """High-level diff summary between two snapshots.

    Lists which models were added, removed, or modified, and provides the
    per-model hash changes for any model whose content hash differs.
    """

    added_models: list[str] = Field(
        default_factory=list,
        description="Models present in target but absent from base.",
    )
    removed_models: list[str] = Field(
        default_factory=list,
        description="Models present in base but absent from target.",
    )
    modified_models: list[str] = Field(
        default_factory=list,
        description="Models present in both snapshots whose content hash changed.",
    )
    hash_changes: dict[str, HashChange] = Field(
        default_factory=dict,
        description="Per-model hash change details, keyed by canonical model name.",
    )


class ASTDiffDetail(BaseModel):
    """Fine-grained, AST-level diff detail for a single modified model.

    Produced by the SQL AST comparator when a model's content hash has changed
    but a deeper semantic diff is desired (e.g. to distinguish column renames
    from expression rewrites).
    """

    change_type: ChangeType = Field(
        ...,
        description="Overall classification of the change.",
    )
    changed_columns: list[str] = Field(
        default_factory=list,
        description="Columns whose expressions were modified.",
    )
    added_columns: list[str] = Field(
        default_factory=list,
        description="Columns added in the target version.",
    )
    removed_columns: list[str] = Field(
        default_factory=list,
        description="Columns removed from the base version.",
    )
    changed_expressions: list[str] = Field(
        default_factory=list,
        description="Raw SQL expression fragments that differ between versions.",
    )

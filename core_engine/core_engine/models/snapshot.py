"""Snapshot models for capturing point-in-time project state.

A snapshot records the exact version of every model in a given environment,
enabling deterministic diff and plan generation.  ``created_at`` is stored
for persistence and auditability but is **not** used in plan determinism
calculations.
"""

from __future__ import annotations

from datetime import UTC, datetime

from pydantic import BaseModel, Field


class ModelVersion(BaseModel):
    """Immutable version record for a single model within a snapshot."""

    version_id: str = Field(
        ...,
        min_length=1,
        description="SHA-256 digest that uniquely identifies this version.",
    )
    model_name: str = Field(
        ...,
        min_length=1,
        description="Canonical model name, e.g. 'analytics.orders_daily'.",
    )
    canonical_sql_hash: str = Field(
        ...,
        min_length=1,
        description="SHA-256 digest of the model's canonical SQL.",
    )
    metadata_hash: str = Field(
        ...,
        min_length=1,
        description="SHA-256 digest of the model's non-SQL metadata (kind, materialization, etc.).",
    )
    canonicalizer_version: str = Field(
        default="v1",
        description="Version of the canonicalisation rule-set used to produce this hash.",
    )


class Snapshot(BaseModel):
    """Point-in-time capture of all model versions in an environment.

    The ``versions`` dictionary is keyed by canonical model name for O(1)
    lookup during diff operations.  ``created_at`` is recorded for
    persistence and human inspection but does **not** influence plan IDs
    or step IDs.
    """

    snapshot_id: str = Field(
        ...,
        min_length=1,
        description="Unique identifier for this snapshot.",
    )
    environment: str = Field(
        ...,
        min_length=1,
        description="Target environment name, e.g. 'production' or 'staging'.",
    )
    versions: dict[str, ModelVersion] = Field(
        default_factory=dict,
        description="Model versions keyed by canonical model name.",
    )
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(UTC),
        description="Timestamp when this snapshot was created (for persistence only).",
    )

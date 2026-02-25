"""Execution plan models for the IronLayer planner.

Plans are **deterministic**: given the same base snapshot, target snapshot, and
model content, the planner must produce an identical plan every time.  To
enforce this, plan IDs and step IDs are derived from content hashes rather than
random UUIDs, and no wall-clock timestamps are embedded in the plan itself.
"""

from __future__ import annotations

import hashlib
from datetime import date
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field, model_validator

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def compute_deterministic_id(*parts: str) -> str:
    """Derive a deterministic SHA-256 hex ID from an ordered sequence of strings.

    This is used for both ``plan_id`` and ``step_id`` so that identical inputs
    always yield the same identifiers.
    """
    hasher = hashlib.sha256()
    for part in parts:
        hasher.update(part.encode("utf-8"))
        hasher.update(b"\x00")  # Null-byte domain separator prevents collisions
    return hasher.hexdigest()


# ---------------------------------------------------------------------------
# Value objects
# ---------------------------------------------------------------------------


class DateRange(BaseModel):
    """An inclusive date range used to scope incremental model runs."""

    start: date = Field(..., description="Inclusive lower bound of the range.")
    end: date = Field(..., description="Inclusive upper bound of the range.")

    @model_validator(mode="after")
    def validate_start_before_end(self) -> DateRange:
        """Ensure *start* does not come after *end*."""
        if self.start > self.end:
            raise ValueError(f"DateRange start ({self.start}) must be <= end ({self.end}).")
        return self


class RunType(str, Enum):
    """Whether a step performs a full refresh or an incremental append."""

    FULL_REFRESH = "FULL_REFRESH"
    INCREMENTAL = "INCREMENTAL"


# ---------------------------------------------------------------------------
# Plan step
# ---------------------------------------------------------------------------


class PlanStep(BaseModel):
    """A single unit of work inside an execution plan.

    ``step_id`` is deterministic -- it is computed from the model's content
    hash and the run type so that identical work always maps to the same step.
    """

    step_id: str = Field(
        ...,
        min_length=1,
        description="Deterministic SHA-256 hex digest derived from the step content.",
    )
    model: str = Field(
        ...,
        min_length=1,
        description="Canonical model name to be executed.",
    )
    run_type: RunType = Field(
        ...,
        description="Whether this step runs as FULL_REFRESH or INCREMENTAL.",
    )
    input_range: DateRange | None = Field(
        default=None,
        description="Optional date range for incremental runs.",
    )
    depends_on: list[str] = Field(
        default_factory=list,
        description="Step IDs that must complete before this step can start.",
    )
    parallel_group: int = Field(
        default=0,
        ge=0,
        description="Steps sharing a parallel group may execute concurrently.",
    )
    reason: str = Field(
        default="",
        description="Human-readable explanation of why this step is included.",
    )
    estimated_compute_seconds: float = Field(
        default=0.0,
        ge=0.0,
        description="Estimated wall-clock seconds for this step.",
    )
    estimated_cost_usd: float = Field(
        default=0.0,
        ge=0.0,
        description="Estimated cost in USD for this step.",
    )
    contract_violations: list[dict[str, Any]] = Field(
        default_factory=list,
        description=(
            "Schema contract violations detected for this step's model.  "
            "Each dict contains: column_name, violation_type, severity, "
            "expected, actual, message."
        ),
    )


# ---------------------------------------------------------------------------
# Plan summary
# ---------------------------------------------------------------------------


class PlanSummary(BaseModel):
    """Aggregate statistics for a plan, surfaced in the UI and logs."""

    total_steps: int = Field(
        ...,
        ge=0,
        description="Total number of steps in the plan.",
    )
    estimated_cost_usd: float = Field(
        default=0.0,
        ge=0.0,
        description="Sum of estimated costs across all steps.",
    )
    models_changed: list[str] = Field(
        default_factory=list,
        description="Canonical names of models that will be rebuilt.",
    )
    cosmetic_changes_skipped: list[str] = Field(
        default_factory=list,
        description="Models excluded from the plan because their changes were cosmetic-only.",
    )
    contract_violations_count: int = Field(
        default=0,
        ge=0,
        description="Total number of schema contract violations across all steps.",
    )
    breaking_contract_violations: int = Field(
        default=0,
        ge=0,
        description="Count of BREAKING severity contract violations that may block apply.",
    )


# ---------------------------------------------------------------------------
# Plan & advisory wrapper
# ---------------------------------------------------------------------------


class Plan(BaseModel):
    """A fully-resolved, deterministic execution plan.

    The ``plan_id`` is derived from ``base``, ``target``, and the ordered
    content hashes of the steps so that identical inputs always produce the
    same plan identity.  No wall-clock timestamp is stored in the plan --
    determinism is paramount.
    """

    plan_id: str = Field(
        ...,
        min_length=1,
        description="Deterministic SHA-256 hex digest identifying this plan.",
    )
    base: str = Field(
        ...,
        description="Identifier of the base snapshot (current state).",
    )
    target: str = Field(
        ...,
        description="Identifier of the target snapshot (desired state).",
    )
    summary: PlanSummary = Field(
        ...,
        description="Aggregate statistics for the plan.",
    )
    steps: list[PlanStep] = Field(
        default_factory=list,
        description="Ordered list of execution steps.",
    )


class PlanWithAdvisory(Plan):
    """A ``Plan`` extended with an optional advisory payload.

    The advisory dictionary carries AI-generated metadata (risk scores,
    suggested review notes, etc.) that is informational only and has no
    effect on execution.
    """

    advisory: dict[str, Any] | None = Field(
        default=None,
        description="Optional AI-generated advisory metadata.",
    )

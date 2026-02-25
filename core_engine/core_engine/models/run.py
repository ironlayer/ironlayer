"""Run record models for tracking model execution state.

Each ``RunRecord`` tracks the lifecycle of a single plan step from PENDING
through to SUCCESS or FAIL, capturing timing, error details, and infrastructure
metadata needed for observability and retry logic.
"""

from __future__ import annotations

from datetime import datetime
from enum import Enum

from pydantic import BaseModel, Field

from core_engine.models.plan import DateRange


class RunStatus(str, Enum):
    """Lifecycle state of an individual model run."""

    PENDING = "PENDING"
    RUNNING = "RUNNING"
    SUCCESS = "SUCCESS"
    FAIL = "FAIL"
    CANCELLED = "CANCELLED"


class RunRecord(BaseModel):
    """Detailed record of a single model execution step.

    Run records are created when the executor picks up a ``PlanStep`` and are
    updated as the step transitions through its lifecycle.  They provide the
    primary audit trail for every SQL statement executed by the engine.
    """

    run_id: str = Field(
        ...,
        min_length=1,
        description="Unique identifier for this run execution.",
    )
    plan_id: str = Field(
        ...,
        min_length=1,
        description="Identifier of the parent plan.",
    )
    step_id: str = Field(
        ...,
        min_length=1,
        description="Identifier of the plan step being executed.",
    )
    model_name: str = Field(
        ...,
        min_length=1,
        description="Canonical model name being executed.",
    )
    status: RunStatus = Field(
        default=RunStatus.PENDING,
        description="Current lifecycle state of the run.",
    )
    started_at: datetime | None = Field(
        default=None,
        description="Timestamp when execution began.",
    )
    finished_at: datetime | None = Field(
        default=None,
        description="Timestamp when execution completed or failed.",
    )
    input_range: DateRange | None = Field(
        default=None,
        description="Date range processed in this run (for incremental models).",
    )
    error_message: str | None = Field(
        default=None,
        description="Error message if the run failed.",
    )
    logs_uri: str | None = Field(
        default=None,
        description="URI to the full execution logs (e.g. GCS or S3 path).",
    )
    cluster_used: str | None = Field(
        default=None,
        description="Identifier of the compute cluster that executed this step.",
    )
    executor_version: str = Field(
        ...,
        min_length=1,
        description="Version of the executor binary that ran this step.",
    )
    retry_count: int = Field(
        default=0,
        ge=0,
        description="Number of retry attempts that have been made for this step.",
    )

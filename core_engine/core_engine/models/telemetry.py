"""Telemetry models for run-time metrics and observability events.

``RunTelemetry`` captures per-model execution metrics (row counts, shuffle
bytes, partition counts) while ``MetricsEvent`` provides a generic envelope
for arbitrary timestamped events emitted by the engine.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field


class RunTelemetry(BaseModel):
    """Execution metrics collected for a single model run.

    These metrics are gathered from the warehouse query profile after the
    model's SQL has completed and are used for cost estimation, performance
    regression detection, and capacity planning.
    """

    run_id: str = Field(
        ...,
        min_length=1,
        description="Identifier of the run that produced these metrics.",
    )
    model_name: str = Field(
        ...,
        min_length=1,
        description="Canonical model name.",
    )
    runtime_seconds: float = Field(
        ...,
        ge=0.0,
        description="Wall-clock execution time in seconds.",
    )
    shuffle_bytes: int = Field(
        default=0,
        ge=0,
        description="Total bytes shuffled during query execution.",
    )
    input_rows: int = Field(
        default=0,
        ge=0,
        description="Number of input rows read by the query.",
    )
    output_rows: int = Field(
        default=0,
        ge=0,
        description="Number of output rows produced by the query.",
    )
    partition_count: int = Field(
        default=0,
        ge=0,
        description="Number of partitions written to or scanned.",
    )
    cluster_id: str | None = Field(
        default=None,
        description="Identifier of the compute cluster that executed the query.",
    )


class MetricsEvent(BaseModel):
    """Generic timestamped event for engine-level observability.

    Used for heartbeat signals, phase transitions, warnings, and any
    other structured event the engine needs to emit to external
    monitoring systems.
    """

    event: str = Field(
        ...,
        min_length=1,
        description="Event type identifier, e.g. 'plan.started' or 'step.retried'.",
    )
    timestamp: datetime = Field(
        ...,
        description="UTC timestamp when the event occurred.",
    )
    data: dict[str, Any] = Field(
        default_factory=dict,
        description="Arbitrary payload associated with the event.",
    )

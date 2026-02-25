"""Telemetry collector for extracting execution metrics from run metadata.

The collector transforms raw execution metadata dictionaries (typically
produced by the executor or warehouse query profile) into strongly-typed
:class:`RunTelemetry` instances that downstream systems can rely on for
cost estimation, performance regression detection, and capacity planning.
"""

from __future__ import annotations

import logging
from typing import Any

from core_engine.models.telemetry import RunTelemetry

logger = logging.getLogger(__name__)


def capture_run_telemetry(
    run_id: str,
    model_name: str,
    execution_metadata: dict[str, Any],
) -> RunTelemetry:
    """Extract and normalise execution metrics into a :class:`RunTelemetry`.

    All numeric fields default to ``0`` when absent from *execution_metadata*
    so that callers never need to guard against ``None`` values.

    Parameters
    ----------
    run_id:
        Unique identifier for the execution run.
    model_name:
        Canonical name of the model that was executed.
    execution_metadata:
        Raw key-value pairs from the executor or warehouse query profile.
        Expected keys (all optional):

        - ``runtime_seconds`` (float)
        - ``shuffle_bytes`` (int)
        - ``input_rows`` (int)
        - ``output_rows`` (int)
        - ``partition_count`` (int)
        - ``cluster_id`` (str)

    Returns
    -------
    RunTelemetry
        A validated, strongly-typed telemetry record.
    """
    runtime_seconds = _safe_float(execution_metadata, "runtime_seconds")
    shuffle_bytes = _safe_int(execution_metadata, "shuffle_bytes")
    input_rows = _safe_int(execution_metadata, "input_rows")
    output_rows = _safe_int(execution_metadata, "output_rows")
    partition_count = _safe_int(execution_metadata, "partition_count")
    cluster_id = execution_metadata.get("cluster_id")

    if isinstance(cluster_id, str) and not cluster_id:
        cluster_id = None

    telemetry = RunTelemetry(
        run_id=run_id,
        model_name=model_name,
        runtime_seconds=runtime_seconds,
        shuffle_bytes=shuffle_bytes,
        input_rows=input_rows,
        output_rows=output_rows,
        partition_count=partition_count,
        cluster_id=cluster_id if isinstance(cluster_id, str) else None,
    )

    logger.debug(
        "Captured telemetry for run %s: %.1fs, %d rows in, %d rows out",
        run_id[:12],
        runtime_seconds,
        input_rows,
        output_rows,
    )

    return telemetry


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _safe_float(data: dict[str, Any], key: str, default: float = 0.0) -> float:
    """Extract a float from *data*, coercing and clamping to >= 0."""
    raw = data.get(key, default)
    try:
        value = float(raw)
    except (TypeError, ValueError):
        logger.warning("Non-numeric value for '%s': %r, defaulting to %s", key, raw, default)
        return default
    return max(value, 0.0)


def _safe_int(data: dict[str, Any], key: str, default: int = 0) -> int:
    """Extract an int from *data*, coercing and clamping to >= 0."""
    raw = data.get(key, default)
    try:
        value = int(raw)
    except (TypeError, ValueError):
        logger.warning("Non-numeric value for '%s': %r, defaulting to %s", key, raw, default)
        return default
    return max(value, 0)

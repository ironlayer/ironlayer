"""Spark/Databricks metrics parser and cost estimation.

Translates the raw metrics dictionary returned by a Databricks run output
into a normalised flat structure suitable for :class:`RunTelemetry`, and
provides a simple cost model based on the per-second rates defined in
:mod:`core_engine.executor.cluster_templates`.
"""

from __future__ import annotations

import logging
from typing import Any

from core_engine.executor.cluster_templates import get_cost_rate

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Well-known keys in the raw Databricks / Spark metrics output.
# ---------------------------------------------------------------------------

_KEY_SHUFFLE_READ = "shuffleReadBytesTotal"
_KEY_SHUFFLE_WRITE = "shuffleWriteBytesTotal"
_KEY_EXECUTOR_RUN_TIME = "executorRunTimeMs"
_KEY_GC_TIME = "jvmGcTimeMs"
_KEY_PEAK_MEMORY = "peakExecutionMemoryBytes"
_KEY_INPUT_ROWS = "inputRows"
_KEY_OUTPUT_ROWS = "outputRows"
_KEY_PARTITION_COUNT = "partitionCount"
_KEY_RUNTIME_SECONDS = "runtimeSeconds"
_KEY_CLUSTER_ID = "clusterId"

# Alternate key forms that Databricks surfaces in different API responses.
_ALT_KEYS: dict[str, list[str]] = {
    _KEY_SHUFFLE_READ: ["shuffle_read_bytes", "shuffleReadBytes"],
    _KEY_SHUFFLE_WRITE: ["shuffle_write_bytes", "shuffleWriteBytes"],
    _KEY_EXECUTOR_RUN_TIME: ["executor_run_time", "executorRunTime", "executor_run_time_ms"],
    _KEY_GC_TIME: ["gc_time", "gcTime", "jvm_gc_time_ms"],
    _KEY_PEAK_MEMORY: ["peak_memory_bytes", "peakMemoryBytes", "peak_execution_memory_bytes"],
    _KEY_INPUT_ROWS: ["input_rows", "numInputRows"],
    _KEY_OUTPUT_ROWS: ["output_rows", "numOutputRows"],
    _KEY_PARTITION_COUNT: ["partition_count", "numPartitions"],
    _KEY_RUNTIME_SECONDS: ["runtime_seconds"],
    _KEY_CLUSTER_ID: ["cluster_id"],
}


def _resolve(raw: dict[str, Any], primary: str, alternatives: list[str], default: Any = 0) -> Any:
    """Resolve a value from *raw* by trying the primary key then alternatives."""
    if primary in raw:
        return raw[primary]
    for alt in alternatives:
        if alt in raw:
            return raw[alt]
    return default


def _safe_int(value: Any, default: int = 0) -> int:
    """Coerce *value* to a non-negative integer."""
    try:
        v = int(value)
    except (TypeError, ValueError):
        return default
    return max(v, 0)


def _safe_float(value: Any, default: float = 0.0) -> float:
    """Coerce *value* to a non-negative float."""
    try:
        v = float(value)
    except (TypeError, ValueError):
        return default
    return max(v, 0.0)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def parse_spark_metrics(raw_metrics: dict[str, Any]) -> dict[str, Any]:
    """Normalise raw Databricks/Spark metrics into a flat dictionary.

    The returned dictionary contains keys that align with
    :class:`RunTelemetry` fields plus additional Spark-specific diagnostics:

    - ``shuffle_read_bytes`` (int)
    - ``shuffle_write_bytes`` (int)
    - ``shuffle_bytes`` (int) -- sum of read + write
    - ``executor_run_time_ms`` (int)
    - ``gc_time_ms`` (int)
    - ``peak_memory_bytes`` (int)
    - ``input_rows`` (int)
    - ``output_rows`` (int)
    - ``partition_count`` (int)
    - ``runtime_seconds`` (float)
    - ``cluster_id`` (str | None)

    Parameters
    ----------
    raw_metrics:
        The raw dictionary from Databricks run output or Spark query profile.

    Returns
    -------
    dict
        Normalised metrics ready for :func:`capture_run_telemetry`.
    """
    shuffle_read = _safe_int(_resolve(raw_metrics, _KEY_SHUFFLE_READ, _ALT_KEYS[_KEY_SHUFFLE_READ]))
    shuffle_write = _safe_int(_resolve(raw_metrics, _KEY_SHUFFLE_WRITE, _ALT_KEYS[_KEY_SHUFFLE_WRITE]))
    executor_run_time_ms = _safe_int(_resolve(raw_metrics, _KEY_EXECUTOR_RUN_TIME, _ALT_KEYS[_KEY_EXECUTOR_RUN_TIME]))
    gc_time_ms = _safe_int(_resolve(raw_metrics, _KEY_GC_TIME, _ALT_KEYS[_KEY_GC_TIME]))
    peak_memory = _safe_int(_resolve(raw_metrics, _KEY_PEAK_MEMORY, _ALT_KEYS[_KEY_PEAK_MEMORY]))
    input_rows = _safe_int(_resolve(raw_metrics, _KEY_INPUT_ROWS, _ALT_KEYS[_KEY_INPUT_ROWS]))
    output_rows = _safe_int(_resolve(raw_metrics, _KEY_OUTPUT_ROWS, _ALT_KEYS[_KEY_OUTPUT_ROWS]))
    partition_count = _safe_int(_resolve(raw_metrics, _KEY_PARTITION_COUNT, _ALT_KEYS[_KEY_PARTITION_COUNT]))
    runtime_seconds = _safe_float(_resolve(raw_metrics, _KEY_RUNTIME_SECONDS, _ALT_KEYS[_KEY_RUNTIME_SECONDS]))
    cluster_id_raw = _resolve(raw_metrics, _KEY_CLUSTER_ID, _ALT_KEYS[_KEY_CLUSTER_ID], default=None)
    cluster_id = str(cluster_id_raw) if cluster_id_raw is not None else None

    return {
        "shuffle_read_bytes": shuffle_read,
        "shuffle_write_bytes": shuffle_write,
        "shuffle_bytes": shuffle_read + shuffle_write,
        "executor_run_time_ms": executor_run_time_ms,
        "gc_time_ms": gc_time_ms,
        "peak_memory_bytes": peak_memory,
        "input_rows": input_rows,
        "output_rows": output_rows,
        "partition_count": partition_count,
        "runtime_seconds": runtime_seconds,
        "cluster_id": cluster_id,
    }


def compute_run_cost(runtime_seconds: float, cluster_size: str) -> float:
    """Estimate the USD cost for a run given its duration and cluster size.

    Parameters
    ----------
    runtime_seconds:
        Total wall-clock seconds the cluster was active.
    cluster_size:
        T-shirt size (``"small"``, ``"medium"``, or ``"large"``).

    Returns
    -------
    float
        Estimated cost in USD, rounded to six decimal places.

    Raises
    ------
    ValueError
        If *cluster_size* is not recognised.
    """
    rate = get_cost_rate(cluster_size)
    cost = max(runtime_seconds, 0.0) * rate
    return round(cost, 6)

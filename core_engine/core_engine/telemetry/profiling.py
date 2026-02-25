"""Continuous performance profiling for hot-path operations.

Provides a ``@profile_operation(name)`` decorator that instruments
both sync and async functions with high-resolution timing (perf_counter_ns)
and optional memory tracking.  Results are recorded to a thread-safe
:class:`ProfileCollector` singleton and logged at DEBUG level.

Usage::

    from core_engine.telemetry.profiling import profile_operation

    @profile_operation("dag.build")
    def build_dag(models):
        ...

    @profile_operation("sql.normalize")
    def normalize_sql(sql):
        ...

The collector stores the last ``max_results`` per operation and
exposes ``get_stats()`` for p50/p95/p99/mean aggregation.
"""

from __future__ import annotations

import asyncio
import functools
import logging
import threading
import time
from collections import deque
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any, TypeVar

logger = logging.getLogger(__name__)

F = TypeVar("F", bound=Callable[..., Any])


# ---------------------------------------------------------------------------
# Profile result
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ProfileResult:
    """Immutable record of a single profiled operation."""

    operation: str
    duration_ms: float
    peak_memory_mb: float
    metadata: dict[str, Any] = field(default_factory=dict)


# ---------------------------------------------------------------------------
# Profile collector (thread-safe singleton)
# ---------------------------------------------------------------------------


class ProfileCollector:
    """Thread-safe collector that stores recent profile results per operation.

    Parameters
    ----------
    max_results:
        Maximum number of results to retain per operation name.
    """

    _instance: ProfileCollector | None = None
    _lock_cls = threading.Lock()

    def __init__(self, max_results: int = 100) -> None:
        self._max_results = max_results
        self._data: dict[str, deque[ProfileResult]] = {}
        self._lock = threading.Lock()

    @classmethod
    def get_instance(cls) -> ProfileCollector:
        """Return the module-level singleton, creating it if needed."""
        if cls._instance is None:
            with cls._lock_cls:
                if cls._instance is None:
                    cls._instance = ProfileCollector()
        return cls._instance

    @classmethod
    def reset(cls) -> None:
        """Reset the singleton (for testing)."""
        with cls._lock_cls:
            cls._instance = None

    def record(self, result: ProfileResult) -> None:
        """Record a profile result.  Thread-safe."""
        with self._lock:
            if result.operation not in self._data:
                self._data[result.operation] = deque(maxlen=self._max_results)
            self._data[result.operation].append(result)

    def get_stats(self, operation: str) -> dict[str, Any] | None:
        """Compute aggregate statistics for an operation.

        Returns ``None`` if no results exist for the operation.

        Returns
        -------
        dict
            ``{"operation": str, "count": int, "mean_ms": float,
              "p50_ms": float, "p95_ms": float, "p99_ms": float,
              "min_ms": float, "max_ms": float}``
        """
        with self._lock:
            results = self._data.get(operation)
            if not results:
                return None
            durations = sorted(r.duration_ms for r in results)

        count = len(durations)
        return {
            "operation": operation,
            "count": count,
            "mean_ms": round(sum(durations) / count, 3),
            "p50_ms": round(self._percentile(durations, 50), 3),
            "p95_ms": round(self._percentile(durations, 95), 3),
            "p99_ms": round(self._percentile(durations, 99), 3),
            "min_ms": round(durations[0], 3),
            "max_ms": round(durations[-1], 3),
        }

    def get_all_stats(self) -> list[dict[str, Any]]:
        """Return stats for all tracked operations, sorted by name."""
        with self._lock:
            operations = sorted(self._data.keys())
        results = []
        for op in operations:
            stats = self.get_stats(op)
            if stats is not None:
                results.append(stats)
        return results

    def clear(self) -> None:
        """Clear all stored results."""
        with self._lock:
            self._data.clear()

    @staticmethod
    def _percentile(sorted_data: list[float], p: float) -> float:
        """Compute the p-th percentile using linear interpolation."""
        if not sorted_data:
            return 0.0
        n = len(sorted_data)
        k = (p / 100.0) * (n - 1)
        floor_k = int(k)
        ceil_k = min(floor_k + 1, n - 1)
        frac = k - floor_k
        return sorted_data[floor_k] + frac * (sorted_data[ceil_k] - sorted_data[floor_k])


# ---------------------------------------------------------------------------
# Decorator
# ---------------------------------------------------------------------------


def profile_operation(name: str) -> Callable[[F], F]:
    """Decorator that profiles a sync or async function.

    Records execution time via ``time.perf_counter_ns()`` and logs
    the result at DEBUG level.  The result is also stored in the
    :class:`ProfileCollector` singleton.

    Parameters
    ----------
    name:
        The operation name for grouping (e.g. ``"dag.build"``).
    """

    def decorator(func: F) -> F:
        if asyncio.iscoroutinefunction(func):

            @functools.wraps(func)
            async def async_wrapper(*args: Any, **kwargs: Any) -> Any:
                start_ns = time.perf_counter_ns()
                try:
                    return await func(*args, **kwargs)
                finally:
                    elapsed_ns = time.perf_counter_ns() - start_ns
                    duration_ms = elapsed_ns / 1_000_000
                    result = ProfileResult(
                        operation=name,
                        duration_ms=round(duration_ms, 3),
                        peak_memory_mb=0.0,
                    )
                    ProfileCollector.get_instance().record(result)
                    logger.debug(
                        "PROFILE %s: %.3f ms",
                        name,
                        duration_ms,
                    )

            return async_wrapper  # type: ignore[return-value]
        else:

            @functools.wraps(func)
            def sync_wrapper(*args: Any, **kwargs: Any) -> Any:
                start_ns = time.perf_counter_ns()
                try:
                    return func(*args, **kwargs)
                finally:
                    elapsed_ns = time.perf_counter_ns() - start_ns
                    duration_ms = elapsed_ns / 1_000_000
                    result = ProfileResult(
                        operation=name,
                        duration_ms=round(duration_ms, 3),
                        peak_memory_mb=0.0,
                    )
                    ProfileCollector.get_instance().record(result)
                    logger.debug(
                        "PROFILE %s: %.3f ms",
                        name,
                        duration_ms,
                    )

            return sync_wrapper  # type: ignore[return-value]

    return decorator

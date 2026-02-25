"""Product KPI thresholds and performance gates.

Defines quantitative metrics that serve as go/no-go criteria for
productisation.  These thresholds are checked at runtime and reported
via the telemetry system.

**Target KPIs**:
- Plan generation time <= 30s for 200 models
- Plan accuracy >= 95% (plans execute without unexpected failures)
- Average cost savings > 15% vs naive full-refresh baseline
- Semantic diff false-positive rate < 10%
- P95 API response time < 2s

Each KPI can be evaluated against historical data and emitted as a
metrics event.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import UTC, datetime
from enum import Enum
from typing import Any

logger = logging.getLogger(__name__)


class KPIStatus(str, Enum):
    """Evaluation result for a single KPI."""

    PASSING = "passing"
    WARNING = "warning"
    FAILING = "failing"
    INSUFFICIENT_DATA = "insufficient_data"


@dataclass(frozen=True)
class KPIThreshold:
    """A single KPI definition with threshold values."""

    name: str
    description: str
    unit: str
    target_value: float
    warning_value: float
    direction: str  # "lower_is_better" or "higher_is_better"

    def evaluate(self, actual_value: float | None) -> KPIStatus:
        """Evaluate an actual metric against this threshold."""
        if actual_value is None:
            return KPIStatus.INSUFFICIENT_DATA

        if self.direction == "lower_is_better":
            if actual_value <= self.target_value:
                return KPIStatus.PASSING
            elif actual_value <= self.warning_value:
                return KPIStatus.WARNING
            else:
                return KPIStatus.FAILING
        else:
            if actual_value >= self.target_value:
                return KPIStatus.PASSING
            elif actual_value >= self.warning_value:
                return KPIStatus.WARNING
            else:
                return KPIStatus.FAILING


@dataclass(frozen=True)
class KPIResult:
    """Result of evaluating a single KPI."""

    kpi: KPIThreshold
    actual_value: float | None
    status: KPIStatus
    evaluated_at: datetime
    sample_size: int


# ---------------------------------------------------------------------------
# Product KPI definitions
# ---------------------------------------------------------------------------

PLAN_GENERATION_TIME = KPIThreshold(
    name="plan_generation_time_seconds",
    description="Plan generation time for up to 200 models",
    unit="seconds",
    target_value=30.0,
    warning_value=45.0,
    direction="lower_is_better",
)

PLAN_ACCURACY = KPIThreshold(
    name="plan_accuracy_percent",
    description="Percentage of plans that execute without unexpected failures",
    unit="percent",
    target_value=95.0,
    warning_value=90.0,
    direction="higher_is_better",
)

COST_SAVINGS = KPIThreshold(
    name="cost_savings_percent",
    description="Average cost savings vs naive full-refresh baseline",
    unit="percent",
    target_value=15.0,
    warning_value=10.0,
    direction="higher_is_better",
)

SEMANTIC_DIFF_FP_RATE = KPIThreshold(
    name="semantic_diff_false_positive_rate",
    description="False positive rate of semantic diff (unnecessary full rebuilds)",
    unit="percent",
    target_value=10.0,
    warning_value=20.0,
    direction="lower_is_better",
)

API_P95_RESPONSE_TIME = KPIThreshold(
    name="api_p95_response_time_seconds",
    description="P95 API endpoint response time",
    unit="seconds",
    target_value=2.0,
    warning_value=5.0,
    direction="lower_is_better",
)

PLANNER_DETERMINISM = KPIThreshold(
    name="planner_determinism_rate",
    description="Rate at which identical inputs produce identical plans",
    unit="percent",
    target_value=100.0,
    warning_value=100.0,
    direction="higher_is_better",
)

AI_SUGGESTION_ACCEPTANCE = KPIThreshold(
    name="ai_suggestion_acceptance_rate",
    description="Rate at which AI suggestions pass validation and are accepted by users",
    unit="percent",
    target_value=60.0,
    warning_value=40.0,
    direction="higher_is_better",
)

ALL_KPIS: list[KPIThreshold] = [
    PLAN_GENERATION_TIME,
    PLAN_ACCURACY,
    COST_SAVINGS,
    SEMANTIC_DIFF_FP_RATE,
    API_P95_RESPONSE_TIME,
    PLANNER_DETERMINISM,
    AI_SUGGESTION_ACCEPTANCE,
]


class KPIEvaluator:
    """Evaluates product KPIs against historical metrics data.

    Parameters
    ----------
    metrics_data:
        Dictionary mapping KPI names to lists of observed values.
    """

    def __init__(self, metrics_data: dict[str, list[float]] | None = None) -> None:
        self._data = metrics_data or {}

    def evaluate_all(self) -> list[KPIResult]:
        """Evaluate all defined KPIs and return results."""
        results: list[KPIResult] = []
        now = datetime.now(UTC)

        for kpi in ALL_KPIS:
            values = self._data.get(kpi.name, [])
            if not values:
                results.append(
                    KPIResult(
                        kpi=kpi,
                        actual_value=None,
                        status=KPIStatus.INSUFFICIENT_DATA,
                        evaluated_at=now,
                        sample_size=0,
                    )
                )
                continue

            # Compute the appropriate aggregate
            if kpi.direction == "lower_is_better":
                # For latency-type metrics, use P95
                actual = _percentile(sorted(values), 0.95)
            else:
                # For rate-type metrics, use mean
                actual = sum(values) / len(values)

            status = kpi.evaluate(actual)
            results.append(
                KPIResult(
                    kpi=kpi,
                    actual_value=round(actual, 4),
                    status=status,
                    evaluated_at=now,
                    sample_size=len(values),
                )
            )

        return results

    def evaluate_single(self, kpi_name: str) -> KPIResult | None:
        """Evaluate a single KPI by name."""
        for kpi in ALL_KPIS:
            if kpi.name == kpi_name:
                values = self._data.get(kpi.name, [])
                now = datetime.now(UTC)
                if not values:
                    return KPIResult(
                        kpi=kpi,
                        actual_value=None,
                        status=KPIStatus.INSUFFICIENT_DATA,
                        evaluated_at=now,
                        sample_size=0,
                    )
                if kpi.direction == "lower_is_better":
                    actual = _percentile(sorted(values), 0.95)
                else:
                    actual = sum(values) / len(values)
                return KPIResult(
                    kpi=kpi,
                    actual_value=round(actual, 4),
                    status=kpi.evaluate(actual),
                    evaluated_at=now,
                    sample_size=len(values),
                )
        return None

    def generate_report(self) -> dict[str, Any]:
        """Generate a full KPI dashboard report."""
        results = self.evaluate_all()
        passing = sum(1 for r in results if r.status == KPIStatus.PASSING)
        failing = sum(1 for r in results if r.status == KPIStatus.FAILING)
        total = len(results)

        return {
            "evaluated_at": datetime.now(UTC).isoformat(),
            "summary": {
                "total_kpis": total,
                "passing": passing,
                "warning": sum(1 for r in results if r.status == KPIStatus.WARNING),
                "failing": failing,
                "insufficient_data": sum(1 for r in results if r.status == KPIStatus.INSUFFICIENT_DATA),
                "health": "healthy" if failing == 0 else "degraded" if failing <= 2 else "unhealthy",
            },
            "kpis": [
                {
                    "name": r.kpi.name,
                    "description": r.kpi.description,
                    "target": r.kpi.target_value,
                    "actual": r.actual_value,
                    "unit": r.kpi.unit,
                    "status": r.status.value,
                    "sample_size": r.sample_size,
                }
                for r in results
            ],
        }


def _percentile(sorted_values: list[float], pct: float) -> float:
    """Compute a percentile from a sorted list."""
    if not sorted_values:
        return 0.0
    idx = int(len(sorted_values) * pct)
    idx = min(idx, len(sorted_values) - 1)
    return sorted_values[idx]

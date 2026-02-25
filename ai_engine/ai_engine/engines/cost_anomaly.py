"""Cost anomaly detection using Z-score and IQR methods.

Analyses historical cost data to identify anomalous cost spikes or drops.
Severity is classified based on standard deviation distance:

- **minor**: 2–3 standard deviations
- **major**: 3–4 standard deviations
- **critical**: > 4 standard deviations

The detector is fully deterministic and stateless.

INVARIANT: This engine **never** mutates plans.  It only returns
advisory metadata.
"""

from __future__ import annotations

import logging
import math

from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)


class AnomalyReport(BaseModel):
    """Anomaly analysis for a single model's cost history."""

    model_name: str = Field(..., description="Model analysed.")
    is_anomaly: bool = Field(default=False, description="Whether an anomaly was detected.")
    anomaly_type: str = Field(default="none", description="Type: 'spike', 'drop', or 'none'.")
    severity: str = Field(
        default="none",
        description="Severity: 'none', 'minor', 'major', or 'critical'.",
    )
    z_score: float = Field(default=0.0, description="Z-score of the latest cost relative to history.")
    percentile: float = Field(
        default=50.0,
        ge=0.0,
        le=100.0,
        description="Percentile rank of the latest cost within the history.",
    )
    suggested_investigation: str = Field(
        default="No anomaly detected.",
        description="Recommended next step.",
    )


class CostAnomalyDetector:
    """Detect cost anomalies using Z-score and IQR methods.

    Fully deterministic and stateless — all state is passed in via
    the method arguments.

    Parameters
    ----------
    z_score_minor:
        Z-score threshold for minor anomalies (default 2.0).
    z_score_major:
        Z-score threshold for major anomalies (default 3.0).
    z_score_critical:
        Z-score threshold for critical anomalies (default 4.0).
    iqr_factor:
        IQR multiplier for the fence (default 1.5).
    """

    def __init__(
        self,
        z_score_minor: float = 2.0,
        z_score_major: float = 3.0,
        z_score_critical: float = 4.0,
        iqr_factor: float = 1.5,
    ) -> None:
        self._z_minor = z_score_minor
        self._z_major = z_score_major
        self._z_critical = z_score_critical
        self._iqr_factor = iqr_factor

    def detect(
        self,
        model_name: str,
        cost_history: list[float],
        latest_cost: float | None = None,
    ) -> AnomalyReport:
        """Analyse a model's cost history for anomalies.

        Parameters
        ----------
        model_name:
            Identifier for the model being analysed.
        cost_history:
            Historical cost values, oldest first.  Must contain at least
            3 data points for meaningful analysis.
        latest_cost:
            The most recent cost to evaluate.  If ``None``, the last
            element of ``cost_history`` is used.
        """
        if len(cost_history) < 3:
            return AnomalyReport(
                model_name=model_name,
                suggested_investigation=("Insufficient data (< 3 points) for anomaly detection."),
            )

        if latest_cost is None:
            latest_cost = cost_history[-1]

        # --- Z-score analysis ---
        mean = sum(cost_history) / len(cost_history)
        variance = sum((x - mean) ** 2 for x in cost_history) / len(cost_history)
        std_dev = math.sqrt(variance) if variance > 0 else 0.0

        z_score = 0.0
        if std_dev > 0:
            z_score = (latest_cost - mean) / std_dev

        # --- IQR analysis ---
        sorted_costs = sorted(cost_history)
        q1 = self._percentile(sorted_costs, 25)
        q3 = self._percentile(sorted_costs, 75)
        iqr = q3 - q1
        lower_fence = q1 - self._iqr_factor * iqr
        upper_fence = q3 + self._iqr_factor * iqr

        # --- Percentile of latest cost ---
        below_count = sum(1 for c in cost_history if c < latest_cost)
        equal_count = sum(1 for c in cost_history if c == latest_cost)
        percentile = round((below_count + 0.5 * equal_count) / len(cost_history) * 100.0, 2)

        # --- Classification ---
        abs_z = abs(z_score)
        iqr_anomaly = latest_cost < lower_fence or latest_cost > upper_fence

        is_anomaly = abs_z >= self._z_minor or iqr_anomaly
        anomaly_type = "none"
        severity = "none"
        suggestion = "No anomaly detected."

        if is_anomaly:
            anomaly_type = "spike" if z_score > 0 else "drop"

            if abs_z >= self._z_critical:
                severity = "critical"
            elif abs_z >= self._z_major:
                severity = "major"
            else:
                severity = "minor"

            if anomaly_type == "spike":
                suggestion = (
                    f"Cost spike detected ({severity}): latest cost "
                    f"${latest_cost:.2f} is {abs_z:.1f} std devs above mean "
                    f"${mean:.2f}.  Investigate query plan changes, data volume "
                    f"growth, or cluster configuration drift."
                )
            else:
                suggestion = (
                    f"Cost drop detected ({severity}): latest cost "
                    f"${latest_cost:.2f} is {abs_z:.1f} std devs below mean "
                    f"${mean:.2f}.  Verify that the model executed completely "
                    f"and check for upstream data availability issues."
                )

        return AnomalyReport(
            model_name=model_name,
            is_anomaly=is_anomaly,
            anomaly_type=anomaly_type,
            severity=severity,
            z_score=round(z_score, 4),
            percentile=percentile,
            suggested_investigation=suggestion,
        )

    def detect_batch(
        self,
        models: dict[str, list[float]],
    ) -> list[AnomalyReport]:
        """Analyse multiple models, returning results sorted by severity.

        Parameters
        ----------
        models:
            Mapping of ``model_name → cost_history``.

        Returns
        -------
        list[AnomalyReport]
            Results sorted by severity (critical → major → minor → none),
            then by absolute z-score descending within each severity level.
        """
        severity_order = {"critical": 0, "major": 1, "minor": 2, "none": 3}
        reports = [self.detect(name, history) for name, history in sorted(models.items())]
        reports.sort(key=lambda r: (severity_order.get(r.severity, 3), -abs(r.z_score)))
        return reports

    @staticmethod
    def _percentile(sorted_data: list[float], p: float) -> float:
        """Compute the p-th percentile of sorted data using linear interpolation."""
        if not sorted_data:
            return 0.0
        n = len(sorted_data)
        k = (p / 100.0) * (n - 1)
        floor_k = int(math.floor(k))
        ceil_k = min(floor_k + 1, n - 1)
        frac = k - floor_k
        return sorted_data[floor_k] + frac * (sorted_data[ceil_k] - sorted_data[floor_k])

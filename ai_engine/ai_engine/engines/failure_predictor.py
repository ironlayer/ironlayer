"""Failure prediction engine -- logistic model on historical run signals.

Predicts the probability that a model's next execution will fail, based
on observable trends in recent run history:

    * Historical failure rate
    * Runtime trend (acceleration suggests resource pressure)
    * Shuffle growth (data volume growth signals capacity risk)
    * Time since last success (staleness)
    * Consecutive recent failures (momentum)

The engine is **fully deterministic** -- no ML training required, no LLM,
no randomness.  It uses a hand-tuned logistic scoring function that
converts signal weights into a calibrated probability.

INVARIANT: This engine **never** mutates execution plans.
"""

from __future__ import annotations

import logging
import math
from dataclasses import dataclass

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

# Default thresholds for flagging at-risk models
_DEFAULT_WARNING_THRESHOLD = 0.3
_DEFAULT_CRITICAL_THRESHOLD = 0.6


# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class FailurePrediction:
    """Output of the failure prediction engine."""

    model_name: str
    failure_probability: float  # 0.0 - 1.0
    risk_level: str  # "low", "medium", "high"
    factors: list[str]  # human-readable contributing factor descriptions
    suggested_actions: list[str]  # actionable recommendations


@dataclass
class RunHistory:
    """Summarised run history for a single model.

    This is the input to the predictor — built from ``RunRepository``
    data by the calling service.  The predictor itself has no database
    dependency.
    """

    model_name: str
    total_runs: int = 0
    failed_runs: int = 0
    recent_runs: int = 0  # runs in last 7 days
    recent_failures: int = 0  # failures in last 7 days
    consecutive_failures: int = 0  # streak from most recent run backward
    avg_runtime_seconds: float = 0.0
    recent_avg_runtime_seconds: float = 0.0  # last 7 days avg
    runtime_trend: float = 0.0  # % change in runtime (recent vs historical)
    avg_shuffle_bytes: float = 0.0
    recent_avg_shuffle_bytes: float = 0.0
    shuffle_trend: float = 0.0  # % change in shuffle bytes
    hours_since_last_success: float = 0.0
    last_error_type: str | None = None


# ---------------------------------------------------------------------------
# Predictor
# ---------------------------------------------------------------------------


class FailurePredictor:
    """Predict failure probability for a model based on run history signals.

    The scoring function is a weighted logistic combination of normalised
    signals.  Each signal contributes a weight between 0.0 and 1.0, and
    the final score is passed through a sigmoid to produce a calibrated
    probability.

    Parameters
    ----------
    warning_threshold:
        Probability above which a model is flagged as "medium" risk.
    critical_threshold:
        Probability above which a model is flagged as "high" risk.
    """

    def __init__(
        self,
        warning_threshold: float = _DEFAULT_WARNING_THRESHOLD,
        critical_threshold: float = _DEFAULT_CRITICAL_THRESHOLD,
    ) -> None:
        self._warning_threshold = warning_threshold
        self._critical_threshold = critical_threshold

    def predict(self, history: RunHistory) -> FailurePrediction:
        """Compute failure probability and generate actionable insights."""

        score = 0.0
        factors: list[str] = []
        actions: list[str] = []

        # --- Signal 1: Historical failure rate (weight: 2.5) ---
        if history.total_runs > 0:
            failure_rate = history.failed_runs / history.total_runs
            signal = min(failure_rate / 0.3, 1.0)  # saturates at 30% failure rate
            score += signal * 2.5
            if failure_rate > 0.05:
                factors.append(
                    f"Historical failure rate: {failure_rate:.1%} " f"({history.failed_runs}/{history.total_runs} runs)"
                )
            if failure_rate > 0.15:
                actions.append(
                    "Investigate recurring failure patterns — " "consider reviewing error logs for systematic issues"
                )

        # --- Signal 2: Recent failure acceleration (weight: 2.0) ---
        if history.recent_runs > 0:
            recent_rate = history.recent_failures / history.recent_runs
            historical_rate = history.failed_runs / history.total_runs if history.total_runs > 0 else 0.0
            if recent_rate > historical_rate * 1.5 and history.recent_failures > 0:
                acceleration = min((recent_rate - historical_rate) / 0.2, 1.0)
                score += acceleration * 2.0
                factors.append(
                    f"Recent failure rate ({recent_rate:.1%}) exceeds " f"historical average ({historical_rate:.1%})"
                )
                actions.append("Recent failure rate is accelerating — " "prioritise investigation of recent changes")

        # --- Signal 3: Consecutive failures (weight: 1.5) ---
        if history.consecutive_failures > 0:
            signal = min(history.consecutive_failures / 3.0, 1.0)
            score += signal * 1.5
            factors.append(f"Consecutive failures: {history.consecutive_failures} " f"(most recent runs all failed)")
            if history.consecutive_failures >= 3:
                actions.append("Model has failed 3+ times in a row — " "manual intervention strongly recommended")

        # --- Signal 4: Runtime trend (weight: 1.0) ---
        if history.runtime_trend > 0.2 and history.avg_runtime_seconds > 0:
            signal = min(history.runtime_trend / 1.0, 1.0)  # saturates at 100% growth
            score += signal * 1.0
            factors.append(
                f"Runtime trend: +{history.runtime_trend:.0%} "
                f"(recent avg {history.recent_avg_runtime_seconds:.0f}s "
                f"vs historical {history.avg_runtime_seconds:.0f}s)"
            )
            if history.runtime_trend > 0.5:
                actions.append(
                    "Runtime has grown significantly — " "consider reviewing data volume growth or query optimisation"
                )

        # --- Signal 5: Shuffle growth (weight: 0.8) ---
        if history.shuffle_trend > 0.3 and history.avg_shuffle_bytes > 0:
            signal = min(history.shuffle_trend / 1.5, 1.0)
            score += signal * 0.8
            factors.append(f"Shuffle volume trend: +{history.shuffle_trend:.0%} growth")
            if history.shuffle_trend > 1.0:
                actions.append(
                    "Data shuffle volume has more than doubled — " "review partition strategy and cluster sizing"
                )

        # --- Signal 6: Staleness (weight: 0.7) ---
        if history.hours_since_last_success > 168:  # > 1 week
            signal = min(history.hours_since_last_success / 720, 1.0)  # caps at 30 days
            score += signal * 0.7
            days = history.hours_since_last_success / 24
            factors.append(f"No successful run in {days:.0f} days")
            actions.append("Model hasn't succeeded recently — " "verify upstream data availability and configuration")

        # --- Signal 7: Known-bad error type (weight: 0.5) ---
        _transient_errors = {"timeout", "throttled", "network", "connection"}
        if (
            history.last_error_type
            and history.consecutive_failures > 0
            and history.last_error_type.lower() not in _transient_errors
        ):
            score += 0.5
            factors.append(f"Last error type: {history.last_error_type}")

        # --- Compute probability via sigmoid ---
        # Score range: [0, ~9.0], logistic midpoint at 3.5
        probability = _sigmoid(score, midpoint=3.5, steepness=1.2)

        # Determine risk level
        if probability >= self._critical_threshold:
            risk_level = "high"
        elif probability >= self._warning_threshold:
            risk_level = "medium"
        else:
            risk_level = "low"

        # Default factor/action for healthy models
        if not factors:
            factors.append("No significant risk signals detected")
        if not actions and probability < self._warning_threshold:
            actions.append("No action required — model is healthy")

        prediction = FailurePrediction(
            model_name=history.model_name,
            failure_probability=round(probability, 4),
            risk_level=risk_level,
            factors=factors,
            suggested_actions=actions,
        )

        logger.info(
            "Failure prediction: model=%s prob=%.4f risk=%s factors=%d",
            history.model_name,
            probability,
            risk_level,
            len(factors),
        )

        return prediction

    def predict_batch(
        self,
        histories: list[RunHistory],
    ) -> list[FailurePrediction]:
        """Predict failure probability for multiple models.

        Returns predictions sorted by descending failure probability.
        """
        predictions = [self.predict(h) for h in histories]
        predictions.sort(key=lambda p: p.failure_probability, reverse=True)
        return predictions


# ---------------------------------------------------------------------------
# Cost trend analysis
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class CostTrend:
    """Cost trend analysis output for a model."""

    model_name: str
    current_avg_cost_usd: float
    previous_avg_cost_usd: float
    cost_change_pct: float  # positive = cost increase
    projected_monthly_cost_usd: float
    trend_direction: str  # "increasing", "decreasing", "stable"
    factors: list[str]
    alert: bool  # True if cost growth exceeds threshold


def compute_cost_trend(
    model_name: str,
    recent_costs: list[float],
    historical_costs: list[float],
    runs_per_month: float = 30.0,
    alert_threshold_pct: float = 0.3,
) -> CostTrend:
    """Analyse cost trend for a model over two periods.

    Parameters
    ----------
    model_name:
        Name of the model.
    recent_costs:
        Costs from the recent period (e.g. last 7 days).
    historical_costs:
        Costs from the historical baseline (e.g. last 30 days).
    runs_per_month:
        Expected runs per month for projection.
    alert_threshold_pct:
        Percentage growth that triggers an alert (default 30%).
    """
    recent_avg = sum(recent_costs) / len(recent_costs) if recent_costs else 0.0
    historical_avg = sum(historical_costs) / len(historical_costs) if historical_costs else 0.0

    if historical_avg > 0.001:
        change_pct = (recent_avg - historical_avg) / historical_avg
    elif recent_avg > 0.001:
        change_pct = 1.0  # new cost where none existed
    else:
        change_pct = 0.0

    projected_monthly = recent_avg * runs_per_month

    if change_pct > 0.05:
        direction = "increasing"
    elif change_pct < -0.05:
        direction = "decreasing"
    else:
        direction = "stable"

    factors: list[str] = []
    if change_pct > 0.05:
        factors.append(
            f"Average cost increased {change_pct:.0%}: " f"${historical_avg:.4f} → ${recent_avg:.4f} per run"
        )
    elif change_pct < -0.05:
        factors.append(
            f"Average cost decreased {abs(change_pct):.0%}: " f"${historical_avg:.4f} → ${recent_avg:.4f} per run"
        )
    else:
        factors.append(f"Cost is stable at ~${recent_avg:.4f} per run")

    factors.append(f"Projected monthly cost: ${projected_monthly:.2f}")

    alert = change_pct > alert_threshold_pct

    if alert:
        factors.append(f"ALERT: Cost growth ({change_pct:.0%}) exceeds " f"threshold ({alert_threshold_pct:.0%})")

    return CostTrend(
        model_name=model_name,
        current_avg_cost_usd=round(recent_avg, 6),
        previous_avg_cost_usd=round(historical_avg, 6),
        cost_change_pct=round(change_pct, 4),
        projected_monthly_cost_usd=round(projected_monthly, 2),
        trend_direction=direction,
        factors=factors,
        alert=alert,
    )


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _sigmoid(x: float, midpoint: float = 0.0, steepness: float = 1.0) -> float:
    """Standard logistic sigmoid function.

    Returns a value in (0, 1).  ``midpoint`` shifts the inflection
    point; ``steepness`` controls the slope.
    """
    z = steepness * (x - midpoint)
    # Clamp to avoid overflow
    z = max(-20.0, min(20.0, z))
    return 1.0 / (1.0 + math.exp(-z))

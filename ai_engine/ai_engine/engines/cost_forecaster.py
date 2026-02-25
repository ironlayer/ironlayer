"""Cost forecasting using simple exponential smoothing.

Projects future costs based on historical data using the exponential
smoothing formula:

    S_t = alpha * Y_t + (1 - alpha) * S_{t-1}

Where:
- ``Y_t`` is the observed cost at time *t*
- ``S_t`` is the smoothed value at time *t*
- ``alpha`` is the smoothing factor (0 < alpha <= 1)

Higher alpha values weight recent observations more heavily.

The forecaster is fully deterministic and stateless.

INVARIANT: This engine **never** mutates plans.  It only returns
advisory metadata.
"""

from __future__ import annotations

import logging
import math

from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)


class CostForecast(BaseModel):
    """Cost forecast for a single model."""

    model_name: str = Field(..., description="Model forecasted.")
    projected_7d_total: float = Field(
        default=0.0,
        ge=0.0,
        description="Projected total cost over the next 7 days.",
    )
    projected_30d_total: float = Field(
        default=0.0,
        ge=0.0,
        description="Projected total cost over the next 30 days.",
    )
    trend_direction: str = Field(
        default="stable",
        description="Trend: 'increasing', 'decreasing', or 'stable'.",
    )
    confidence_interval: list[float] = Field(
        default_factory=lambda: [0.0, 0.0],
        description="[lower, upper] 95% confidence bounds for 7-day projection.",
    )
    smoothing_factor: float = Field(
        default=0.3,
        ge=0.0,
        le=1.0,
        description="Alpha parameter used for smoothing.",
    )


class CostForecaster:
    """Forecast future costs using simple exponential smoothing.

    Fully deterministic and stateless.

    Parameters
    ----------
    alpha:
        Smoothing factor.  Higher values make the forecast more
        responsive to recent changes.  Default 0.3.
    trend_threshold:
        Minimum slope (per data point) to classify as increasing or
        decreasing rather than stable.  Default 0.05.
    """

    def __init__(
        self,
        alpha: float = 0.3,
        trend_threshold: float = 0.05,
    ) -> None:
        self._alpha = alpha
        self._trend_threshold = trend_threshold

    def forecast(
        self,
        model_name: str,
        cost_history: list[float],
        runs_per_day: float = 1.0,
    ) -> CostForecast:
        """Forecast future costs for a single model.

        Parameters
        ----------
        model_name:
            Identifier for the model.
        cost_history:
            Historical cost values (per run), oldest first.
        runs_per_day:
            Expected number of runs per day (for projection scaling).
        """
        if not cost_history:
            return CostForecast(
                model_name=model_name,
                smoothing_factor=self._alpha,
            )

        if len(cost_history) == 1:
            daily_cost = cost_history[0] * runs_per_day
            return CostForecast(
                model_name=model_name,
                projected_7d_total=round(daily_cost * 7, 4),
                projected_30d_total=round(daily_cost * 30, 4),
                trend_direction="stable",
                confidence_interval=[
                    round(daily_cost * 7 * 0.5, 4),
                    round(daily_cost * 7 * 1.5, 4),
                ],
                smoothing_factor=self._alpha,
            )

        # --- Exponential smoothing ---
        smoothed = self._exponential_smooth(cost_history)
        forecast_value = smoothed[-1]

        # --- Trend detection ---
        trend_direction = self._detect_trend(smoothed)

        # --- Projections ---
        daily_cost = forecast_value * runs_per_day
        projected_7d = round(daily_cost * 7, 4)
        projected_30d = round(daily_cost * 30, 4)

        # --- Confidence interval (based on forecast error variance) ---
        errors = [abs(actual - pred) for actual, pred in zip(cost_history[1:], smoothed[:-1], strict=False)]
        if errors:
            mean_error = sum(errors) / len(errors)
            error_var = sum((e - mean_error) ** 2 for e in errors) / len(errors)
            error_std = math.sqrt(error_var)
        else:
            error_std = forecast_value * 0.1  # fallback: 10% of forecast

        # 95% confidence: ±1.96 * std * sqrt(7 days) * runs_per_day
        margin = 1.96 * error_std * math.sqrt(7.0) * runs_per_day
        ci_lower = round(max(projected_7d - margin, 0.0), 4)
        ci_upper = round(projected_7d + margin, 4)

        return CostForecast(
            model_name=model_name,
            projected_7d_total=projected_7d,
            projected_30d_total=projected_30d,
            trend_direction=trend_direction,
            confidence_interval=[ci_lower, ci_upper],
            smoothing_factor=self._alpha,
        )

    def forecast_aggregate(
        self,
        models: dict[str, list[float]],
        runs_per_day: float = 1.0,
    ) -> CostForecast:
        """Aggregate forecast across all models.

        Parameters
        ----------
        models:
            Mapping of ``model_name → cost_history``.
        runs_per_day:
            Expected runs per day per model.

        Returns
        -------
        CostForecast
            Aggregated forecast with model_name set to ``"__aggregate__"``.
        """
        if not models:
            return CostForecast(
                model_name="__aggregate__",
                smoothing_factor=self._alpha,
            )

        individual = [self.forecast(name, history, runs_per_day) for name, history in sorted(models.items())]

        total_7d = sum(f.projected_7d_total for f in individual)
        total_30d = sum(f.projected_30d_total for f in individual)
        ci_lower = sum(f.confidence_interval[0] for f in individual)
        ci_upper = sum(f.confidence_interval[1] for f in individual)

        # Aggregate trend: majority vote.
        directions = [f.trend_direction for f in individual]
        inc_count = directions.count("increasing")
        dec_count = directions.count("decreasing")
        if inc_count > dec_count and inc_count > len(directions) / 2:
            agg_trend = "increasing"
        elif dec_count > inc_count and dec_count > len(directions) / 2:
            agg_trend = "decreasing"
        else:
            agg_trend = "stable"

        return CostForecast(
            model_name="__aggregate__",
            projected_7d_total=round(total_7d, 4),
            projected_30d_total=round(total_30d, 4),
            trend_direction=agg_trend,
            confidence_interval=[round(ci_lower, 4), round(ci_upper, 4)],
            smoothing_factor=self._alpha,
        )

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _exponential_smooth(self, data: list[float]) -> list[float]:
        """Apply simple exponential smoothing to the data series."""
        smoothed = [data[0]]
        for i in range(1, len(data)):
            s = self._alpha * data[i] + (1 - self._alpha) * smoothed[-1]
            smoothed.append(s)
        return smoothed

    def _detect_trend(self, smoothed: list[float]) -> str:
        """Detect trend direction from the smoothed series.

        Uses the slope of the smoothed series (last value vs first value,
        normalised by length) compared against ``trend_threshold``.
        """
        if len(smoothed) < 2:
            return "stable"

        # Compute normalised slope (change per data point).
        slope = (smoothed[-1] - smoothed[0]) / (len(smoothed) - 1)

        # Normalise by the mean to get relative slope.
        mean = sum(smoothed) / len(smoothed)
        if mean == 0:
            return "stable"

        relative_slope = slope / mean

        if relative_slope > self._trend_threshold:
            return "increasing"
        elif relative_slope < -self._trend_threshold:
            return "decreasing"
        return "stable"

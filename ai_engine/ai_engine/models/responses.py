"""Pydantic response models for every advisory endpoint."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

ChangeType = Literal[
    "non_breaking",
    "breaking",
    "metric_semantic",
    "rename_only",
    "partition_shift",
    "cosmetic",
]


class SemanticClassifyResponse(BaseModel):
    """Response from ``POST /semantic_classify``."""

    change_type: ChangeType = Field(..., description="Classified change category.")
    confidence: float = Field(..., ge=0.0, le=1.0, description="Classifier confidence.")
    requires_full_rebuild: bool = Field(
        ...,
        description="Whether the change requires a full historical rebuild.",
    )
    impact_scope: str = Field(
        ...,
        description="Human-readable description of the impact scope.",
    )


class CostPredictResponse(BaseModel):
    """Response from ``POST /predict_cost``."""

    estimated_runtime_minutes: float = Field(..., ge=0.0, description="Predicted runtime in minutes.")
    estimated_cost_usd: float = Field(..., ge=0.0, description="Predicted cost in USD.")
    confidence: float = Field(..., ge=0.0, le=1.0, description="Prediction confidence.")
    cost_lower_bound_usd: float = Field(
        default=0.0,
        ge=0.0,
        description="Lower bound of the cost estimate (based on confidence level).",
    )
    cost_upper_bound_usd: float = Field(
        default=0.0,
        ge=0.0,
        description="Upper bound of the cost estimate (based on confidence level).",
    )
    confidence_label: str = Field(
        default="low",
        description="Human-readable confidence label: 'low', 'medium', or 'high'.",
    )


class RiskScoreResponse(BaseModel):
    """Response from ``POST /risk_score``."""

    risk_score: float = Field(..., ge=0.0, le=10.0, description="Composite risk score.")
    business_critical: bool = Field(..., description="True when risk_score >= 7.0.")
    approval_required: bool = Field(
        ...,
        description=("True when the score exceeds the auto-approve threshold."),
    )
    risk_factors: list[str] = Field(
        ...,
        description="Human-readable list of factors that contributed to the score.",
    )


class SQLSuggestion(BaseModel):
    """A single SQL optimisation suggestion."""

    suggestion_type: str = Field(..., description="Category of the suggestion.")
    description: str = Field(..., description="Human-readable explanation.")
    rewritten_sql: str | None = Field(
        default=None,
        description="Rewritten SQL if the suggestion includes one.",
    )
    confidence: float = Field(..., ge=0.0, le=1.0, description="Confidence in the suggestion.")


class OptimizeSQLResponse(BaseModel):
    """Response from ``POST /optimize_sql``."""

    suggestions: list[SQLSuggestion] = Field(..., description="Ordered list of optimisation suggestions.")


class FragilityScoreResponse(BaseModel):
    """Response from ``POST /fragility_score``."""

    model_name: str = Field(..., description="Model that was scored.")
    own_risk: float = Field(..., ge=0.0, le=1.0, description="Model's own failure probability.")
    upstream_risk: float = Field(..., ge=0.0, description="Max decayed failure probability from ancestors.")
    cascade_risk: float = Field(..., ge=0.0, description="Downstream count × own failure probability.")
    fragility_score: float = Field(..., ge=0.0, le=10.0, description="Composite fragility score (0-10).")
    critical_path: bool = Field(
        ...,
        description="True if model sits on a path where all nodes have failure_prob > 0.3.",
    )
    risk_factors: list[str] = Field(..., description="Human-readable contributing factors.")


class FragilityBatchResponse(BaseModel):
    """Response from ``POST /fragility_score/batch``."""

    scores: list[FragilityScoreResponse] = Field(
        ..., description="Scores for all models, sorted by descending fragility."
    )


class CostAnomalyResponse(BaseModel):
    """Response from ``POST /cost_anomaly``."""

    model_name: str = Field(..., description="Model analysed.")
    is_anomaly: bool = Field(..., description="Whether an anomaly was detected.")
    anomaly_type: str = Field(..., description="Type: 'spike', 'drop', or 'none'.")
    severity: str = Field(..., description="Severity: 'none', 'minor', 'major', or 'critical'.")
    z_score: float = Field(..., description="Z-score of the latest cost.")
    percentile: float = Field(..., ge=0.0, le=100.0, description="Percentile rank of the latest cost.")
    suggested_investigation: str = Field(..., description="Recommended next step.")


class CostForecastResponse(BaseModel):
    """Response from ``POST /cost_forecast``."""

    model_name: str = Field(..., description="Model forecasted.")
    projected_7d_total: float = Field(..., ge=0.0, description="Projected total cost over the next 7 days.")
    projected_30d_total: float = Field(..., ge=0.0, description="Projected total cost over the next 30 days.")
    trend_direction: str = Field(..., description="Trend: 'increasing', 'decreasing', or 'stable'.")
    confidence_interval: list[float] = Field(
        ..., description="[lower, upper] 95% confidence bounds for 7-day projection."
    )
    smoothing_factor: float = Field(..., ge=0.0, le=1.0, description="Alpha parameter used for smoothing.")

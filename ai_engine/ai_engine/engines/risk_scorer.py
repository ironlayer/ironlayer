"""Deterministic rule-based risk scorer.

Produces a composite risk score in the range [0.0, 10.0] along with a
human-readable list of contributing factors.  The scorer is **fully
deterministic** -- no ML, no LLM, no randomness.

INVARIANT: This engine **never** mutates execution plans.  It only
returns advisory metadata.
"""

from __future__ import annotations

import logging

from ai_engine.models.requests import RiskScoreRequest
from ai_engine.models.responses import RiskScoreResponse

logger = logging.getLogger(__name__)

# Tags that signal elevated criticality
_CRITICAL_TAGS: frozenset[str] = frozenset({"critical", "production", "revenue"})


class RiskScorer:
    """Score the deployment risk of a model change."""

    def __init__(
        self,
        auto_approve_threshold: float = 3.0,
        manual_review_threshold: float = 7.0,
    ) -> None:
        self._auto_approve_threshold = auto_approve_threshold
        self._manual_review_threshold = manual_review_threshold

    def score(self, request: RiskScoreRequest) -> RiskScoreResponse:
        """Compute a deterministic risk score with contributing factors."""

        risk: float = 0.0
        factors: list[str] = []

        # 1. Downstream depth impact (capped at 6.0)
        if request.downstream_depth > 0:
            depth_score = min(request.downstream_depth * 1.5, 6.0)
            risk += depth_score
            factors.append(f"Downstream depth: {request.downstream_depth} model(s) affected (+{depth_score:.1f})")

        # 2. SLA tags
        if request.sla_tags:
            risk += 3.0
            tag_str = ", ".join(request.sla_tags)
            factors.append(f"SLA-tagged: {tag_str} (+3.0)")

        # 3. Dashboard dependencies
        if request.dashboard_dependencies:
            risk += 2.0
            dep_str = ", ".join(request.dashboard_dependencies)
            factors.append(f"Dashboard dependencies: {dep_str} (+2.0)")

        # 4. Historical failure rate
        if request.historical_failure_rate > 0.05:
            risk += 1.0
            factors.append(f"Historical failure rate: {request.historical_failure_rate:.1%} (+1.0)")

        # 5. Critical model tags
        matched_tags = _CRITICAL_TAGS & {t.lower() for t in request.model_tags}
        for tag in sorted(matched_tags):
            risk += 0.5
            factors.append(f"Critical tag: {tag} (+0.5)")

        # Clamp to [0.0, 10.0]
        risk = max(0.0, min(risk, 10.0))

        business_critical = risk >= self._manual_review_threshold
        approval_required = risk >= self._auto_approve_threshold

        logger.info(
            "Risk score for model=%s: %.1f (business_critical=%s, approval_required=%s)",
            request.model_name,
            risk,
            business_critical,
            approval_required,
        )

        return RiskScoreResponse(
            risk_score=round(risk, 2),
            business_critical=business_critical,
            approval_required=approval_required,
            risk_factors=factors,
        )

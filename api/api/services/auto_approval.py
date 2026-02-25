"""Guarded auto-approval engine for execution plans.

Feature-flagged via ``AUTO_APPROVAL_ENABLED=true``.  All auto-approval
decisions are persisted with full reasoning for audit trails.

**Auto-approval rules** (ALL must pass):

1. ``risk_score < configurable_threshold`` (default: 3.0)
2. ``estimated_cost_usd < configurable_threshold`` (default: 50.0)
3. ``change_type in {non_breaking, rename_only, cosmetic_only}``
4. No SLA-tagged models affected
5. No dashboard dependencies affected
6. No models with ``force_manual_review`` flag

If all pass -> auto-approve with logged reasoning.
If any fail -> require manual approval.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)


class AutoApprovalConfig(BaseModel):
    """Configuration for the auto-approval engine."""

    enabled: bool = Field(
        default=False,
        description="Master switch for auto-approval.  Must be explicitly enabled.",
    )
    max_risk_score: float = Field(
        default=3.0,
        ge=0.0,
        le=10.0,
        description="Plans with risk score >= this value require manual approval.",
    )
    max_cost_usd: float = Field(
        default=50.0,
        ge=0.0,
        description="Plans with estimated cost >= this value require manual approval.",
    )
    allowed_change_types: list[str] = Field(
        default_factory=lambda: [
            "non_breaking",
            "rename_only",
            "cosmetic_only",
            "COSMETIC_ONLY",
            "NO_CHANGE",
        ],
        description="Change types eligible for auto-approval.",
    )
    sla_tags: list[str] = Field(
        default_factory=lambda: ["sla", "sla-critical", "tier-1"],
        description="Tags that indicate SLA-bound models (blocks auto-approval).",
    )
    dashboard_tags: list[str] = Field(
        default_factory=lambda: ["dashboard", "executive-dashboard", "reporting"],
        description="Tags indicating dashboard dependencies (blocks auto-approval).",
    )
    force_manual_models: list[str] = Field(
        default_factory=list,
        description="Model names that always require manual review.",
    )


@dataclass(frozen=True)
class ApprovalRule:
    """A single rule evaluation result."""

    rule_name: str
    passed: bool
    reason: str


@dataclass(frozen=True)
class ApprovalDecision:
    """Complete auto-approval decision with audit trail."""

    auto_approved: bool
    rules_evaluated: list[ApprovalRule]
    decision_reason: str
    decided_at: datetime = field(default_factory=lambda: datetime.now(UTC))

    def to_dict(self) -> dict[str, Any]:
        """Serialize for persistence in the plans table."""
        return {
            "auto_approved": self.auto_approved,
            "rules": [
                {
                    "rule": r.rule_name,
                    "passed": r.passed,
                    "reason": r.reason,
                }
                for r in self.rules_evaluated
            ],
            "decision_reason": self.decision_reason,
            "decided_at": self.decided_at.isoformat(),
        }


class AutoApprovalEngine:
    """Evaluates plans against auto-approval rules.

    Parameters
    ----------
    config:
        Auto-approval configuration.  Defaults to disabled.
    """

    def __init__(self, config: AutoApprovalConfig | None = None) -> None:
        self._config = config or AutoApprovalConfig()

    @property
    def enabled(self) -> bool:
        return self._config.enabled

    def evaluate(
        self,
        plan_data: dict[str, Any],
        advisory_data: dict[str, Any] | None = None,
        model_tags: dict[str, list[str]] | None = None,
    ) -> ApprovalDecision:
        """Evaluate a plan for auto-approval eligibility.

        Parameters
        ----------
        plan_data:
            The plan dictionary (from plan_json).
        advisory_data:
            Optional AI advisory metadata keyed by model name.
        model_tags:
            Optional mapping of model_name -> list of tags.

        Returns
        -------
        ApprovalDecision
            Full decision with per-rule evaluation.
        """
        if not self._config.enabled:
            return ApprovalDecision(
                auto_approved=False,
                rules_evaluated=[
                    ApprovalRule(
                        rule_name="feature_enabled",
                        passed=False,
                        reason="Auto-approval is disabled",
                    )
                ],
                decision_reason="Auto-approval feature is not enabled",
            )

        if advisory_data is None:
            advisory_data = {}
        if model_tags is None:
            model_tags = {}

        rules: list[ApprovalRule] = []
        summary = plan_data.get("summary", {})
        plan_data.get("steps", [])
        models_changed = summary.get("models_changed", [])

        # Rule 1: Risk score check
        rules.append(self._check_risk_score(advisory_data))

        # Rule 2: Cost threshold
        rules.append(self._check_cost(summary))

        # Rule 3: Change type check
        rules.append(self._check_change_types(advisory_data, models_changed))

        # Rule 4: SLA-tagged models
        rules.append(self._check_sla_tags(models_changed, model_tags))

        # Rule 5: Dashboard dependencies
        rules.append(self._check_dashboard_deps(models_changed, model_tags))

        # Rule 6: Force manual review models
        rules.append(self._check_force_manual(models_changed))

        all_passed = all(r.passed for r in rules)
        failing_rules = [r for r in rules if not r.passed]

        if all_passed:
            reason = "All auto-approval rules passed"
        else:
            reasons = [f"{r.rule_name}: {r.reason}" for r in failing_rules]
            reason = f"Manual approval required: {'; '.join(reasons)}"

        decision = ApprovalDecision(
            auto_approved=all_passed,
            rules_evaluated=rules,
            decision_reason=reason,
        )

        logger.info(
            "Auto-approval decision: %s (%d rules, %d passed, %d failed)",
            "APPROVED" if all_passed else "MANUAL_REQUIRED",
            len(rules),
            len(rules) - len(failing_rules),
            len(failing_rules),
        )

        return decision

    # ------------------------------------------------------------------
    # Individual rule checks
    # ------------------------------------------------------------------

    def _check_risk_score(
        self,
        advisory_data: dict[str, Any],
    ) -> ApprovalRule:
        """Rule 1: Maximum risk score across all models."""
        max_risk = 0.0
        for _model_name, advisory in advisory_data.items():
            risk_data = advisory.get("risk_score", {})
            score = risk_data.get("risk_score", 0.0) if isinstance(risk_data, dict) else 0.0
            max_risk = max(max_risk, score)

        passed = max_risk < self._config.max_risk_score
        return ApprovalRule(
            rule_name="risk_score",
            passed=passed,
            reason=(
                f"Max risk score {max_risk:.1f} < threshold {self._config.max_risk_score}"
                if passed
                else f"Max risk score {max_risk:.1f} >= threshold {self._config.max_risk_score}"
            ),
        )

    def _check_cost(self, summary: dict[str, Any]) -> ApprovalRule:
        """Rule 2: Estimated cost within threshold."""
        cost = summary.get("estimated_cost_usd", 0.0)
        passed = cost < self._config.max_cost_usd
        return ApprovalRule(
            rule_name="cost_threshold",
            passed=passed,
            reason=(
                f"Estimated cost ${cost:.2f} < threshold ${self._config.max_cost_usd:.2f}"
                if passed
                else f"Estimated cost ${cost:.2f} >= threshold ${self._config.max_cost_usd:.2f}"
            ),
        )

    def _check_change_types(
        self,
        advisory_data: dict[str, Any],
        models_changed: list[str],
    ) -> ApprovalRule:
        """Rule 3: All change types must be in the allowed set."""
        disqualifying: list[str] = []
        allowed = set(self._config.allowed_change_types)

        for model_name in models_changed:
            advisory = advisory_data.get(model_name, {})
            classification = advisory.get("semantic_classification", {})
            change_type = (
                classification.get("change_type", "unknown") if isinstance(classification, dict) else "unknown"
            )
            if change_type not in allowed and change_type != "unknown":
                disqualifying.append(f"{model_name}={change_type}")

        passed = len(disqualifying) == 0
        return ApprovalRule(
            rule_name="change_type",
            passed=passed,
            reason=(
                "All change types are in the allowed set"
                if passed
                else f"Disqualifying change types: {', '.join(disqualifying)}"
            ),
        )

    def _check_sla_tags(
        self,
        models_changed: list[str],
        model_tags: dict[str, list[str]],
    ) -> ApprovalRule:
        """Rule 4: No SLA-tagged models in the change set."""
        sla_models: list[str] = []
        sla_set = set(t.lower() for t in self._config.sla_tags)

        for model_name in models_changed:
            tags = model_tags.get(model_name, [])
            if any(t.lower() in sla_set for t in tags):
                sla_models.append(model_name)

        passed = len(sla_models) == 0
        return ApprovalRule(
            rule_name="sla_models",
            passed=passed,
            reason=(
                "No SLA-tagged models affected" if passed else f"SLA-tagged models affected: {', '.join(sla_models)}"
            ),
        )

    def _check_dashboard_deps(
        self,
        models_changed: list[str],
        model_tags: dict[str, list[str]],
    ) -> ApprovalRule:
        """Rule 5: No dashboard-dependency models in the change set."""
        dashboard_models: list[str] = []
        dashboard_set = set(t.lower() for t in self._config.dashboard_tags)

        for model_name in models_changed:
            tags = model_tags.get(model_name, [])
            if any(t.lower() in dashboard_set for t in tags):
                dashboard_models.append(model_name)

        passed = len(dashboard_models) == 0
        return ApprovalRule(
            rule_name="dashboard_dependencies",
            passed=passed,
            reason=(
                "No dashboard-dependent models affected"
                if passed
                else f"Dashboard models affected: {', '.join(dashboard_models)}"
            ),
        )

    def _check_force_manual(self, models_changed: list[str]) -> ApprovalRule:
        """Rule 6: No models with force-manual-review flag."""
        blocked: list[str] = [m for m in models_changed if m in self._config.force_manual_models]
        passed = len(blocked) == 0
        return ApprovalRule(
            rule_name="force_manual_review",
            passed=passed,
            reason=(
                "No force-manual-review models affected"
                if passed
                else f"Force-manual models affected: {', '.join(blocked)}"
            ),
        )

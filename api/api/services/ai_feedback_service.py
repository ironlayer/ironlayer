"""AI feedback loop service -- records predictions vs actual outcomes.

Captures AI advisory predictions (cost, risk, classification) before plan
execution, then compares against actual run results to compute accuracy
scores.  Operators can also record acceptance/rejection of AI suggestions.
The accumulated data feeds back into model retraining.
"""

from __future__ import annotations

import json
import logging
from typing import Any

from core_engine.state.repository import (
    AIFeedbackRepository,
    PlanRepository,
    RunRepository,
)
from core_engine.state.tables import AIFeedbackTable
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Accuracy scoring helpers
# ---------------------------------------------------------------------------


def _compute_cost_accuracy(predicted_cost: float, actual_cost: float) -> float:
    """Compute accuracy score for cost predictions.

    Uses symmetric MAPE-based approach:
        ``1 - |predicted - actual| / max(predicted, actual, 0.01)``

    Returns a value clamped to [0.0, 1.0].
    """
    if predicted_cost <= 0 and actual_cost <= 0:
        return 1.0
    denominator = max(predicted_cost, actual_cost, 0.01)
    error_ratio = abs(predicted_cost - actual_cost) / denominator
    return max(0.0, min(1.0, 1.0 - error_ratio))


def _compute_risk_accuracy(predicted_risk: float, actual_success: bool) -> float:
    """Compute accuracy score for risk predictions.

    Maps the predicted risk (0-10 scale) against the binary success outcome:
    - Low risk + success = high accuracy
    - High risk + failure = high accuracy
    """
    normalized_risk = max(0.0, min(10.0, predicted_risk)) / 10.0
    if actual_success:
        return 1.0 - normalized_risk
    else:
        return normalized_risk


# ---------------------------------------------------------------------------
# Service
# ---------------------------------------------------------------------------


class AIFeedbackService:
    """Captures AI predictions and compares against execution outcomes.

    Parameters
    ----------
    session:
        Active database session.
    tenant_id:
        Tenant scope for all operations.
    """

    def __init__(self, session: AsyncSession, *, tenant_id: str = "default") -> None:
        self._session = session
        self._tenant_id = tenant_id
        self._feedback_repo = AIFeedbackRepository(session, tenant_id=tenant_id)
        self._plan_repo = PlanRepository(session, tenant_id=tenant_id)
        self._run_repo = RunRepository(session, tenant_id=tenant_id)

    # ------------------------------------------------------------------
    # Prediction capture
    # ------------------------------------------------------------------

    async def capture_predictions_from_plan(self, plan_id: str) -> int:
        """Extract AI predictions from a plan's ``advisory_json`` and persist them.

        Returns the number of prediction records created.
        """
        plan_row = await self._plan_repo.get_plan(plan_id)
        if plan_row is None:
            raise ValueError(f"Plan {plan_id} not found")

        advisory = plan_row.advisory_json
        if not advisory:
            return 0

        # advisory_json is JSONB -- may be dict or JSON string.
        if isinstance(advisory, str):
            advisory = json.loads(advisory)

        plan_data = plan_row.plan_json
        if isinstance(plan_data, str):
            plan_data = json.loads(plan_data)

        steps = plan_data.get("steps", []) if plan_data else []
        step_map = {s["step_id"]: s for s in steps}

        recorded = 0

        step_advisories: dict[str, dict] = advisory.get("steps", {})
        for step_id, step_advisory in step_advisories.items():
            step = step_map.get(step_id, {})
            model_name = step.get("model", step_advisory.get("model", "unknown"))

            # Cost prediction
            cost_pred = step_advisory.get("cost")
            if cost_pred:
                await self._feedback_repo.record_prediction(
                    plan_id=plan_id,
                    step_id=step_id,
                    model_name=model_name,
                    feedback_type="cost",
                    prediction=cost_pred,
                )
                recorded += 1

            # Risk prediction
            risk_pred = step_advisory.get("risk")
            if risk_pred:
                await self._feedback_repo.record_prediction(
                    plan_id=plan_id,
                    step_id=step_id,
                    model_name=model_name,
                    feedback_type="risk",
                    prediction=risk_pred,
                )
                recorded += 1

            # Classification prediction
            classification = step_advisory.get("classification")
            if classification:
                await self._feedback_repo.record_prediction(
                    plan_id=plan_id,
                    step_id=step_id,
                    model_name=model_name,
                    feedback_type="classification",
                    prediction=classification,
                )
                recorded += 1

        logger.info(
            "Captured %d AI predictions for plan %s",
            recorded,
            plan_id[:12],
        )
        return recorded

    # ------------------------------------------------------------------
    # Outcome recording
    # ------------------------------------------------------------------

    async def record_execution_outcome(
        self,
        plan_id: str,
        step_id: str,
        model_name: str,
        run_dict: dict[str, Any],
    ) -> int:
        """Compare AI predictions against actual execution outcome.

        Called after each step completes in ExecutionService.
        Returns the number of feedback records updated.
        """
        updated = 0
        actual_status = run_dict.get("status", "")
        actual_cost = run_dict.get("cost_usd")
        started = run_dict.get("started_at")
        finished = run_dict.get("finished_at")
        actual_runtime = None
        if started and finished:
            actual_runtime = (finished - started).total_seconds()

        actual_success = actual_status == "SUCCESS"

        # --- Cost outcome ---
        cost_outcome: dict[str, Any] = {
            "actual_cost_usd": actual_cost,
            "actual_runtime_seconds": actual_runtime,
            "status": actual_status,
        }

        cost_accuracy = None
        if actual_cost is not None and actual_cost > 0:
            pred_stmt = (
                select(AIFeedbackTable)
                .where(
                    AIFeedbackTable.tenant_id == self._tenant_id,
                    AIFeedbackTable.plan_id == plan_id,
                    AIFeedbackTable.step_id == step_id,
                    AIFeedbackTable.model_name == model_name,
                    AIFeedbackTable.feedback_type == "cost",
                )
                .order_by(AIFeedbackTable.created_at.desc())
                .limit(1)
            )
            pred_result = await self._session.execute(pred_stmt)
            pred_row = pred_result.scalar_one_or_none()
            if pred_row and pred_row.prediction_json:
                predicted_cost = pred_row.prediction_json.get("estimated_cost_usd", 0)
                if predicted_cost and predicted_cost > 0:
                    cost_accuracy = _compute_cost_accuracy(predicted_cost, actual_cost)

        await self._feedback_repo.record_outcome(
            plan_id=plan_id,
            step_id=step_id,
            model_name=model_name,
            feedback_type="cost",
            outcome=cost_outcome,
            accuracy_score=cost_accuracy,
        )
        updated += 1

        # --- Risk outcome ---
        risk_stmt = (
            select(AIFeedbackTable)
            .where(
                AIFeedbackTable.tenant_id == self._tenant_id,
                AIFeedbackTable.plan_id == plan_id,
                AIFeedbackTable.step_id == step_id,
                AIFeedbackTable.model_name == model_name,
                AIFeedbackTable.feedback_type == "risk",
            )
            .order_by(AIFeedbackTable.created_at.desc())
            .limit(1)
        )
        risk_result = await self._session.execute(risk_stmt)
        risk_pred_row = risk_result.scalar_one_or_none()

        if risk_pred_row and risk_pred_row.prediction_json:
            predicted_risk = risk_pred_row.prediction_json.get("risk_score", 5.0)
            risk_accuracy = _compute_risk_accuracy(predicted_risk, actual_success)

            risk_outcome: dict[str, Any] = {
                "actual_success": actual_success,
                "status": actual_status,
                "error_message": run_dict.get("error_message"),
            }
            await self._feedback_repo.record_outcome(
                plan_id=plan_id,
                step_id=step_id,
                model_name=model_name,
                feedback_type="risk",
                outcome=risk_outcome,
                accuracy_score=risk_accuracy,
            )
            updated += 1

        return updated

    # ------------------------------------------------------------------
    # Operator feedback
    # ------------------------------------------------------------------

    async def record_suggestion_feedback(
        self,
        plan_id: str,
        feedbacks: list[dict[str, Any]],
    ) -> int:
        """Record operator acceptance/rejection of AI suggestions.

        Each entry in *feedbacks* should contain:
        - ``step_id``: str
        - ``model_name``: str
        - ``feedback_type``: str (``"cost"``, ``"risk"``, ``"classification"``)
        - ``accepted``: bool

        Returns count of records updated.
        """
        updated = 0
        for fb in feedbacks:
            success = await self._feedback_repo.mark_accepted(
                plan_id=plan_id,
                step_id=fb["step_id"],
                model_name=fb["model_name"],
                feedback_type=fb["feedback_type"],
                accepted=fb["accepted"],
            )
            if success:
                updated += 1
        return updated

    # ------------------------------------------------------------------
    # Stats & training
    # ------------------------------------------------------------------

    async def get_accuracy_stats(
        self,
        feedback_type: str | None = None,
        model_name: str | None = None,
    ) -> dict[str, Any]:
        """Return aggregate accuracy and acceptance statistics."""
        return await self._feedback_repo.get_accuracy_stats(
            feedback_type=feedback_type,
            model_name=model_name,
        )

    async def get_training_data(
        self,
        feedback_type: str,
        limit: int = 1000,
    ) -> list[dict[str, Any]]:
        """Return prediction/outcome pairs for model retraining."""
        return await self._feedback_repo.get_training_data(
            feedback_type=feedback_type,
            limit=limit,
        )

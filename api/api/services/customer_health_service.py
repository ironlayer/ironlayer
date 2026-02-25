"""Customer health scoring and churn signal detection.

Computes a 0-100 health score for each tenant based on four dimensions:
  - Login recency (0-25 points)
  - Plan activity (0-25 points)
  - AI adoption (0-25 points)
  - Feature breadth (0-25 points)

Health status classification:
  - ``active``:   score >= 60
  - ``at_risk``:  30 <= score < 60
  - ``churning``: score < 30

Trend direction is computed by comparing the current score to the
previous score: ``improving`` (>5 increase), ``declining`` (>5 decrease),
or ``stable``.
"""

from __future__ import annotations

import logging
import time
from datetime import UTC, datetime, timedelta
from typing import Any

from core_engine.state.repository import CustomerHealthRepository, TenantConfigRepository
from core_engine.state.tables import (
    CustomerHealthTable,
    UsageEventTable,
    UserTable,
)
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)


def _score_recency(dt: datetime | None, max_points: float = 25.0) -> float:
    """Score a timestamp by recency: full points if within 1 day, decaying
    linearly to zero at 30 days.
    """
    if dt is None:
        return 0.0
    age_days = (datetime.now(UTC) - dt).total_seconds() / 86400
    if age_days <= 1:
        return max_points
    if age_days >= 30:
        return 0.0
    return round(max_points * (1 - (age_days - 1) / 29), 2)


def _classify_status(score: float) -> str:
    """Map a numeric score to a health status label."""
    if score >= 60:
        return "active"
    if score >= 30:
        return "at_risk"
    return "churning"


def _compute_trend(current: float, previous: float | None) -> str:
    """Determine trend direction from score delta."""
    if previous is None:
        return "stable"
    delta = current - previous
    if delta > 5:
        return "improving"
    if delta < -5:
        return "declining"
    return "stable"


class CustomerHealthService:
    """Computes and manages customer health metrics across all tenants."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session
        self._health_repo = CustomerHealthRepository(session)

    async def compute_health_score(self, tenant_id: str) -> dict[str, Any]:
        """Compute and persist the health score for a single tenant.

        Returns the full health record as a dict.
        """
        now = datetime.now(UTC)
        thirty_days_ago = now - timedelta(days=30)

        # ----- Dimension 1: Login recency (0-25) -----
        last_login_r = await self._session.execute(
            select(func.max(UserTable.last_login_at)).where(
                UserTable.tenant_id == tenant_id,
                UserTable.is_active == True,  # noqa: E712
            )
        )
        last_login = last_login_r.scalar_one_or_none()
        login_score = _score_recency(last_login)

        # ----- Dimension 2: Plan activity (0-25) -----
        last_plan_r = await self._session.execute(
            select(func.max(UsageEventTable.created_at)).where(
                UsageEventTable.tenant_id == tenant_id,
                UsageEventTable.event_type == "plan_run",
            )
        )
        last_plan_run = last_plan_r.scalar_one_or_none()
        plan_score = _score_recency(last_plan_run)

        # ----- Dimension 3: AI adoption (0-25) -----
        last_ai_r = await self._session.execute(
            select(func.max(UsageEventTable.created_at)).where(
                UsageEventTable.tenant_id == tenant_id,
                UsageEventTable.event_type == "ai_call",
            )
        )
        last_ai_call = last_ai_r.scalar_one_or_none()
        ai_score = _score_recency(last_ai_call)

        # ----- Dimension 4: Feature breadth (0-25) -----
        # Count distinct event types used in the last 30 days.
        distinct_types_r = await self._session.execute(
            select(func.count(func.distinct(UsageEventTable.event_type))).where(
                UsageEventTable.tenant_id == tenant_id,
                UsageEventTable.created_at >= thirty_days_ago,
            )
        )
        distinct_types = distinct_types_r.scalar_one()
        # Max 6 event types: plan_run, plan_apply, ai_call, model_loaded, backfill_run, api_request
        feature_score = min(25.0, round((distinct_types / 6) * 25, 2))

        # ----- Aggregate -----
        total_score = round(login_score + plan_score + ai_score + feature_score, 1)
        total_score = max(0.0, min(100.0, total_score))
        status = _classify_status(total_score)

        # Look up previous score for trend.
        existing = await self._health_repo.get(tenant_id)
        previous_score = existing.health_score if existing else None
        trend = _compute_trend(total_score, previous_score)

        engagement_metrics = {
            "login_recency": login_score,
            "plan_activity": plan_score,
            "ai_adoption": ai_score,
            "feature_breadth": feature_score,
        }

        # Detect status changes for eventing.
        old_status = existing.health_status if existing else None

        await self._health_repo.upsert(
            tenant_id,
            health_score=total_score,
            health_status=status,
            engagement_metrics=engagement_metrics,
            trend_direction=trend,
            previous_score=previous_score,
            last_login_at=last_login,
            last_plan_run_at=last_plan_run,
            last_ai_call_at=last_ai_call,
        )

        if old_status and old_status != status:
            self._fire_status_change_event(tenant_id, old_status, status, total_score)

        return {
            "tenant_id": tenant_id,
            "health_score": total_score,
            "health_status": status,
            "trend_direction": trend,
            "previous_score": previous_score,
            "engagement_metrics": engagement_metrics,
            "last_login_at": last_login.isoformat() if last_login else None,
            "last_plan_run_at": last_plan_run.isoformat() if last_plan_run else None,
            "last_ai_call_at": last_ai_call.isoformat() if last_ai_call else None,
        }

    async def compute_all(self) -> dict[str, Any]:
        """Recompute health scores for all active tenants.

        Returns ``{"computed_count": int, "duration_ms": int}``.
        """
        start = time.monotonic()

        config_repo = TenantConfigRepository(self._session, "system")
        configs = await config_repo.list_all(include_deactivated=False)

        count = 0
        for config in configs:
            try:
                await self.compute_health_score(config.tenant_id)
                count += 1
            except Exception:
                logger.exception("Failed to compute health for tenant=%s", config.tenant_id)

        duration_ms = int((time.monotonic() - start) * 1000)
        logger.info("Computed health scores for %d tenants in %dms", count, duration_ms)
        return {"computed_count": count, "duration_ms": duration_ms}

    async def get_health_detail(self, tenant_id: str) -> dict[str, Any] | None:
        """Return the full health record for a specific tenant."""
        record = await self._health_repo.get(tenant_id)
        if record is None:
            return None
        return {
            "tenant_id": record.tenant_id,
            "health_score": record.health_score,
            "health_status": record.health_status,
            "trend_direction": record.trend_direction,
            "previous_score": record.previous_score,
            "engagement_metrics": record.engagement_metrics_json,
            "last_login_at": record.last_login_at.isoformat() if record.last_login_at else None,
            "last_plan_run_at": record.last_plan_run_at.isoformat() if record.last_plan_run_at else None,
            "last_ai_call_at": record.last_ai_call_at.isoformat() if record.last_ai_call_at else None,
            "computed_at": record.computed_at.isoformat() if record.computed_at else None,
            "updated_at": record.updated_at.isoformat() if record.updated_at else None,
        }

    async def list_tenants(
        self,
        *,
        status_filter: str | None = None,
        sort_by: str = "health_score",
        limit: int = 50,
        offset: int = 0,
    ) -> dict[str, Any]:
        """List customer health records with filtering, sorting, and summary counts.

        Returns
        -------
        dict
            ``{"tenants": [...], "total": int, "summary": {"active": int, "at_risk": int, "churning": int}}``
        """
        rows, total = await self._health_repo.list_all(
            status_filter=status_filter,
            sort_by=sort_by,
            limit=limit,
            offset=offset,
        )

        tenants = []
        for r in rows:
            tenants.append(
                {
                    "tenant_id": r.tenant_id,
                    "health_score": r.health_score,
                    "health_status": r.health_status,
                    "trend_direction": r.trend_direction,
                    "last_login_at": r.last_login_at.isoformat() if r.last_login_at else None,
                    "last_plan_run_at": r.last_plan_run_at.isoformat() if r.last_plan_run_at else None,
                    "computed_at": r.computed_at.isoformat() if r.computed_at else None,
                }
            )

        # Summary counts across ALL records via a single GROUP BY query.
        summary_r = await self._session.execute(
            select(
                CustomerHealthTable.health_status,
                func.count().label("cnt"),
            ).group_by(CustomerHealthTable.health_status)
        )
        summary = {"active": 0, "at_risk": 0, "churning": 0}
        for row in summary_r.all():
            if row.health_status in summary:
                summary[row.health_status] = int(row.cnt)

        return {"tenants": tenants, "total": total, "summary": summary}

    def _fire_status_change_event(
        self,
        tenant_id: str,
        old_status: str,
        new_status: str,
        score: float,
    ) -> None:
        """Log a health status transition for observability.

        In production this would dispatch via EventBus; for now we log at
        WARNING level so operators can set up alerts.
        """
        logger.warning(
            "Customer health status change: tenant=%s %s -> %s (score=%.1f)",
            tenant_id,
            old_status,
            new_status,
            score,
        )

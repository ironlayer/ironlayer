"""Admin analytics service for cross-tenant platform insights.

Provides platform-wide metrics for the admin dashboard: tenant counts,
MRR, cost breakdowns, health metrics, and per-tenant usage detail.
All methods are admin-only and cross-tenant.
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime, timedelta
from typing import Any

from core_engine.state.repository import AnalyticsRepository
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)


class AnalyticsService:
    """Cross-tenant analytics composition layer for admin dashboards."""

    def __init__(self, session: AsyncSession) -> None:
        self._repo = AnalyticsRepository(session)

    async def get_overview(self, days: int = 30) -> dict[str, Any]:
        """Return platform overview metrics for the last *days* days."""
        since = datetime.now(UTC) - timedelta(days=days)
        return await self._repo.get_platform_overview(since)

    async def get_tenant_breakdown(
        self,
        days: int = 30,
        limit: int = 50,
        offset: int = 0,
    ) -> dict[str, Any]:
        """Return per-tenant usage breakdown with pagination."""
        since = datetime.now(UTC) - timedelta(days=days)
        return await self._repo.get_per_tenant_breakdown(since, limit, offset)

    async def get_revenue(self) -> dict[str, Any]:
        """Return MRR and subscription counts by tier."""
        return await self._repo.get_revenue_metrics()

    async def get_cost_breakdown(
        self,
        days: int = 30,
        group_by: str = "model",
    ) -> dict[str, Any]:
        """Return cost breakdown grouped by model or time bucket."""
        since = datetime.now(UTC) - timedelta(days=days)
        return await self._repo.get_cost_breakdown(since, group_by)

    async def get_health(self, days: int = 30) -> dict[str, Any]:
        """Return platform health metrics: error rate, P95, AI stats."""
        since = datetime.now(UTC) - timedelta(days=days)
        return await self._repo.get_health_metrics(since)

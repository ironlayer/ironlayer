"""Tests for api/api/routers/admin_analytics.py

Covers:
- GET /admin/analytics/overview: platform overview metrics
- GET /admin/analytics/tenants: per-tenant breakdown with pagination
- GET /admin/analytics/revenue: MRR and subscription counts
- GET /admin/analytics/cost-breakdown: cost grouped by model or time bucket
- GET /admin/analytics/health: error rates, P95 runtime, AI accuracy
- RBAC: all endpoints require VIEW_ANALYTICS (admin-only)
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import time
from typing import Any
from unittest.mock import AsyncMock, patch

import pytest
from httpx import AsyncClient

_DEV_SECRET = "test-secret-key-for-ironlayer-tests"


def _make_dev_token(
    tenant_id: str = "default",
    sub: str = "test-user",
    role: str = "admin",
    scopes: list[str] | None = None,
) -> str:
    now = time.time()
    payload: dict[str, Any] = {
        "sub": sub,
        "tenant_id": tenant_id,
        "iss": "ironlayer",
        "iat": now,
        "exp": now + 3600,
        "scopes": scopes or ["read", "write"],
        "jti": "test-jti-conftest",
        "identity_kind": "user",
        "role": role,
    }
    payload_json = json.dumps(payload)
    signature = hmac.new(
        _DEV_SECRET.encode("utf-8"),
        payload_json.encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()
    token_bytes = base64.urlsafe_b64encode(payload_json.encode("utf-8")).decode("ascii")
    return f"bmdev.{token_bytes}.{signature}"


_VIEWER_TOKEN = _make_dev_token(role="viewer")
_VIEWER_HEADERS = {"Authorization": f"Bearer {_VIEWER_TOKEN}"}

_BASE = "/api/v1/admin/analytics"


# ---------------------------------------------------------------------------
# Sample response data
# ---------------------------------------------------------------------------

_OVERVIEW_DATA: dict[str, Any] = {
    "total_tenants": 12,
    "active_tenants": 8,
    "total_usage_events": 4500,
    "total_runs": 320,
    "total_cost_usd": 1285.50,
    "period_days": 30,
}

_TENANTS_DATA: dict[str, Any] = {
    "tenants": [
        {
            "tenant_id": "acme-corp",
            "plan_tier": "team",
            "usage_events": 1200,
            "run_count": 80,
            "run_cost_usd": 340.0,
            "llm_cost_usd": 45.0,
        },
        {
            "tenant_id": "widgets-inc",
            "plan_tier": "enterprise",
            "usage_events": 3000,
            "run_count": 200,
            "run_cost_usd": 800.0,
            "llm_cost_usd": 120.0,
        },
    ],
    "total": 2,
    "limit": 50,
    "offset": 0,
}

_REVENUE_DATA: dict[str, Any] = {
    "mrr_usd": 5430.0,
    "tiers": {
        "community": {"count": 5, "mrr_usd": 0.0},
        "team": {"count": 45, "mrr_usd": 2205.0},
        "enterprise": {"count": 12, "mrr_usd": 2388.0},
    },
}

_COST_BREAKDOWN_DATA: dict[str, Any] = {
    "groups": [
        {"group": "staging.orders", "total_cost_usd": 450.0, "run_count": 30},
        {"group": "marts.revenue", "total_cost_usd": 680.0, "run_count": 55},
    ],
    "period_days": 30,
    "group_by": "model",
}

_HEALTH_DATA: dict[str, Any] = {
    "run_error_rate": 0.032,
    "p95_runtime_seconds": 145.6,
    "ai_acceptance_rate": 0.78,
    "ai_prediction_accuracy": 0.91,
    "period_days": 30,
}


# ---------------------------------------------------------------------------
# GET /admin/analytics/overview
# ---------------------------------------------------------------------------


class TestOverviewEndpoint:
    """Verify GET /api/v1/admin/analytics/overview responses."""

    @pytest.mark.asyncio
    async def test_returns_overview_data(self, client: AsyncClient) -> None:
        """Admin token returns 200 with platform overview metrics."""
        with patch("api.routers.admin_analytics.AnalyticsService") as MockService:
            instance = MockService.return_value
            instance.get_overview = AsyncMock(return_value=_OVERVIEW_DATA)

            resp = await client.get(f"{_BASE}/overview")

        assert resp.status_code == 200
        body = resp.json()
        assert body["total_tenants"] == 12
        assert body["active_tenants"] == 8
        assert body["total_usage_events"] == 4500
        assert body["total_runs"] == 320
        assert body["total_cost_usd"] == 1285.50
        assert body["period_days"] == 30

    @pytest.mark.asyncio
    async def test_custom_days_parameter(self, client: AsyncClient) -> None:
        """Passing days=7 forwards the value to the service layer."""
        with patch("api.routers.admin_analytics.AnalyticsService") as MockService:
            instance = MockService.return_value
            instance.get_overview = AsyncMock(return_value={**_OVERVIEW_DATA, "period_days": 7})

            resp = await client.get(f"{_BASE}/overview", params={"days": 7})

        assert resp.status_code == 200
        instance.get_overview.assert_awaited_once_with(7)

    @pytest.mark.asyncio
    async def test_non_admin_forbidden(self, client: AsyncClient) -> None:
        """Viewer role cannot access overview endpoint."""
        resp = await client.get(f"{_BASE}/overview", headers=_VIEWER_HEADERS)

        assert resp.status_code == 403


# ---------------------------------------------------------------------------
# GET /admin/analytics/tenants
# ---------------------------------------------------------------------------


class TestTenantsEndpoint:
    """Verify GET /api/v1/admin/analytics/tenants responses."""

    @pytest.mark.asyncio
    async def test_returns_tenant_breakdown(self, client: AsyncClient) -> None:
        """Admin token returns 200 with per-tenant breakdown."""
        with patch("api.routers.admin_analytics.AnalyticsService") as MockService:
            instance = MockService.return_value
            instance.get_tenant_breakdown = AsyncMock(return_value=_TENANTS_DATA)

            resp = await client.get(f"{_BASE}/tenants")

        assert resp.status_code == 200
        body = resp.json()
        assert body["total"] == 2
        assert len(body["tenants"]) == 2
        assert body["tenants"][0]["tenant_id"] == "acme-corp"
        assert body["tenants"][1]["plan_tier"] == "enterprise"

    @pytest.mark.asyncio
    async def test_pagination_params(self, client: AsyncClient) -> None:
        """Custom limit and offset are forwarded to the service."""
        paginated = {**_TENANTS_DATA, "limit": 10, "offset": 5}
        with patch("api.routers.admin_analytics.AnalyticsService") as MockService:
            instance = MockService.return_value
            instance.get_tenant_breakdown = AsyncMock(return_value=paginated)

            resp = await client.get(f"{_BASE}/tenants", params={"limit": 10, "offset": 5})

        assert resp.status_code == 200
        instance.get_tenant_breakdown.assert_awaited_once_with(30, 10, 5)

    @pytest.mark.asyncio
    async def test_non_admin_forbidden(self, client: AsyncClient) -> None:
        """Viewer role cannot access tenants endpoint."""
        resp = await client.get(f"{_BASE}/tenants", headers=_VIEWER_HEADERS)

        assert resp.status_code == 403


# ---------------------------------------------------------------------------
# GET /admin/analytics/revenue
# ---------------------------------------------------------------------------


class TestRevenueEndpoint:
    """Verify GET /api/v1/admin/analytics/revenue responses."""

    @pytest.mark.asyncio
    async def test_returns_revenue(self, client: AsyncClient) -> None:
        """Admin token returns 200 with MRR and tier breakdown."""
        with patch("api.routers.admin_analytics.AnalyticsService") as MockService:
            instance = MockService.return_value
            instance.get_revenue = AsyncMock(return_value=_REVENUE_DATA)

            resp = await client.get(f"{_BASE}/revenue")

        assert resp.status_code == 200
        body = resp.json()
        assert body["mrr_usd"] == 5430.0
        assert body["tiers"]["team"]["count"] == 45
        assert body["tiers"]["enterprise"]["mrr_usd"] == 2388.0

    @pytest.mark.asyncio
    async def test_non_admin_forbidden(self, client: AsyncClient) -> None:
        """Viewer role cannot access revenue endpoint."""
        resp = await client.get(f"{_BASE}/revenue", headers=_VIEWER_HEADERS)

        assert resp.status_code == 403


# ---------------------------------------------------------------------------
# GET /admin/analytics/cost-breakdown
# ---------------------------------------------------------------------------


class TestCostBreakdownEndpoint:
    """Verify GET /api/v1/admin/analytics/cost-breakdown responses."""

    @pytest.mark.asyncio
    async def test_returns_cost_breakdown(self, client: AsyncClient) -> None:
        """Admin token returns 200 with cost groups."""
        with patch("api.routers.admin_analytics.AnalyticsService") as MockService:
            instance = MockService.return_value
            instance.get_cost_breakdown = AsyncMock(return_value=_COST_BREAKDOWN_DATA)

            resp = await client.get(f"{_BASE}/cost-breakdown")

        assert resp.status_code == 200
        body = resp.json()
        assert len(body["groups"]) == 2
        assert body["group_by"] == "model"
        assert body["groups"][0]["group"] == "staging.orders"
        assert body["groups"][1]["total_cost_usd"] == 680.0

    @pytest.mark.asyncio
    async def test_custom_group_by(self, client: AsyncClient) -> None:
        """Passing group_by=day forwards the value to the service."""
        day_data = {**_COST_BREAKDOWN_DATA, "group_by": "day"}
        with patch("api.routers.admin_analytics.AnalyticsService") as MockService:
            instance = MockService.return_value
            instance.get_cost_breakdown = AsyncMock(return_value=day_data)

            resp = await client.get(f"{_BASE}/cost-breakdown", params={"group_by": "day"})

        assert resp.status_code == 200
        instance.get_cost_breakdown.assert_awaited_once_with(30, "day")

    @pytest.mark.asyncio
    async def test_non_admin_forbidden(self, client: AsyncClient) -> None:
        """Viewer role cannot access cost-breakdown endpoint."""
        resp = await client.get(f"{_BASE}/cost-breakdown", headers=_VIEWER_HEADERS)

        assert resp.status_code == 403


# ---------------------------------------------------------------------------
# GET /admin/analytics/health
# ---------------------------------------------------------------------------


class TestHealthEndpoint:
    """Verify GET /api/v1/admin/analytics/health responses."""

    @pytest.mark.asyncio
    async def test_returns_health_metrics(self, client: AsyncClient) -> None:
        """Admin token returns 200 with health metrics."""
        with patch("api.routers.admin_analytics.AnalyticsService") as MockService:
            instance = MockService.return_value
            instance.get_health = AsyncMock(return_value=_HEALTH_DATA)

            resp = await client.get(f"{_BASE}/health")

        assert resp.status_code == 200
        body = resp.json()
        assert body["run_error_rate"] == 0.032
        assert body["p95_runtime_seconds"] == 145.6
        assert body["ai_acceptance_rate"] == 0.78
        assert body["ai_prediction_accuracy"] == 0.91

    @pytest.mark.asyncio
    async def test_non_admin_forbidden(self, client: AsyncClient) -> None:
        """Viewer role cannot access health endpoint."""
        resp = await client.get(f"{_BASE}/health", headers=_VIEWER_HEADERS)

        assert resp.status_code == 403

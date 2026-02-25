"""Tests for api/api/services/analytics_service.py

Covers:
- AnalyticsService: get_overview delegates to AnalyticsRepository with correct since datetime
- AnalyticsService: get_tenant_breakdown passes days, limit, offset correctly
- AnalyticsService: get_revenue delegates directly
- AnalyticsService: get_cost_breakdown passes days and group_by
- AnalyticsService: get_health passes days
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from api.services.analytics_service import AnalyticsService

# ---------------------------------------------------------------------------
# Shared fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def mock_session() -> AsyncMock:
    """Mock async database session."""
    session = AsyncMock()
    session.add = MagicMock()
    session.flush = AsyncMock()
    session.commit = AsyncMock()

    result_mock = MagicMock()
    result_mock.scalar_one_or_none.return_value = None
    result_mock.scalars.return_value.all.return_value = []
    session.execute = AsyncMock(return_value=result_mock)

    return session


# ---------------------------------------------------------------------------
# get_overview
# ---------------------------------------------------------------------------


class TestGetOverview:
    """Verify get_overview computes the 'since' datetime and delegates to the repository."""

    @pytest.mark.asyncio
    async def test_calls_repo_with_correct_since_datetime(self, mock_session: AsyncMock) -> None:
        """get_overview(days=30) passes a 'since' datetime ~30 days in the past."""
        expected_result = {
            "total_tenants": 42,
            "active_tenants_30d": 35,
            "total_plans": 1200,
            "total_runs": 8500,
            "total_ai_calls": 6000,
        }

        with patch("api.services.analytics_service.AnalyticsRepository") as MockRepo:
            mock_repo_instance = AsyncMock()
            mock_repo_instance.get_platform_overview = AsyncMock(return_value=expected_result)
            MockRepo.return_value = mock_repo_instance

            service = AnalyticsService(mock_session)
            before = datetime.now(UTC)
            result = await service.get_overview(days=30)
            after = datetime.now(UTC)

        assert result == expected_result
        mock_repo_instance.get_platform_overview.assert_called_once()

        call_args = mock_repo_instance.get_platform_overview.call_args
        since_arg = call_args[0][0]
        expected_since_lower = before - timedelta(days=30)
        expected_since_upper = after - timedelta(days=30)
        assert expected_since_lower <= since_arg <= expected_since_upper

    @pytest.mark.asyncio
    async def test_default_days_is_30(self, mock_session: AsyncMock) -> None:
        """get_overview() without arguments defaults to 30 days."""
        with patch("api.services.analytics_service.AnalyticsRepository") as MockRepo:
            mock_repo_instance = AsyncMock()
            mock_repo_instance.get_platform_overview = AsyncMock(return_value={})
            MockRepo.return_value = mock_repo_instance

            service = AnalyticsService(mock_session)
            before = datetime.now(UTC)
            await service.get_overview()
            after = datetime.now(UTC)

        call_args = mock_repo_instance.get_platform_overview.call_args
        since_arg = call_args[0][0]
        expected_since_lower = before - timedelta(days=30)
        expected_since_upper = after - timedelta(days=30)
        assert expected_since_lower <= since_arg <= expected_since_upper

    @pytest.mark.asyncio
    async def test_custom_days_value(self, mock_session: AsyncMock) -> None:
        """get_overview(days=7) computes since as 7 days ago."""
        with patch("api.services.analytics_service.AnalyticsRepository") as MockRepo:
            mock_repo_instance = AsyncMock()
            mock_repo_instance.get_platform_overview = AsyncMock(return_value={})
            MockRepo.return_value = mock_repo_instance

            service = AnalyticsService(mock_session)
            before = datetime.now(UTC)
            await service.get_overview(days=7)
            after = datetime.now(UTC)

        call_args = mock_repo_instance.get_platform_overview.call_args
        since_arg = call_args[0][0]
        expected_since_lower = before - timedelta(days=7)
        expected_since_upper = after - timedelta(days=7)
        assert expected_since_lower <= since_arg <= expected_since_upper

    @pytest.mark.asyncio
    async def test_returns_repo_result_unchanged(self, mock_session: AsyncMock) -> None:
        """The return value is passed through from the repository without modification."""
        payload = {"total_tenants": 1, "arbitrary_key": "preserved"}

        with patch("api.services.analytics_service.AnalyticsRepository") as MockRepo:
            mock_repo_instance = AsyncMock()
            mock_repo_instance.get_platform_overview = AsyncMock(return_value=payload)
            MockRepo.return_value = mock_repo_instance

            service = AnalyticsService(mock_session)
            result = await service.get_overview()

        assert result is payload


# ---------------------------------------------------------------------------
# get_tenant_breakdown
# ---------------------------------------------------------------------------


class TestGetTenantBreakdown:
    """Verify get_tenant_breakdown passes days, limit, and offset to the repository."""

    @pytest.mark.asyncio
    async def test_passes_all_parameters(self, mock_session: AsyncMock) -> None:
        """Days, limit, and offset are forwarded to get_per_tenant_breakdown."""
        expected_result = {
            "tenants": [{"tenant_id": "t1", "plan_count": 10}],
            "total": 1,
        }

        with patch("api.services.analytics_service.AnalyticsRepository") as MockRepo:
            mock_repo_instance = AsyncMock()
            mock_repo_instance.get_per_tenant_breakdown = AsyncMock(return_value=expected_result)
            MockRepo.return_value = mock_repo_instance

            service = AnalyticsService(mock_session)
            before = datetime.now(UTC)
            result = await service.get_tenant_breakdown(days=14, limit=25, offset=50)
            after = datetime.now(UTC)

        assert result == expected_result
        mock_repo_instance.get_per_tenant_breakdown.assert_called_once()

        call_args = mock_repo_instance.get_per_tenant_breakdown.call_args
        since_arg = call_args[0][0]
        limit_arg = call_args[0][1]
        offset_arg = call_args[0][2]

        expected_since_lower = before - timedelta(days=14)
        expected_since_upper = after - timedelta(days=14)
        assert expected_since_lower <= since_arg <= expected_since_upper
        assert limit_arg == 25
        assert offset_arg == 50

    @pytest.mark.asyncio
    async def test_default_parameters(self, mock_session: AsyncMock) -> None:
        """Default values are days=30, limit=50, offset=0."""
        with patch("api.services.analytics_service.AnalyticsRepository") as MockRepo:
            mock_repo_instance = AsyncMock()
            mock_repo_instance.get_per_tenant_breakdown = AsyncMock(return_value={})
            MockRepo.return_value = mock_repo_instance

            service = AnalyticsService(mock_session)
            before = datetime.now(UTC)
            await service.get_tenant_breakdown()
            after = datetime.now(UTC)

        call_args = mock_repo_instance.get_per_tenant_breakdown.call_args
        since_arg = call_args[0][0]
        limit_arg = call_args[0][1]
        offset_arg = call_args[0][2]

        expected_since_lower = before - timedelta(days=30)
        expected_since_upper = after - timedelta(days=30)
        assert expected_since_lower <= since_arg <= expected_since_upper
        assert limit_arg == 50
        assert offset_arg == 0


# ---------------------------------------------------------------------------
# get_revenue
# ---------------------------------------------------------------------------


class TestGetRevenue:
    """Verify get_revenue delegates directly to AnalyticsRepository."""

    @pytest.mark.asyncio
    async def test_delegates_to_repo(self, mock_session: AsyncMock) -> None:
        """get_revenue calls get_revenue_metrics and returns its result."""
        expected_result = {
            "mrr_usd": 5000.0,
            "subscriptions": {"community": 30, "team": 15, "enterprise": 5},
        }

        with patch("api.services.analytics_service.AnalyticsRepository") as MockRepo:
            mock_repo_instance = AsyncMock()
            mock_repo_instance.get_revenue_metrics = AsyncMock(return_value=expected_result)
            MockRepo.return_value = mock_repo_instance

            service = AnalyticsService(mock_session)
            result = await service.get_revenue()

        assert result == expected_result
        mock_repo_instance.get_revenue_metrics.assert_called_once_with()

    @pytest.mark.asyncio
    async def test_returns_repo_result_unchanged(self, mock_session: AsyncMock) -> None:
        """The return value is passed through without modification."""
        payload = {"mrr_usd": 0, "extra_field": True}

        with patch("api.services.analytics_service.AnalyticsRepository") as MockRepo:
            mock_repo_instance = AsyncMock()
            mock_repo_instance.get_revenue_metrics = AsyncMock(return_value=payload)
            MockRepo.return_value = mock_repo_instance

            service = AnalyticsService(mock_session)
            result = await service.get_revenue()

        assert result is payload


# ---------------------------------------------------------------------------
# get_cost_breakdown
# ---------------------------------------------------------------------------


class TestGetCostBreakdown:
    """Verify get_cost_breakdown passes days and group_by to the repository."""

    @pytest.mark.asyncio
    async def test_passes_days_and_group_by(self, mock_session: AsyncMock) -> None:
        """Days and group_by are forwarded to get_cost_breakdown on the repo."""
        expected_result = {
            "items": [{"model": "gpt-4", "cost_usd": 42.0}],
            "group_by": "model",
        }

        with patch("api.services.analytics_service.AnalyticsRepository") as MockRepo:
            mock_repo_instance = AsyncMock()
            mock_repo_instance.get_cost_breakdown = AsyncMock(return_value=expected_result)
            MockRepo.return_value = mock_repo_instance

            service = AnalyticsService(mock_session)
            before = datetime.now(UTC)
            result = await service.get_cost_breakdown(days=7, group_by="time")
            after = datetime.now(UTC)

        assert result == expected_result
        mock_repo_instance.get_cost_breakdown.assert_called_once()

        call_args = mock_repo_instance.get_cost_breakdown.call_args
        since_arg = call_args[0][0]
        group_by_arg = call_args[0][1]

        expected_since_lower = before - timedelta(days=7)
        expected_since_upper = after - timedelta(days=7)
        assert expected_since_lower <= since_arg <= expected_since_upper
        assert group_by_arg == "time"

    @pytest.mark.asyncio
    async def test_default_group_by_is_model(self, mock_session: AsyncMock) -> None:
        """Default group_by is 'model'."""
        with patch("api.services.analytics_service.AnalyticsRepository") as MockRepo:
            mock_repo_instance = AsyncMock()
            mock_repo_instance.get_cost_breakdown = AsyncMock(return_value={})
            MockRepo.return_value = mock_repo_instance

            service = AnalyticsService(mock_session)
            await service.get_cost_breakdown()

        call_args = mock_repo_instance.get_cost_breakdown.call_args
        group_by_arg = call_args[0][1]
        assert group_by_arg == "model"

    @pytest.mark.asyncio
    async def test_default_days_is_30(self, mock_session: AsyncMock) -> None:
        """Default days is 30."""
        with patch("api.services.analytics_service.AnalyticsRepository") as MockRepo:
            mock_repo_instance = AsyncMock()
            mock_repo_instance.get_cost_breakdown = AsyncMock(return_value={})
            MockRepo.return_value = mock_repo_instance

            service = AnalyticsService(mock_session)
            before = datetime.now(UTC)
            await service.get_cost_breakdown()
            after = datetime.now(UTC)

        call_args = mock_repo_instance.get_cost_breakdown.call_args
        since_arg = call_args[0][0]
        expected_since_lower = before - timedelta(days=30)
        expected_since_upper = after - timedelta(days=30)
        assert expected_since_lower <= since_arg <= expected_since_upper


# ---------------------------------------------------------------------------
# get_health
# ---------------------------------------------------------------------------


class TestGetHealth:
    """Verify get_health passes days to the repository health metrics query."""

    @pytest.mark.asyncio
    async def test_passes_days_correctly(self, mock_session: AsyncMock) -> None:
        """get_health(days=7) passes a 'since' datetime 7 days in the past."""
        expected_result = {
            "error_rate": 0.02,
            "p95_latency_ms": 450,
            "ai_success_rate": 0.98,
        }

        with patch("api.services.analytics_service.AnalyticsRepository") as MockRepo:
            mock_repo_instance = AsyncMock()
            mock_repo_instance.get_health_metrics = AsyncMock(return_value=expected_result)
            MockRepo.return_value = mock_repo_instance

            service = AnalyticsService(mock_session)
            before = datetime.now(UTC)
            result = await service.get_health(days=7)
            after = datetime.now(UTC)

        assert result == expected_result
        mock_repo_instance.get_health_metrics.assert_called_once()

        call_args = mock_repo_instance.get_health_metrics.call_args
        since_arg = call_args[0][0]
        expected_since_lower = before - timedelta(days=7)
        expected_since_upper = after - timedelta(days=7)
        assert expected_since_lower <= since_arg <= expected_since_upper

    @pytest.mark.asyncio
    async def test_default_days_is_30(self, mock_session: AsyncMock) -> None:
        """get_health() without arguments defaults to 30 days."""
        with patch("api.services.analytics_service.AnalyticsRepository") as MockRepo:
            mock_repo_instance = AsyncMock()
            mock_repo_instance.get_health_metrics = AsyncMock(return_value={})
            MockRepo.return_value = mock_repo_instance

            service = AnalyticsService(mock_session)
            before = datetime.now(UTC)
            await service.get_health()
            after = datetime.now(UTC)

        call_args = mock_repo_instance.get_health_metrics.call_args
        since_arg = call_args[0][0]
        expected_since_lower = before - timedelta(days=30)
        expected_since_upper = after - timedelta(days=30)
        assert expected_since_lower <= since_arg <= expected_since_upper

    @pytest.mark.asyncio
    async def test_returns_repo_result_unchanged(self, mock_session: AsyncMock) -> None:
        """The return value is passed through from the repository without modification."""
        payload = {"error_rate": 0.0, "custom_field": "kept"}

        with patch("api.services.analytics_service.AnalyticsRepository") as MockRepo:
            mock_repo_instance = AsyncMock()
            mock_repo_instance.get_health_metrics = AsyncMock(return_value=payload)
            MockRepo.return_value = mock_repo_instance

            service = AnalyticsService(mock_session)
            result = await service.get_health()

        assert result is payload

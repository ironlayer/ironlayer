"""Tests for api/api/services/quota_service.py

Covers:
- QuotaService: plan quota enforcement (community, team, enterprise tiers)
- QuotaService: AI call quota enforcement
- QuotaService: API request quota enforcement
- QuotaService: LLM daily and monthly budget checks
- QuotaService: usage-vs-limits dashboard data assembly
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from api.services.quota_service import QuotaService

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


def _make_service(session: AsyncMock, tenant_id: str = "test-tenant") -> QuotaService:
    """Create a QuotaService with the given session and tenant."""
    return QuotaService(session, tenant_id)


# ---------------------------------------------------------------------------
# Plan Quota
# ---------------------------------------------------------------------------


class TestCheckPlanQuota:
    """Verify check_plan_quota enforces monthly plan-run limits correctly."""

    @pytest.mark.asyncio
    async def test_under_limit_returns_allowed(self, mock_session: AsyncMock) -> None:
        """When plan runs are under the limit, return (True, None)."""
        service = _make_service(mock_session)

        service._quota_repo = AsyncMock()
        service._quota_repo.get_monthly_event_count = AsyncMock(return_value=50)
        service._config_repo = AsyncMock()
        service._config_repo.get = AsyncMock(return_value=None)

        with patch.object(service, "_get_plan_tier", return_value="community"):
            allowed, reason = await service.check_plan_quota()

        assert allowed is True
        assert reason is None
        service._quota_repo.get_monthly_event_count.assert_called_once_with("plan_run")

    @pytest.mark.asyncio
    async def test_at_limit_returns_denied(self, mock_session: AsyncMock) -> None:
        """When plan runs equal the limit, return (False, message)."""
        service = _make_service(mock_session)

        service._quota_repo = AsyncMock()
        service._quota_repo.get_monthly_event_count = AsyncMock(return_value=100)
        service._config_repo = AsyncMock()
        service._config_repo.get = AsyncMock(return_value=None)

        with patch.object(service, "_get_plan_tier", return_value="community"):
            allowed, reason = await service.check_plan_quota()

        assert allowed is False
        assert reason is not None
        assert "100/100" in reason
        assert "plan run quota exceeded" in reason.lower()

    @pytest.mark.asyncio
    async def test_over_limit_returns_denied(self, mock_session: AsyncMock) -> None:
        """When plan runs exceed the limit, return (False, message)."""
        service = _make_service(mock_session)

        service._quota_repo = AsyncMock()
        service._quota_repo.get_monthly_event_count = AsyncMock(return_value=150)
        service._config_repo = AsyncMock()
        service._config_repo.get = AsyncMock(return_value=None)

        with patch.object(service, "_get_plan_tier", return_value="community"):
            allowed, reason = await service.check_plan_quota()

        assert allowed is False
        assert reason is not None
        assert "150/100" in reason

    @pytest.mark.asyncio
    async def test_enterprise_unlimited_always_allowed(self, mock_session: AsyncMock) -> None:
        """Enterprise tier has unlimited plan runs (limit=None), always allowed."""
        service = _make_service(mock_session)

        service._quota_repo = AsyncMock()
        service._quota_repo.get_monthly_event_count = AsyncMock(return_value=999_999)
        service._config_repo = AsyncMock()
        service._config_repo.get = AsyncMock(return_value=None)

        with patch.object(service, "_get_plan_tier", return_value="enterprise"):
            allowed, reason = await service.check_plan_quota()

        assert allowed is True
        assert reason is None
        # Should not even check the count when unlimited.
        service._quota_repo.get_monthly_event_count.assert_not_called()

    @pytest.mark.asyncio
    async def test_explicit_config_overrides_tier_default(self, mock_session: AsyncMock) -> None:
        """An explicit plan_quota_monthly in tenant config overrides the tier default."""
        service = _make_service(mock_session)

        service._quota_repo = AsyncMock()
        service._quota_repo.get_monthly_event_count = AsyncMock(return_value=200)
        config_row = MagicMock()
        config_row.plan_quota_monthly = 500
        config_row.ai_quota_monthly = None
        config_row.api_quota_monthly = None
        service._config_repo = AsyncMock()
        service._config_repo.get = AsyncMock(return_value=config_row)

        with patch.object(service, "_get_plan_tier", return_value="community"):
            allowed, reason = await service.check_plan_quota()

        # 200 < 500, so allowed.
        assert allowed is True
        assert reason is None

    @pytest.mark.asyncio
    async def test_explicit_config_override_denied(self, mock_session: AsyncMock) -> None:
        """An explicit config limit that is exceeded returns denied."""
        service = _make_service(mock_session)

        service._quota_repo = AsyncMock()
        service._quota_repo.get_monthly_event_count = AsyncMock(return_value=50)
        config_row = MagicMock()
        config_row.plan_quota_monthly = 25
        service._config_repo = AsyncMock()
        service._config_repo.get = AsyncMock(return_value=config_row)

        with patch.object(service, "_get_plan_tier", return_value="community"):
            allowed, reason = await service.check_plan_quota()

        assert allowed is False
        assert reason is not None
        assert "50/25" in reason

    @pytest.mark.asyncio
    async def test_team_tier_default_limit(self, mock_session: AsyncMock) -> None:
        """Team tier has plan_quota_monthly=1000."""
        service = _make_service(mock_session)

        service._quota_repo = AsyncMock()
        service._quota_repo.get_monthly_event_count = AsyncMock(return_value=999)
        service._config_repo = AsyncMock()
        service._config_repo.get = AsyncMock(return_value=None)

        with patch.object(service, "_get_plan_tier", return_value="team"):
            allowed, reason = await service.check_plan_quota()

        assert allowed is True
        assert reason is None


# ---------------------------------------------------------------------------
# AI Quota
# ---------------------------------------------------------------------------


class TestCheckAiQuota:
    """Verify check_ai_quota enforces monthly AI call limits correctly."""

    @pytest.mark.asyncio
    async def test_under_limit_returns_allowed(self, mock_session: AsyncMock) -> None:
        """When AI calls are under the limit, return (True, None)."""
        service = _make_service(mock_session)

        service._quota_repo = AsyncMock()
        service._quota_repo.get_monthly_event_count = AsyncMock(return_value=100)
        service._config_repo = AsyncMock()
        service._config_repo.get = AsyncMock(return_value=None)

        with patch.object(service, "_get_plan_tier", return_value="community"):
            allowed, reason = await service.check_ai_quota()

        assert allowed is True
        assert reason is None
        service._quota_repo.get_monthly_event_count.assert_called_once_with("ai_call")

    @pytest.mark.asyncio
    async def test_at_limit_returns_denied(self, mock_session: AsyncMock) -> None:
        """When AI calls equal the limit, return (False, message)."""
        service = _make_service(mock_session)

        service._quota_repo = AsyncMock()
        service._quota_repo.get_monthly_event_count = AsyncMock(return_value=500)
        service._config_repo = AsyncMock()
        service._config_repo.get = AsyncMock(return_value=None)

        with patch.object(service, "_get_plan_tier", return_value="community"):
            allowed, reason = await service.check_ai_quota()

        assert allowed is False
        assert reason is not None
        assert "500/500" in reason
        assert "ai call quota exceeded" in reason.lower()

    @pytest.mark.asyncio
    async def test_over_limit_returns_denied(self, mock_session: AsyncMock) -> None:
        """When AI calls exceed the community limit of 500, return denied."""
        service = _make_service(mock_session)

        service._quota_repo = AsyncMock()
        service._quota_repo.get_monthly_event_count = AsyncMock(return_value=750)
        service._config_repo = AsyncMock()
        service._config_repo.get = AsyncMock(return_value=None)

        with patch.object(service, "_get_plan_tier", return_value="community"):
            allowed, reason = await service.check_ai_quota()

        assert allowed is False
        assert reason is not None
        assert "750/500" in reason

    @pytest.mark.asyncio
    async def test_enterprise_unlimited_always_allowed(self, mock_session: AsyncMock) -> None:
        """Enterprise tier has unlimited AI calls, always allowed."""
        service = _make_service(mock_session)

        service._quota_repo = AsyncMock()
        service._quota_repo.get_monthly_event_count = AsyncMock(return_value=999_999)
        service._config_repo = AsyncMock()
        service._config_repo.get = AsyncMock(return_value=None)

        with patch.object(service, "_get_plan_tier", return_value="enterprise"):
            allowed, reason = await service.check_ai_quota()

        assert allowed is True
        assert reason is None
        service._quota_repo.get_monthly_event_count.assert_not_called()

    @pytest.mark.asyncio
    async def test_team_tier_default_limit(self, mock_session: AsyncMock) -> None:
        """Team tier has ai_quota_monthly=5000."""
        service = _make_service(mock_session)

        service._quota_repo = AsyncMock()
        service._quota_repo.get_monthly_event_count = AsyncMock(return_value=4999)
        service._config_repo = AsyncMock()
        service._config_repo.get = AsyncMock(return_value=None)

        with patch.object(service, "_get_plan_tier", return_value="team"):
            allowed, reason = await service.check_ai_quota()

        assert allowed is True
        assert reason is None

    @pytest.mark.asyncio
    async def test_explicit_config_overrides_tier_default(self, mock_session: AsyncMock) -> None:
        """Explicit ai_quota_monthly config overrides the tier default."""
        service = _make_service(mock_session)

        service._quota_repo = AsyncMock()
        service._quota_repo.get_monthly_event_count = AsyncMock(return_value=800)
        config_row = MagicMock()
        config_row.ai_quota_monthly = 1000
        service._config_repo = AsyncMock()
        service._config_repo.get = AsyncMock(return_value=config_row)

        with patch.object(service, "_get_plan_tier", return_value="community"):
            allowed, reason = await service.check_ai_quota()

        # 800 < 1000, so allowed despite community default of 500.
        assert allowed is True
        assert reason is None


# ---------------------------------------------------------------------------
# API Quota
# ---------------------------------------------------------------------------


class TestCheckApiQuota:
    """Verify check_api_quota enforces monthly API request limits correctly."""

    @pytest.mark.asyncio
    async def test_under_limit_returns_allowed(self, mock_session: AsyncMock) -> None:
        """When API requests are under the limit, return (True, None)."""
        service = _make_service(mock_session)

        service._quota_repo = AsyncMock()
        service._quota_repo.get_monthly_event_count = AsyncMock(return_value=5000)
        service._config_repo = AsyncMock()
        service._config_repo.get = AsyncMock(return_value=None)

        with patch.object(service, "_get_plan_tier", return_value="community"):
            allowed, reason = await service.check_api_quota()

        assert allowed is True
        assert reason is None
        service._quota_repo.get_monthly_event_count.assert_called_once_with("api_request")

    @pytest.mark.asyncio
    async def test_at_limit_returns_denied(self, mock_session: AsyncMock) -> None:
        """When API requests equal the limit, return (False, message)."""
        service = _make_service(mock_session)

        service._quota_repo = AsyncMock()
        service._quota_repo.get_monthly_event_count = AsyncMock(return_value=10_000)
        service._config_repo = AsyncMock()
        service._config_repo.get = AsyncMock(return_value=None)

        with patch.object(service, "_get_plan_tier", return_value="community"):
            allowed, reason = await service.check_api_quota()

        assert allowed is False
        assert reason is not None
        assert "10000/10000" in reason
        assert "api request quota exceeded" in reason.lower()

    @pytest.mark.asyncio
    async def test_over_limit_returns_denied(self, mock_session: AsyncMock) -> None:
        """When API requests exceed the community limit of 10000, return denied."""
        service = _make_service(mock_session)

        service._quota_repo = AsyncMock()
        service._quota_repo.get_monthly_event_count = AsyncMock(return_value=15_000)
        service._config_repo = AsyncMock()
        service._config_repo.get = AsyncMock(return_value=None)

        with patch.object(service, "_get_plan_tier", return_value="community"):
            allowed, reason = await service.check_api_quota()

        assert allowed is False
        assert reason is not None
        assert "15000/10000" in reason

    @pytest.mark.asyncio
    async def test_enterprise_unlimited_always_allowed(self, mock_session: AsyncMock) -> None:
        """Enterprise tier has unlimited API requests, always allowed."""
        service = _make_service(mock_session)

        service._quota_repo = AsyncMock()
        service._quota_repo.get_monthly_event_count = AsyncMock(return_value=999_999)
        service._config_repo = AsyncMock()
        service._config_repo.get = AsyncMock(return_value=None)

        with patch.object(service, "_get_plan_tier", return_value="enterprise"):
            allowed, reason = await service.check_api_quota()

        assert allowed is True
        assert reason is None
        service._quota_repo.get_monthly_event_count.assert_not_called()

    @pytest.mark.asyncio
    async def test_team_tier_default_limit(self, mock_session: AsyncMock) -> None:
        """Team tier has api_quota_monthly=100000."""
        service = _make_service(mock_session)

        service._quota_repo = AsyncMock()
        service._quota_repo.get_monthly_event_count = AsyncMock(return_value=99_999)
        service._config_repo = AsyncMock()
        service._config_repo.get = AsyncMock(return_value=None)

        with patch.object(service, "_get_plan_tier", return_value="team"):
            allowed, reason = await service.check_api_quota()

        assert allowed is True
        assert reason is None

    @pytest.mark.asyncio
    async def test_explicit_config_overrides_tier_default(self, mock_session: AsyncMock) -> None:
        """Explicit api_quota_monthly config overrides the tier default."""
        service = _make_service(mock_session)

        service._quota_repo = AsyncMock()
        service._quota_repo.get_monthly_event_count = AsyncMock(return_value=20_000)
        config_row = MagicMock()
        config_row.api_quota_monthly = 50_000
        service._config_repo = AsyncMock()
        service._config_repo.get = AsyncMock(return_value=config_row)

        with patch.object(service, "_get_plan_tier", return_value="community"):
            allowed, reason = await service.check_api_quota()

        # 20000 < 50000, so allowed despite community default of 10000.
        assert allowed is True
        assert reason is None


# ---------------------------------------------------------------------------
# LLM Budget
# ---------------------------------------------------------------------------


class TestCheckLlmBudget:
    """Verify check_llm_budget enforces daily and monthly LLM cost budgets."""

    @pytest.mark.asyncio
    async def test_no_config_returns_allowed(self, mock_session: AsyncMock) -> None:
        """When no tenant config exists, all LLM spending is allowed."""
        service = _make_service(mock_session)

        service._config_repo = AsyncMock()
        service._config_repo.get = AsyncMock(return_value=None)

        allowed, reason = await service.check_llm_budget()

        assert allowed is True
        assert reason is None

    @pytest.mark.asyncio
    async def test_within_both_budgets_returns_allowed(self, mock_session: AsyncMock) -> None:
        """When daily and monthly costs are within budgets, return allowed."""
        service = _make_service(mock_session)

        config_row = MagicMock()
        config_row.llm_daily_budget_usd = 10.0
        config_row.llm_monthly_budget_usd = 200.0
        service._config_repo = AsyncMock()
        service._config_repo.get = AsyncMock(return_value=config_row)

        service._llm_repo = AsyncMock()
        service._llm_repo.get_daily_cost = AsyncMock(return_value=5.0)
        service._llm_repo.get_monthly_cost = AsyncMock(return_value=100.0)

        allowed, reason = await service.check_llm_budget()

        assert allowed is True
        assert reason is None

    @pytest.mark.asyncio
    async def test_daily_budget_exceeded_returns_denied(self, mock_session: AsyncMock) -> None:
        """When daily cost meets or exceeds the daily budget, return denied."""
        service = _make_service(mock_session)

        config_row = MagicMock()
        config_row.llm_daily_budget_usd = 10.0
        config_row.llm_monthly_budget_usd = 200.0
        service._config_repo = AsyncMock()
        service._config_repo.get = AsyncMock(return_value=config_row)

        service._llm_repo = AsyncMock()
        service._llm_repo.get_daily_cost = AsyncMock(return_value=12.50)
        service._llm_repo.get_monthly_cost = AsyncMock(return_value=50.0)

        allowed, reason = await service.check_llm_budget()

        assert allowed is False
        assert reason is not None
        assert "daily llm budget exceeded" in reason.lower()
        assert "$12.50" in reason
        assert "$10.00" in reason

    @pytest.mark.asyncio
    async def test_daily_budget_exactly_at_limit_returns_denied(self, mock_session: AsyncMock) -> None:
        """When daily cost exactly equals the daily budget, return denied."""
        service = _make_service(mock_session)

        config_row = MagicMock()
        config_row.llm_daily_budget_usd = 10.0
        config_row.llm_monthly_budget_usd = 200.0
        service._config_repo = AsyncMock()
        service._config_repo.get = AsyncMock(return_value=config_row)

        service._llm_repo = AsyncMock()
        service._llm_repo.get_daily_cost = AsyncMock(return_value=10.0)
        service._llm_repo.get_monthly_cost = AsyncMock(return_value=50.0)

        allowed, reason = await service.check_llm_budget()

        assert allowed is False
        assert reason is not None
        assert "daily" in reason.lower()

    @pytest.mark.asyncio
    async def test_monthly_budget_exceeded_returns_denied(self, mock_session: AsyncMock) -> None:
        """When monthly cost meets or exceeds the monthly budget, return denied."""
        service = _make_service(mock_session)

        config_row = MagicMock()
        config_row.llm_daily_budget_usd = 50.0
        config_row.llm_monthly_budget_usd = 200.0
        service._config_repo = AsyncMock()
        service._config_repo.get = AsyncMock(return_value=config_row)

        service._llm_repo = AsyncMock()
        service._llm_repo.get_daily_cost = AsyncMock(return_value=5.0)
        service._llm_repo.get_monthly_cost = AsyncMock(return_value=250.0)

        allowed, reason = await service.check_llm_budget()

        assert allowed is False
        assert reason is not None
        assert "monthly llm budget exceeded" in reason.lower()
        assert "$250.00" in reason
        assert "$200.00" in reason

    @pytest.mark.asyncio
    async def test_only_daily_budget_set(self, mock_session: AsyncMock) -> None:
        """When only daily budget is configured and within limit, return allowed."""
        service = _make_service(mock_session)

        config_row = MagicMock()
        config_row.llm_daily_budget_usd = 10.0
        config_row.llm_monthly_budget_usd = None
        service._config_repo = AsyncMock()
        service._config_repo.get = AsyncMock(return_value=config_row)

        service._llm_repo = AsyncMock()
        service._llm_repo.get_daily_cost = AsyncMock(return_value=5.0)

        allowed, reason = await service.check_llm_budget()

        assert allowed is True
        assert reason is None

    @pytest.mark.asyncio
    async def test_only_monthly_budget_set(self, mock_session: AsyncMock) -> None:
        """When only monthly budget is configured and within limit, return allowed."""
        service = _make_service(mock_session)

        config_row = MagicMock()
        config_row.llm_daily_budget_usd = None
        config_row.llm_monthly_budget_usd = 200.0
        service._config_repo = AsyncMock()
        service._config_repo.get = AsyncMock(return_value=config_row)

        service._llm_repo = AsyncMock()
        service._llm_repo.get_monthly_cost = AsyncMock(return_value=100.0)

        allowed, reason = await service.check_llm_budget()

        assert allowed is True
        assert reason is None

    @pytest.mark.asyncio
    async def test_daily_checked_before_monthly(self, mock_session: AsyncMock) -> None:
        """When both budgets are exceeded, the daily check fires first."""
        service = _make_service(mock_session)

        config_row = MagicMock()
        config_row.llm_daily_budget_usd = 10.0
        config_row.llm_monthly_budget_usd = 200.0
        service._config_repo = AsyncMock()
        service._config_repo.get = AsyncMock(return_value=config_row)

        service._llm_repo = AsyncMock()
        service._llm_repo.get_daily_cost = AsyncMock(return_value=15.0)
        service._llm_repo.get_monthly_cost = AsyncMock(return_value=300.0)

        allowed, reason = await service.check_llm_budget()

        assert allowed is False
        assert "daily" in reason.lower()
        # Monthly cost should not even have been checked.
        service._llm_repo.get_monthly_cost.assert_not_called()


# ---------------------------------------------------------------------------
# Usage vs Limits
# ---------------------------------------------------------------------------


class TestGetUsageVsLimits:
    """Verify get_usage_vs_limits returns the correct structure for billing UI."""

    @pytest.mark.asyncio
    async def test_returns_correct_structure(self, mock_session: AsyncMock) -> None:
        """Result has 'quotas' list and 'llm_budget' dict."""
        service = _make_service(mock_session)

        service._quota_repo = AsyncMock()
        service._quota_repo.get_current_usage = AsyncMock(
            return_value={"plan_run": 42, "ai_call": 100, "api_request": 5000}
        )
        service._quota_repo.get_monthly_event_count = AsyncMock(return_value=0)

        service._config_repo = AsyncMock()
        service._config_repo.get = AsyncMock(return_value=None)

        service._llm_repo = AsyncMock()
        service._llm_repo.get_daily_cost = AsyncMock(return_value=2.50)
        service._llm_repo.get_monthly_cost = AsyncMock(return_value=45.0)

        with patch.object(service, "_get_plan_tier", return_value="community"):
            result = await service.get_usage_vs_limits()

        assert "quotas" in result
        assert "llm_budget" in result
        assert isinstance(result["quotas"], list)
        assert len(result["quotas"]) == 3

    @pytest.mark.asyncio
    async def test_quota_items_have_correct_fields(self, mock_session: AsyncMock) -> None:
        """Each quota item has name, event_type, used, limit, and percentage."""
        service = _make_service(mock_session)

        service._quota_repo = AsyncMock()
        service._quota_repo.get_current_usage = AsyncMock(
            return_value={"plan_run": 50, "ai_call": 250, "api_request": 5000}
        )

        service._config_repo = AsyncMock()
        service._config_repo.get = AsyncMock(return_value=None)

        service._llm_repo = AsyncMock()
        service._llm_repo.get_daily_cost = AsyncMock(return_value=0.0)
        service._llm_repo.get_monthly_cost = AsyncMock(return_value=0.0)

        with patch.object(service, "_get_plan_tier", return_value="community"):
            result = await service.get_usage_vs_limits()

        plan_quota = result["quotas"][0]
        assert plan_quota["name"] == "Plan Runs"
        assert plan_quota["event_type"] == "plan_run"
        assert plan_quota["used"] == 50
        assert plan_quota["limit"] == 100
        assert plan_quota["percentage"] == 50.0

        ai_quota = result["quotas"][1]
        assert ai_quota["name"] == "AI Calls"
        assert ai_quota["event_type"] == "ai_call"
        assert ai_quota["used"] == 250
        assert ai_quota["limit"] == 500
        assert ai_quota["percentage"] == 50.0

        api_quota = result["quotas"][2]
        assert api_quota["name"] == "API Requests"
        assert api_quota["event_type"] == "api_request"
        assert api_quota["used"] == 5000
        assert api_quota["limit"] == 10_000
        assert api_quota["percentage"] == 50.0

    @pytest.mark.asyncio
    async def test_enterprise_unlimited_percentage_is_none(self, mock_session: AsyncMock) -> None:
        """Enterprise tier quotas have limit=None and percentage=None."""
        service = _make_service(mock_session)

        service._quota_repo = AsyncMock()
        service._quota_repo.get_current_usage = AsyncMock(
            return_value={"plan_run": 500, "ai_call": 2000, "api_request": 50_000}
        )

        service._config_repo = AsyncMock()
        service._config_repo.get = AsyncMock(return_value=None)

        service._llm_repo = AsyncMock()
        service._llm_repo.get_daily_cost = AsyncMock(return_value=0.0)
        service._llm_repo.get_monthly_cost = AsyncMock(return_value=0.0)

        with patch.object(service, "_get_plan_tier", return_value="enterprise"):
            result = await service.get_usage_vs_limits()

        for quota in result["quotas"]:
            assert quota["limit"] is None
            assert quota["percentage"] is None

    @pytest.mark.asyncio
    async def test_llm_budget_includes_daily_and_monthly(self, mock_session: AsyncMock) -> None:
        """LLM budget section includes daily and monthly used/limit values."""
        service = _make_service(mock_session)

        config_row = MagicMock()
        config_row.llm_daily_budget_usd = 25.0
        config_row.llm_monthly_budget_usd = 500.0

        service._quota_repo = AsyncMock()
        service._quota_repo.get_current_usage = AsyncMock(return_value={"plan_run": 0, "ai_call": 0, "api_request": 0})

        service._config_repo = AsyncMock()
        service._config_repo.get = AsyncMock(return_value=config_row)

        service._llm_repo = AsyncMock()
        service._llm_repo.get_daily_cost = AsyncMock(return_value=8.1234)
        service._llm_repo.get_monthly_cost = AsyncMock(return_value=123.4567)

        with patch.object(service, "_get_plan_tier", return_value="team"):
            result = await service.get_usage_vs_limits()

        llm = result["llm_budget"]
        assert llm["daily_used_usd"] == 8.1234
        assert llm["daily_limit_usd"] == 25.0
        assert llm["monthly_used_usd"] == 123.4567
        assert llm["monthly_limit_usd"] == 500.0

    @pytest.mark.asyncio
    async def test_llm_budget_no_config_limits_are_none(self, mock_session: AsyncMock) -> None:
        """When no tenant config exists, LLM budget limits are None."""
        service = _make_service(mock_session)

        service._quota_repo = AsyncMock()
        service._quota_repo.get_current_usage = AsyncMock(return_value={"plan_run": 0, "ai_call": 0, "api_request": 0})

        service._config_repo = AsyncMock()
        service._config_repo.get = AsyncMock(return_value=None)

        service._llm_repo = AsyncMock()
        service._llm_repo.get_daily_cost = AsyncMock(return_value=0.0)
        service._llm_repo.get_monthly_cost = AsyncMock(return_value=0.0)

        with patch.object(service, "_get_plan_tier", return_value="community"):
            result = await service.get_usage_vs_limits()

        llm = result["llm_budget"]
        assert llm["daily_limit_usd"] is None
        assert llm["monthly_limit_usd"] is None

    @pytest.mark.asyncio
    async def test_missing_event_types_default_to_zero(self, mock_session: AsyncMock) -> None:
        """Event types not in the usage dict default to 0 used."""
        service = _make_service(mock_session)

        service._quota_repo = AsyncMock()
        # Return empty dict — no events at all.
        service._quota_repo.get_current_usage = AsyncMock(return_value={})

        service._config_repo = AsyncMock()
        service._config_repo.get = AsyncMock(return_value=None)

        service._llm_repo = AsyncMock()
        service._llm_repo.get_daily_cost = AsyncMock(return_value=0.0)
        service._llm_repo.get_monthly_cost = AsyncMock(return_value=0.0)

        with patch.object(service, "_get_plan_tier", return_value="community"):
            result = await service.get_usage_vs_limits()

        for quota in result["quotas"]:
            assert quota["used"] == 0
            assert quota["percentage"] == 0.0

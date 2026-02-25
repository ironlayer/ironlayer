"""Tests for seat-based quota enforcement in QuotaService.

Covers:
- Community tier (1 seat default): first user allowed, second blocked
- Team tier (10 seats default): up to 10 allowed, 11th blocked
- Enterprise tier (unlimited): always allowed
- Explicit max_seats override on tenant_config overrides tier default
- get_usage_vs_limits() returns correct seat info
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from api.services.quota_service import QuotaService

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_billing_row(tier: str = "community") -> MagicMock:
    """Return a mock scalar result that returns a plan tier string."""
    row = MagicMock()
    row.plan_tier = tier
    return row


def _make_config_row(max_seats: int | None = None) -> MagicMock:
    """Return a mock TenantConfigTable row."""
    config = MagicMock()
    config.max_seats = max_seats
    config.plan_quota_monthly = None
    config.ai_quota_monthly = None
    config.api_quota_monthly = None
    config.llm_daily_budget_usd = None
    config.llm_monthly_budget_usd = None
    return config


def _build_service(
    tier: str = "community",
    current_users: int = 0,
    config_max_seats: int | None = None,
    has_config: bool = True,
) -> QuotaService:
    """Build a QuotaService with mocked repositories.

    Parameters
    ----------
    tier:
        The billing plan tier to simulate.
    current_users:
        Number of active users the mock UserRepository.count_by_tenant returns.
    config_max_seats:
        Explicit max_seats override on tenant_config (None = no override).
    has_config:
        Whether a tenant_config row exists.
    """
    session = AsyncMock()
    # Advisory locks are no-ops (SQLite dialect detection).
    bind = MagicMock()
    bind.dialect.name = "sqlite"
    session.get_bind = MagicMock(return_value=bind)

    service = QuotaService(session, tenant_id="test-tenant")

    # Mock _get_plan_tier to return the desired tier.
    tier_result = MagicMock()
    tier_result.scalar_one_or_none.return_value = tier

    # Mock tenant config repository.
    config_row = _make_config_row(max_seats=config_max_seats) if has_config else None
    service._config_repo = MagicMock()
    service._config_repo.get = AsyncMock(return_value=config_row)

    # Mock the billing tier lookup via _get_plan_tier.
    service._get_plan_tier = AsyncMock(return_value=tier)

    # Mock the UserRepository that is instantiated inside check_seat_quota.
    mock_user_repo = MagicMock()
    mock_user_repo.count_by_tenant = AsyncMock(return_value=current_users)

    # Patch UserRepository construction inside quota_service.
    service._mock_user_repo = mock_user_repo

    return service


def _patch_user_repo(service: QuotaService):
    """Return a patch context for UserRepository used in the quota service."""
    return patch(
        "api.services.quota_service.UserRepository",
        return_value=service._mock_user_repo,
    )


# ---------------------------------------------------------------------------
# Community tier (default: 1 seat)
# ---------------------------------------------------------------------------


class TestCommunitySeatQuota:
    """Community tier allows exactly 1 seat by default."""

    @pytest.mark.asyncio
    async def test_first_user_allowed(self) -> None:
        """A brand-new community tenant (0 users) can add the first user."""
        service = _build_service(tier="community", current_users=0)
        with _patch_user_repo(service):
            allowed, reason = await service.check_seat_quota()
        assert allowed is True
        assert reason is None

    @pytest.mark.asyncio
    async def test_second_user_blocked(self) -> None:
        """A community tenant with 1 user cannot add a second."""
        service = _build_service(tier="community", current_users=1)
        with _patch_user_repo(service):
            allowed, reason = await service.check_seat_quota()
        assert allowed is False
        assert reason is not None
        assert "1/1" in reason
        assert "Seat limit reached" in reason

    @pytest.mark.asyncio
    async def test_multiple_users_blocked(self) -> None:
        """A community tenant already over limit is still blocked."""
        service = _build_service(tier="community", current_users=5)
        with _patch_user_repo(service):
            allowed, reason = await service.check_seat_quota()
        assert allowed is False
        assert reason is not None


# ---------------------------------------------------------------------------
# Team tier (default: 10 seats)
# ---------------------------------------------------------------------------


class TestTeamSeatQuota:
    """Team tier allows up to 10 seats by default."""

    @pytest.mark.asyncio
    async def test_under_limit_allowed(self) -> None:
        """A team tenant with fewer than 10 users can add another."""
        service = _build_service(tier="team", current_users=5)
        with _patch_user_repo(service):
            allowed, reason = await service.check_seat_quota()
        assert allowed is True
        assert reason is None

    @pytest.mark.asyncio
    async def test_at_limit_blocked(self) -> None:
        """A team tenant with exactly 10 users cannot add the 11th."""
        service = _build_service(tier="team", current_users=10)
        with _patch_user_repo(service):
            allowed, reason = await service.check_seat_quota()
        assert allowed is False
        assert reason is not None
        assert "10/10" in reason

    @pytest.mark.asyncio
    async def test_one_under_limit_allowed(self) -> None:
        """A team tenant with 9 users can add the 10th."""
        service = _build_service(tier="team", current_users=9)
        with _patch_user_repo(service):
            allowed, reason = await service.check_seat_quota()
        assert allowed is True
        assert reason is None

    @pytest.mark.asyncio
    async def test_over_limit_blocked(self) -> None:
        """A team tenant already over limit is still blocked."""
        service = _build_service(tier="team", current_users=15)
        with _patch_user_repo(service):
            allowed, reason = await service.check_seat_quota()
        assert allowed is False
        assert reason is not None


# ---------------------------------------------------------------------------
# Enterprise tier (unlimited)
# ---------------------------------------------------------------------------


class TestEnterpriseSeatQuota:
    """Enterprise tier has no seat limit (None = unlimited)."""

    @pytest.mark.asyncio
    async def test_always_allowed(self) -> None:
        """Enterprise tenants can add users without limit."""
        service = _build_service(tier="enterprise", current_users=100)
        with _patch_user_repo(service):
            allowed, reason = await service.check_seat_quota()
        assert allowed is True
        assert reason is None

    @pytest.mark.asyncio
    async def test_zero_users_allowed(self) -> None:
        """Enterprise tenant with no users can add the first."""
        service = _build_service(tier="enterprise", current_users=0)
        with _patch_user_repo(service):
            allowed, reason = await service.check_seat_quota()
        assert allowed is True
        assert reason is None

    @pytest.mark.asyncio
    async def test_large_count_allowed(self) -> None:
        """Enterprise tenant with many users is still allowed."""
        service = _build_service(tier="enterprise", current_users=1000)
        with _patch_user_repo(service):
            allowed, reason = await service.check_seat_quota()
        assert allowed is True
        assert reason is None


# ---------------------------------------------------------------------------
# Explicit max_seats override
# ---------------------------------------------------------------------------


class TestExplicitMaxSeatsOverride:
    """Explicit tenant_config.max_seats overrides tier defaults."""

    @pytest.mark.asyncio
    async def test_override_higher_than_default(self) -> None:
        """Community tenant with max_seats=5 override allows up to 5."""
        service = _build_service(
            tier="community",
            current_users=3,
            config_max_seats=5,
        )
        with _patch_user_repo(service):
            allowed, reason = await service.check_seat_quota()
        assert allowed is True
        assert reason is None

    @pytest.mark.asyncio
    async def test_override_reached(self) -> None:
        """Community tenant with max_seats=5 blocks at 5 users."""
        service = _build_service(
            tier="community",
            current_users=5,
            config_max_seats=5,
        )
        with _patch_user_repo(service):
            allowed, reason = await service.check_seat_quota()
        assert allowed is False
        assert "5/5" in (reason or "")

    @pytest.mark.asyncio
    async def test_override_lower_than_default(self) -> None:
        """Team tenant with max_seats=3 blocks at 3 (lower than default 10)."""
        service = _build_service(
            tier="team",
            current_users=3,
            config_max_seats=3,
        )
        with _patch_user_repo(service):
            allowed, reason = await service.check_seat_quota()
        assert allowed is False
        assert "3/3" in (reason or "")

    @pytest.mark.asyncio
    async def test_no_config_row_uses_tier_default(self) -> None:
        """When no tenant_config exists, tier default applies."""
        service = _build_service(
            tier="team",
            current_users=9,
            has_config=False,
        )
        with _patch_user_repo(service):
            allowed, reason = await service.check_seat_quota()
        assert allowed is True
        assert reason is None


# ---------------------------------------------------------------------------
# get_usage_vs_limits() seat info
# ---------------------------------------------------------------------------


class TestUsageVsLimitsSeatInfo:
    """Verify get_usage_vs_limits() includes correct seat information."""

    @pytest.mark.asyncio
    async def test_seat_info_community(self) -> None:
        """Community tier returns seat usage with limit=1."""
        service = _build_service(tier="community", current_users=1)

        # Mock quota repo for get_usage_vs_limits.
        service._quota_repo = MagicMock()
        service._quota_repo.get_current_usage = AsyncMock(return_value={})
        service._quota_repo.get_monthly_event_count = AsyncMock(return_value=0)

        # Mock LLM usage repo.
        service._llm_repo = MagicMock()
        service._llm_repo.get_daily_cost = AsyncMock(return_value=0.0)
        service._llm_repo.get_monthly_cost = AsyncMock(return_value=0.0)

        with _patch_user_repo(service):
            result = await service.get_usage_vs_limits()

        assert "seats" in result
        seats = result["seats"]
        assert seats["used"] == 1
        assert seats["limit"] == 1
        assert seats["percentage"] == 100.0

    @pytest.mark.asyncio
    async def test_seat_info_team(self) -> None:
        """Team tier returns seat usage with limit=10."""
        service = _build_service(tier="team", current_users=5)

        service._quota_repo = MagicMock()
        service._quota_repo.get_current_usage = AsyncMock(return_value={})
        service._quota_repo.get_monthly_event_count = AsyncMock(return_value=0)

        service._llm_repo = MagicMock()
        service._llm_repo.get_daily_cost = AsyncMock(return_value=0.0)
        service._llm_repo.get_monthly_cost = AsyncMock(return_value=0.0)

        with _patch_user_repo(service):
            result = await service.get_usage_vs_limits()

        seats = result["seats"]
        assert seats["used"] == 5
        assert seats["limit"] == 10
        assert seats["percentage"] == 50.0

    @pytest.mark.asyncio
    async def test_seat_info_enterprise_unlimited(self) -> None:
        """Enterprise tier returns seat usage with limit=None."""
        service = _build_service(tier="enterprise", current_users=50)

        service._quota_repo = MagicMock()
        service._quota_repo.get_current_usage = AsyncMock(return_value={})
        service._quota_repo.get_monthly_event_count = AsyncMock(return_value=0)

        service._llm_repo = MagicMock()
        service._llm_repo.get_daily_cost = AsyncMock(return_value=0.0)
        service._llm_repo.get_monthly_cost = AsyncMock(return_value=0.0)

        with _patch_user_repo(service):
            result = await service.get_usage_vs_limits()

        seats = result["seats"]
        assert seats["used"] == 50
        assert seats["limit"] is None
        assert seats["percentage"] is None

    @pytest.mark.asyncio
    async def test_seat_info_with_override(self) -> None:
        """Explicit max_seats override reflected in usage response."""
        service = _build_service(
            tier="community",
            current_users=3,
            config_max_seats=5,
        )

        service._quota_repo = MagicMock()
        service._quota_repo.get_current_usage = AsyncMock(return_value={})
        service._quota_repo.get_monthly_event_count = AsyncMock(return_value=0)

        service._llm_repo = MagicMock()
        service._llm_repo.get_daily_cost = AsyncMock(return_value=0.0)
        service._llm_repo.get_monthly_cost = AsyncMock(return_value=0.0)

        with _patch_user_repo(service):
            result = await service.get_usage_vs_limits()

        seats = result["seats"]
        assert seats["used"] == 3
        assert seats["limit"] == 5
        assert seats["percentage"] == 60.0

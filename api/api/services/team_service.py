"""Team management service for member CRUD, seat enforcement, and Stripe sync.

Provides operations for listing, inviting, removing, and updating team
members.  Seat quota enforcement uses the :class:`QuotaService` advisory
lock pattern to prevent concurrent invites from exceeding the seat limit.
Stripe subscription quantity is synced as a best-effort side effect after
member count changes.
"""

from __future__ import annotations

import logging
from typing import Any

import stripe
from core_engine.state.repository import UserRepository
from core_engine.state.tables import BillingCustomerTable
from sqlalchemy.ext.asyncio import AsyncSession

from api.config import APISettings
from api.services.quota_service import QuotaService

logger = logging.getLogger(__name__)


class TeamService:
    """CRUD operations for team members with seat enforcement and Stripe sync.

    Parameters
    ----------
    session:
        Active database session with RLS tenant context.
    settings:
        API settings containing Stripe configuration.
    tenant_id:
        The tenant performing team operations.
    """

    def __init__(
        self,
        session: AsyncSession,
        settings: APISettings,
        *,
        tenant_id: str,
    ) -> None:
        self._session = session
        self._settings = settings
        self._tenant_id = tenant_id
        self._user_repo = UserRepository(session, tenant_id=tenant_id)

    async def list_members(self) -> dict[str, Any]:
        """Return all team members with seat usage information.

        Returns
        -------
        dict
            Contains ``members`` list, ``total``, ``seat_limit``, and
            ``seats_used`` for frontend display.
        """
        users = await self._user_repo.list_by_tenant()
        quota = QuotaService(self._session, self._tenant_id)
        seat_limit = await quota._get_effective_seat_limit()
        seats_used = len(users)

        members = [
            {
                "id": user.id,
                "email": user.email,
                "display_name": user.display_name,
                "role": user.role,
                "is_active": user.is_active,
                "created_at": user.created_at.isoformat() if user.created_at else None,
                "last_login_at": user.last_login_at.isoformat() if user.last_login_at else None,
            }
            for user in users
        ]

        return {
            "members": members,
            "total": seats_used,
            "seat_limit": seat_limit,
            "seats_used": seats_used,
        }

    async def invite_member(
        self,
        email: str,
        role: str,
        invited_by: str,
    ) -> dict[str, Any]:
        """Invite a new team member with seat quota enforcement.

        1. Checks seat quota (with advisory lock to prevent races).
        2. Creates the user with a random temporary password.
        3. Syncs Stripe subscription quantity (best-effort).

        Parameters
        ----------
        email:
            Email address of the new team member.
        role:
            Role to assign (viewer, operator, engineer, admin).
        invited_by:
            User ID of the admin performing the invitation.

        Returns
        -------
        dict
            The new user's information.

        Raises
        ------
        ValueError
            If the email is already registered for this tenant.
        PermissionError
            If the seat quota has been reached.
        """
        # Check seat quota first (with advisory lock).
        quota = QuotaService(self._session, self._tenant_id)
        allowed, reason = await quota.check_seat_quota()
        if not allowed:
            raise PermissionError(reason)

        # Check for existing user with this email in the tenant.
        existing = await self._user_repo.get_by_email(email)
        if existing is not None:
            if existing.is_active:
                raise ValueError(f"User with email '{email}' already exists in this tenant.")
            # Reactivate a previously removed member.
            existing.is_active = True
            existing.role = role
            await self._session.flush()
            await self._sync_stripe_quantity()
            return {
                "id": existing.id,
                "email": existing.email,
                "display_name": existing.display_name,
                "role": existing.role,
                "is_active": existing.is_active,
                "created_at": existing.created_at.isoformat() if existing.created_at else None,
            }

        # Create new user with a temporary password.
        # In production, an email-based invite flow would replace this.
        import secrets

        temp_password = secrets.token_urlsafe(24)
        user = await self._user_repo.create(
            email=email,
            password=temp_password,
            display_name=email.split("@")[0],
            role=role,
        )

        # Best-effort Stripe quantity sync.
        await self._sync_stripe_quantity()

        return {
            "id": user.id,
            "email": user.email,
            "display_name": user.display_name,
            "role": user.role,
            "is_active": user.is_active,
            "created_at": user.created_at.isoformat() if user.created_at else None,
        }

    async def remove_member(self, user_id: str) -> dict[str, Any]:
        """Soft-delete a team member by setting is_active=False.

        Parameters
        ----------
        user_id:
            The ID of the user to remove.

        Returns
        -------
        dict
            The updated user info.

        Raises
        ------
        ValueError
            If the user does not exist or is already inactive.
        """
        user = await self._user_repo.get_by_id(user_id)
        if user is None:
            raise ValueError(f"User '{user_id}' not found in this tenant.")
        if not user.is_active:
            raise ValueError(f"User '{user_id}' is already inactive.")

        user.is_active = False
        await self._session.flush()

        # Best-effort Stripe quantity sync.
        await self._sync_stripe_quantity()

        return {
            "id": user.id,
            "email": user.email,
            "display_name": user.display_name,
            "role": user.role,
            "is_active": user.is_active,
        }

    async def update_role(self, user_id: str, new_role: str) -> dict[str, Any]:
        """Change a team member's role.

        Parameters
        ----------
        user_id:
            The ID of the user whose role to change.
        new_role:
            The new role to assign (viewer, operator, engineer, admin).

        Returns
        -------
        dict
            The updated user info.

        Raises
        ------
        ValueError
            If the user does not exist.
        """
        valid_roles = {"viewer", "operator", "engineer", "admin"}
        if new_role not in valid_roles:
            raise ValueError(f"Invalid role '{new_role}'. Must be one of: {sorted(valid_roles)}")

        user = await self._user_repo.get_by_id(user_id)
        if user is None:
            raise ValueError(f"User '{user_id}' not found in this tenant.")

        user.role = new_role
        await self._session.flush()

        return {
            "id": user.id,
            "email": user.email,
            "display_name": user.display_name,
            "role": user.role,
            "is_active": user.is_active,
        }

    async def _sync_stripe_quantity(self) -> None:
        """Sync the active member count to the Stripe subscription quantity.

        This is a best-effort operation: if Stripe is not configured or the
        API call fails, the error is logged but does not fail the parent
        operation.
        """
        if not self._settings.billing_enabled:
            return

        try:
            from sqlalchemy import select

            result = await self._session.execute(
                select(BillingCustomerTable).where(BillingCustomerTable.tenant_id == self._tenant_id)
            )
            billing_row = result.scalar_one_or_none()

            if billing_row is None or not billing_row.stripe_subscription_id:
                return

            active_count = await self._user_repo.count_by_tenant()

            stripe.api_key = self._settings.stripe_secret_key.get_secret_value()
            subscription = stripe.Subscription.retrieve(
                billing_row.stripe_subscription_id,
                expand=["items.data"],
            )

            items = subscription.get("items", {}).get("data", [])
            if items:
                stripe.SubscriptionItem.modify(
                    items[0]["id"],
                    quantity=max(active_count, 1),
                )
                logger.info(
                    "Synced Stripe quantity to %d for tenant %s",
                    active_count,
                    self._tenant_id,
                )
        except Exception:
            logger.warning(
                "Failed to sync Stripe subscription quantity for tenant %s",
                self._tenant_id,
                exc_info=True,
            )

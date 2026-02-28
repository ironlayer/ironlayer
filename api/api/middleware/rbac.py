"""Role-Based Access Control middleware and decorators.

Defines a four-tier role hierarchy (VIEWER, OPERATOR, ENGINEER, ADMIN)
with fine-grained permissions.  Each role inherits all permissions from
the roles below it in the hierarchy.

Usage in routers::

    from api.middleware.rbac import Permission, Role, require_permission

    @router.get("")
    async def list_plans(
        ...,
        _role: Role = Depends(require_permission(Permission.READ_PLANS)),
    ) -> ...:
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from enum import Enum, IntEnum

from fastapi import Depends, HTTPException, Request

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Role hierarchy (higher int = more authority)
# ---------------------------------------------------------------------------


class Role(IntEnum):
    """User roles ordered by privilege level.

    The integer value encodes hierarchy: every role implicitly inherits
    the capabilities of roles with lower numeric values.
    """

    VIEWER = 0
    OPERATOR = 1
    ENGINEER = 2
    ADMIN = 3
    SERVICE = 10  # Non-hierarchical: outside 0-3 range to avoid inheriting approval perms


# Mapping from the string claim value to the enum member.
_ROLE_LOOKUP: dict[str, Role] = {r.name.lower(): r for r in Role}


def parse_role(raw: str) -> Role:
    """Convert a JWT ``role`` claim string into a :class:`Role`.

    Raises :class:`ValueError` if the string does not map to a known role.
    """
    try:
        return _ROLE_LOOKUP[raw.strip().lower()]
    except KeyError:
        raise ValueError(f"Unknown role '{raw}'. Valid roles: {sorted(_ROLE_LOOKUP)}")


# ---------------------------------------------------------------------------
# Permissions
# ---------------------------------------------------------------------------


class Permission(str, Enum):
    """Fine-grained permission tokens checked by endpoint guards."""

    # Plans
    READ_PLANS = "read:plans"
    CREATE_PLANS = "create:plans"
    APPROVE_PLANS = "approve:plans"
    APPLY_PLANS = "apply:plans"

    # Models
    READ_MODELS = "read:models"
    WRITE_MODELS = "write:models"

    # Runs
    READ_RUNS = "read:runs"

    # Backfills
    CREATE_BACKFILLS = "create:backfills"

    # Administration
    MANAGE_CREDENTIALS = "manage:credentials"
    READ_AUDIT = "read:audit"
    MANAGE_SETTINGS = "manage:settings"
    MANAGE_WEBHOOKS = "manage:webhooks"

    # Tests
    RUN_TESTS = "run:tests"
    READ_TEST_RESULTS = "read:test_results"

    # Checks (unified check engine)
    RUN_CHECKS = "run:checks"
    READ_CHECK_RESULTS = "read:check_results"

    # Environments
    MANAGE_ENVIRONMENTS = "manage:environments"
    CREATE_EPHEMERAL_ENVS = "create:ephemeral_environments"
    PROMOTE_ENVIRONMENTS = "promote:environments"

    # Analytics & reporting (admin)
    VIEW_ANALYTICS = "view:analytics"
    VIEW_REPORTS = "view:reports"
    MANAGE_HEALTH = "manage:health"
    VIEW_INVOICES = "view:invoices"


# ---------------------------------------------------------------------------
# Role -> Permission mapping (each role inherits from the tier below)
# ---------------------------------------------------------------------------

_VIEWER_PERMS: frozenset[Permission] = frozenset(
    {
        Permission.READ_PLANS,
        Permission.READ_MODELS,
        Permission.READ_RUNS,
        Permission.READ_TEST_RESULTS,
        Permission.READ_CHECK_RESULTS,
    }
)

_OPERATOR_PERMS: frozenset[Permission] = _VIEWER_PERMS | frozenset(
    {
        Permission.APPROVE_PLANS,
        Permission.CREATE_BACKFILLS,
        Permission.READ_AUDIT,
    }
)

_ENGINEER_PERMS: frozenset[Permission] = _OPERATOR_PERMS | frozenset(
    {
        Permission.CREATE_PLANS,
        Permission.APPLY_PLANS,
        Permission.WRITE_MODELS,
        Permission.CREATE_EPHEMERAL_ENVS,
        Permission.RUN_TESTS,
        Permission.RUN_CHECKS,
    }
)

_ADMIN_PERMS: frozenset[Permission] = _ENGINEER_PERMS | frozenset(
    {
        Permission.MANAGE_CREDENTIALS,
        Permission.MANAGE_SETTINGS,
        Permission.MANAGE_WEBHOOKS,
        Permission.MANAGE_ENVIRONMENTS,
        Permission.PROMOTE_ENVIRONMENTS,
        Permission.VIEW_ANALYTICS,
        Permission.VIEW_REPORTS,
        Permission.MANAGE_HEALTH,
        Permission.VIEW_INVOICES,
    }
)

_SERVICE_PERMS: frozenset[Permission] = frozenset(
    {
        Permission.READ_PLANS,
        Permission.READ_MODELS,
        Permission.READ_RUNS,
        Permission.CREATE_PLANS,
        Permission.APPLY_PLANS,
    }
)

ROLE_PERMISSIONS: dict[Role, frozenset[Permission]] = {
    Role.VIEWER: _VIEWER_PERMS,
    Role.OPERATOR: _OPERATOR_PERMS,
    Role.ENGINEER: _ENGINEER_PERMS,
    Role.ADMIN: _ADMIN_PERMS,
    Role.SERVICE: _SERVICE_PERMS,
}


def role_has_permission(role: Role, permission: Permission) -> bool:
    """Return ``True`` if *role* grants *permission*."""
    return permission in ROLE_PERMISSIONS.get(role, frozenset())


# ---------------------------------------------------------------------------
# FastAPI dependency: extract role from request.state
# ---------------------------------------------------------------------------


def get_user_role(request: Request) -> Role:
    """Extract and validate the user role from ``request.state.role``.

    The :class:`AuthenticationMiddleware` is responsible for setting
    ``request.state.role`` from the JWT ``role`` claim.

    If the request passed authentication (``request.state.sub`` is set)
    but has no ``role`` attribute, the token is malformed and a 401 is
    raised.  This prevents silently granting viewer access to
    authenticated requests whose tokens lack a role claim.

    For unauthenticated public endpoints (where neither ``sub`` nor
    ``role`` is present on ``request.state``), the default ``VIEWER``
    role is returned so that public read-only paths work without a
    token.  These endpoints are additionally gated by the auth
    middleware's ``_PUBLIC_PATHS`` whitelist.

    Raises
    ------
    HTTPException(401)
        If the request is authenticated but the role claim is missing.
    HTTPException(403)
        If the role claim value is not a recognised role.
    """
    raw_role: str | None = getattr(request.state, "role", None)
    if raw_role is None:
        # Distinguish authenticated-but-missing-role from unauthenticated.
        # The auth middleware always sets ``request.state.sub`` for
        # authenticated requests.  If ``sub`` exists but ``role`` does
        # not, the token is malformed.
        is_authenticated = getattr(request.state, "sub", None) is not None
        if is_authenticated:
            logger.warning(
                "Authenticated request (sub=%s) missing role claim; rejecting",
                getattr(request.state, "sub", "unknown"),
            )
            raise HTTPException(
                status_code=401,
                detail="Missing role claim in authenticated token",
            )
        # Unauthenticated public path -- allow with least-privilege role.
        return Role.VIEWER

    try:
        return parse_role(raw_role)
    except ValueError:
        logger.warning("Unrecognised role claim '%s'; denying access", raw_role)
        raise HTTPException(
            status_code=403,
            detail=f"Unrecognised role '{raw_role}'. Valid roles: {sorted(_ROLE_LOOKUP)}",
        )


# ---------------------------------------------------------------------------
# FastAPI dependencies: permission and role guards
# ---------------------------------------------------------------------------


def require_permission(permission: Permission) -> Callable[..., Role]:
    """Return a FastAPI dependency that enforces a specific permission.

    Example::

        @router.get("/plans")
        async def list_plans(
            _role: Role = Depends(require_permission(Permission.READ_PLANS)),
        ):
            ...

    Returns the resolved :class:`Role` so downstream handlers can inspect
    it if needed.
    """

    def _guard(role: Role = Depends(get_user_role)) -> Role:
        if not role_has_permission(role, permission):
            logger.info(
                "Permission denied: role=%s requires %s",
                role.name,
                permission.value,
            )
            raise HTTPException(
                status_code=403,
                detail=(f"Permission denied: role '{role.name.lower()}' does not have '{permission.value}' permission"),
            )
        return role

    return _guard


def require_role(min_role: Role) -> Callable[..., Role]:
    """Return a FastAPI dependency that enforces a minimum role level.

    Example::

        @router.delete("/settings/dangerous")
        async def nuke(
            _role: Role = Depends(require_role(Role.ADMIN)),
        ):
            ...
    """

    def _guard(role: Role = Depends(get_user_role)) -> Role:
        # SERVICE accounts must not pass role-based checks via numeric
        # comparison (SERVICE=10 > ADMIN=3).  They are non-hierarchical
        # and should use permission-based auth instead.
        if role == Role.SERVICE:
            logger.info(
                "Service account attempted role-based access: requires %s",
                min_role.name,
            )
            raise HTTPException(
                status_code=403,
                detail=(
                    "Service accounts must use permission-based auth, not role-based. "
                    "Use require_permission() instead of require_role() for service-accessible endpoints."
                ),
            )
        if role < min_role:
            logger.info(
                "Role check failed: has=%s, required=%s",
                role.name,
                min_role.name,
            )
            raise HTTPException(
                status_code=403,
                detail=(f"Insufficient role: '{role.name.lower()}' requires at least '{min_role.name.lower()}'"),
            )
        return role

    return _guard

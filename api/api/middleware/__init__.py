"""Middleware components for the IronLayer API."""

from __future__ import annotations

from api.middleware.auth import AuthenticationMiddleware
from api.middleware.csp import ContentSecurityPolicyMiddleware
from api.middleware.csrf import CSRFMiddleware
from api.middleware.logging import RequestLoggingMiddleware
from api.middleware.login_rate_limiter import LoginRateLimiter
from api.middleware.rate_limit import RateLimitConfig, RateLimitMiddleware
from api.middleware.rbac import (
    ROLE_PERMISSIONS,
    Permission,
    Role,
    get_user_role,
    require_permission,
    require_role,
)

__all__ = [
    "AuthenticationMiddleware",
    "CSRFMiddleware",
    "ContentSecurityPolicyMiddleware",
    "LoginRateLimiter",
    "Permission",
    "ROLE_PERMISSIONS",
    "RateLimitConfig",
    "RateLimitMiddleware",
    "RequestLoggingMiddleware",
    "Role",
    "get_user_role",
    "require_permission",
    "require_role",
]

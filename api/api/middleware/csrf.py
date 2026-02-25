"""CSRF protection middleware for cookie-based authentication.

Implements the double-submit cookie pattern:

1. On safe requests (GET, HEAD, OPTIONS), the middleware ensures a ``csrf_token``
   cookie is set.  This cookie is **not** HttpOnly so that JavaScript can read it.
2. On state-changing requests (POST, PUT, DELETE, PATCH), the middleware validates
   that the ``X-CSRF-Token`` header matches the ``csrf_token`` cookie.
3. CSRF validation is **only enforced** on requests that carry a ``refresh_token``
   cookie (i.e. browser sessions).  Requests authenticated via API keys or
   Bearer tokens without a cookie are not susceptible to CSRF.

The ``SameSite=Strict`` attribute on both the refresh and CSRF cookies provides
defence-in-depth, but the double-submit check remains as a second layer.
"""

from __future__ import annotations

import logging
import secrets

from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import JSONResponse, Response

logger = logging.getLogger(__name__)

_SAFE_METHODS = frozenset({"GET", "HEAD", "OPTIONS"})
_CSRF_COOKIE = "csrf_token"
_CSRF_HEADER = "X-CSRF-Token"
_CSRF_COOKIE_MAX_AGE = 7 * 24 * 3600  # 7 days, matches refresh token


class CSRFMiddleware(BaseHTTPMiddleware):
    """Validates that state-changing requests include a valid CSRF token.

    The token is validated using :func:`secrets.compare_digest` to prevent
    timing side-channel attacks.
    """

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        # Safe methods do not need CSRF protection.
        if request.method in _SAFE_METHODS:
            response = await call_next(request)
            # Ensure the CSRF cookie exists (set on first GET so JS can read it).
            if _CSRF_COOKIE not in request.cookies:
                csrf_token = secrets.token_hex(32)
                response.set_cookie(
                    key=_CSRF_COOKIE,
                    value=csrf_token,
                    httponly=False,  # JavaScript must be able to read this.
                    secure=True,
                    samesite="strict",
                    max_age=_CSRF_COOKIE_MAX_AGE,
                    path="/",
                )
            return response

        # State-changing methods: validate CSRF token.
        cookie_token = request.cookies.get(_CSRF_COOKIE, "")
        header_token = request.headers.get(_CSRF_HEADER, "")

        # Only enforce on endpoints that use cookie-based auth.
        # API-key / Bearer-only requests don't carry a refresh_token cookie
        # and therefore aren't susceptible to CSRF.
        if "refresh_token" not in request.cookies:
            return await call_next(request)

        if not cookie_token or not header_token:
            logger.warning(
                "CSRF token missing on cookie-authenticated request: %s %s",
                request.method,
                request.url.path,
            )
            return JSONResponse(
                {"detail": "CSRF token required"},
                status_code=403,
            )

        if not secrets.compare_digest(cookie_token, header_token):
            logger.warning(
                "CSRF token mismatch: %s %s",
                request.method,
                request.url.path,
            )
            return JSONResponse(
                {"detail": "CSRF token mismatch"},
                status_code=403,
            )

        return await call_next(request)

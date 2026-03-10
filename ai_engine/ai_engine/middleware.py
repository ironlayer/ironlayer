"""Authentication, rate limiting, and request size middleware for the AI engine.

Pure ASGI middleware — no BaseHTTPMiddleware dependency.  Each class
implements ``__init__(app, ...)`` + ``async __call__(scope, receive, send)``
and is registered via ``app.add_middleware(ClassName, **kwargs)``.
"""

from __future__ import annotations

import json
import logging
import os
import re
import secrets
import time
from collections import defaultdict
from typing import Any, Callable

logger = logging.getLogger(__name__)

# Type aliases for ASGI callables.
ASGIApp = Any
Scope = dict[str, Any]
Receive = Callable[..., Any]
Send = Callable[..., Any]

# Paths that bypass authentication and rate limiting (health checks, readiness probes).
_PUBLIC_PATHS: frozenset[str] = frozenset({"/health", "/healthz", "/readyz"})


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------


def _get_header(scope: Scope, name: bytes) -> bytes:
    """Extract a header value from ASGI scope (lowercase byte-tuple list)."""
    for key, val in scope.get("headers", []):
        if key == name:
            return val
    return b""


async def _send_json_error(
    send: Send,
    status: int,
    detail: str,
    *,
    extra_headers: list[tuple[bytes, bytes]] | None = None,
) -> None:
    """Send a complete JSON error response via raw ASGI send."""
    body = json.dumps({"detail": detail}).encode()
    headers: list[tuple[bytes, bytes]] = [
        (b"content-type", b"application/json"),
        (b"content-length", str(len(body)).encode()),
    ]
    if extra_headers:
        headers.extend(extra_headers)
    await send({
        "type": "http.response.start",
        "status": status,
        "headers": headers,
    })
    await send({
        "type": "http.response.body",
        "body": body,
        "more_body": False,
    })


# ---------------------------------------------------------------------------
# Shared-secret authentication
# ---------------------------------------------------------------------------


class SharedSecretMiddleware:
    """Validates a shared secret on every non-public request.

    In development mode (AI_ENGINE_SHARED_SECRET not set and
    PLATFORM_ENV == "development"), generates a random per-process
    secret and logs a warning.  In all other environments, the
    AI_ENGINE_SHARED_SECRET env var is mandatory -- the middleware
    raises RuntimeError at init time if it is missing.
    """

    def __init__(self, app: ASGIApp, *, platform_env: str = "development") -> None:
        self.app = app
        raw_secret = os.environ.get("AI_ENGINE_SHARED_SECRET", "")
        if raw_secret:
            self._secret = raw_secret
        elif platform_env.lower() in ("development", "dev", "local"):
            self._secret = f"dev-{secrets.token_hex(32)}"
            logger.warning(
                "AI_ENGINE_SHARED_SECRET not set -- generated random per-process "
                "dev secret. Cross-service calls will fail unless the API uses "
                "the same secret."
            )
        else:
            raise RuntimeError(
                f"AI_ENGINE_SHARED_SECRET is required in {platform_env} mode. "
                "Refusing to start AI engine without authentication."
            )

        # Optional previous secret for zero-downtime rotation (BL-049).
        # During rotation: set AI_ENGINE_SHARED_SECRET to the new secret and
        # AI_ENGINE_SHARED_SECRET_PREVIOUS to the old secret.  Both values are
        # accepted until all callers have been updated to the new secret, then
        # AI_ENGINE_SHARED_SECRET_PREVIOUS can be removed.
        self._previous_secret = os.environ.get("AI_ENGINE_SHARED_SECRET_PREVIOUS", "")

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        # Allow health checks without auth.
        if scope["path"] in _PUBLIC_PATHS:
            await self.app(scope, receive, send)
            return

        auth_header = _get_header(scope, b"authorization").decode("latin-1")
        if not auth_header.startswith("Bearer "):
            await _send_json_error(
                send, 401,
                "Missing or malformed Authorization header. Expected: Bearer <token>",
            )
            return

        token = auth_header[7:]  # Strip "Bearer " prefix

        # Accept the current secret or the previous secret (rotation window).
        valid = secrets.compare_digest(token, self._secret)
        if not valid and self._previous_secret:
            valid = secrets.compare_digest(token, self._previous_secret)
            if valid:
                client = scope.get("client")
                client_host = client[0] if client else "unknown"
                logger.info(
                    "AI engine auth: request from %s accepted with previous shared secret "
                    "-- update caller to use the new AI_ENGINE_SHARED_SECRET.",
                    client_host,
                )

        if not valid:
            client = scope.get("client")
            client_host = client[0] if client else "unknown"
            logger.warning(
                "AI engine auth failed: invalid shared secret from %s",
                client_host,
            )
            await _send_json_error(send, 401, "Invalid shared secret")
            return

        await self.app(scope, receive, send)


# ---------------------------------------------------------------------------
# Token-bucket rate limiter
# ---------------------------------------------------------------------------


class _TenantBucket:
    """Token bucket rate limiter per tenant.

    Tracks a sliding window of request timestamps and rejects requests
    once the window fills.  Thread safety is not required because
    Starlette middlewares execute inside a single async event loop.
    """

    __slots__ = ("max_requests", "window", "requests")

    def __init__(self, max_requests: int = 60, window_seconds: float = 60.0) -> None:
        self.max_requests = max_requests
        self.window = window_seconds
        self.requests: list[float] = []

    def check(self) -> tuple[bool, int]:
        """Return ``(allowed, retry_after_seconds)``.

        If the request is allowed, appends the current timestamp and
        returns ``(True, 0)``.  If rejected, returns ``(False, N)``
        where *N* is the number of seconds the caller should wait.
        """
        now = time.monotonic()
        cutoff = now - self.window
        # Prune expired timestamps.
        self.requests = [t for t in self.requests if t > cutoff]
        if len(self.requests) >= self.max_requests:
            oldest_in_window = self.requests[0] if self.requests else now
            retry_after = int(oldest_in_window + self.window - now) + 1
            return False, max(retry_after, 1)
        self.requests.append(now)
        return True, 0


class AIRateLimitMiddleware:
    """Rate limits AI engine requests by tenant.

    Uses the ``X-Tenant-Id`` header (set by the API service) to
    identify tenants.  Requests without a tenant header are tracked
    under the ``__unknown__`` bucket.

    Default: 60 requests per minute per tenant.
    """

    def __init__(
        self,
        app: ASGIApp,
        *,
        max_requests: int = 60,
        window_seconds: float = 60.0,
    ) -> None:
        self.app = app
        self._max_requests = max_requests
        self._window = window_seconds
        self._buckets: dict[str, _TenantBucket] = defaultdict(
            lambda: _TenantBucket(self._max_requests, self._window),
        )

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        # Skip rate limiting for health checks.
        if scope["path"] in _PUBLIC_PATHS:
            await self.app(scope, receive, send)
            return

        raw_tenant_id = _get_header(scope, b"x-tenant-id").decode("latin-1") or "__unknown__"
        # BL-076: Sanitize tenant_id before logging to prevent log injection.
        # A header value containing \n or \r can inject fake log lines into SIEM.
        tenant_id = re.sub(r"[\r\n\t\0]", "_", raw_tenant_id)[:128]
        bucket = self._buckets[tenant_id]
        allowed, retry_after = bucket.check()

        if not allowed:
            logger.warning("AI engine rate limit exceeded for tenant %s", tenant_id)
            await _send_json_error(
                send, 429,
                f"Rate limit exceeded. Try again in {retry_after} seconds.",
                extra_headers=[(b"retry-after", str(retry_after).encode())],
            )
            return

        await self.app(scope, receive, send)


# ---------------------------------------------------------------------------
# Request body size guard
# ---------------------------------------------------------------------------


class RequestSizeLimitMiddleware:
    """Reject requests whose body exceeds a configurable limit.

    Two-layer guard:
    1. **Pre-read** — checks ``Content-Length`` header before any body
       is consumed (fast reject for well-behaved clients).
    2. **Streaming** — wraps the ASGI receive channel to count bytes as
       they arrive.  When the limit is exceeded the inner app's response
       is suppressed and a 413 is sent directly.

    Default limit: 1 MiB (1 048 576 bytes).
    """

    def __init__(self, app: ASGIApp, *, max_body_size: int = 1_048_576) -> None:
        self.app = app
        self._max_size = max_body_size

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        path = scope.get("path", "")

        # Layer 1: fast Content-Length check.
        content_length_raw = _get_header(scope, b"content-length")
        if content_length_raw:
            try:
                length = int(content_length_raw)
            except (ValueError, OverflowError):
                await _send_json_error(send, 400, "Invalid Content-Length header")
                return
            if length > self._max_size:
                logger.warning(
                    "Rejected request to %s: Content-Length %d exceeds limit %d",
                    path,
                    length,
                    self._max_size,
                )
                await _send_json_error(
                    send, 413,
                    f"Request body too large. Maximum: {self._max_size} bytes",
                )
                return

        # Layer 2: streaming byte counter for chunked requests.
        # When the limit is exceeded, the inner app's response is suppressed
        # and replaced with a 413.
        bytes_received = 0
        max_size = self._max_size
        exceeded = False
        response_started = False

        async def _counting_receive() -> dict[str, Any]:
            nonlocal bytes_received, exceeded
            message = await receive()
            if message.get("type") == "http.request":
                body = message.get("body", b"")
                bytes_received += len(body)
                if bytes_received > max_size:
                    exceeded = True
            return message

        async def _guarded_send(message: dict[str, Any]) -> None:
            nonlocal response_started
            if exceeded:
                # Suppress the inner app's response — we send 413 after it finishes.
                return
            if message.get("type") == "http.response.start":
                response_started = True
            await send(message)

        await self.app(scope, _counting_receive, _guarded_send)

        if exceeded:
            logger.warning(
                "Rejected chunked request to %s: streamed %d bytes exceeds limit %d",
                path,
                bytes_received,
                max_size,
            )
            if not response_started:
                await _send_json_error(
                    send, 413,
                    f"Request body too large. Maximum: {self._max_size} bytes",
                )

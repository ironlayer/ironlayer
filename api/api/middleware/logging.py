"""Structured request-logging middleware for the IronLayer API."""

from __future__ import annotations

import logging
import time
import uuid
from typing import Any

from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import Response

logger = logging.getLogger("api.access")

# Header names whose values must be masked in log output.
_SENSITIVE_HEADERS: frozenset[str] = frozenset({"authorization", "x-api-key", "cookie", "x-csrf-token"})
_MASK: str = "***"

_CORRELATION_HEADER: str = "X-Correlation-ID"


def _safe_headers(request: Request) -> dict[str, str]:
    """Return a copy of the request headers with sensitive values masked."""
    out: dict[str, str] = {}
    for key, value in request.headers.items():
        if key.lower() in _SENSITIVE_HEADERS:
            out[key] = _MASK
        else:
            out[key] = value
    return out


class RequestLoggingMiddleware(BaseHTTPMiddleware):
    """Log every request with method, path, status code, and duration.

    Each request is tagged with a ``correlation_id`` (taken from the
    incoming ``X-Correlation-ID`` header or generated as a UUID-4) and
    the authenticated ``tenant_id`` (if available from
    ``request.state``).  The correlation ID is also set as a response
    header for end-to-end tracing.

    Output is emitted as a structured JSON-compatible dictionary so that
    downstream log aggregators (Datadog, CloudWatch, etc.) can index
    individual fields without regex parsing.
    """

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        # Derive or generate a correlation ID for this request.
        correlation_id = request.headers.get(
            _CORRELATION_HEADER.lower(),
            request.headers.get(_CORRELATION_HEADER, ""),
        )
        if not correlation_id:
            correlation_id = str(uuid.uuid4())

        start = time.monotonic()
        response: Response | None = None
        try:
            response = await call_next(request)
            # Attach the correlation ID to the response for tracing.
            response.headers[_CORRELATION_HEADER] = correlation_id
            return response
        finally:
            duration_ms = round((time.monotonic() - start) * 1000, 2)
            status_code = response.status_code if response is not None else 500

            # Extract tenant_id from request.state if the auth middleware
            # has already populated it; fall back to "anonymous".
            tenant_id = getattr(request.state, "tenant_id", "anonymous")

            # Include trace context if the TraceContextMiddleware populated it.
            trace_id = getattr(request.state, "trace_id", "")
            span_id = getattr(request.state, "span_id", "")

            log_payload: dict[str, Any] = {
                "method": request.method,
                "path": request.url.path,
                "query": str(request.url.query) if request.url.query else None,
                "status_code": status_code,
                "duration_ms": duration_ms,
                "client": request.client.host if request.client else None,
                "correlation_id": correlation_id,
                "tenant_id": tenant_id,
                "identity_kind": getattr(request.state, "identity_kind", "user"),
                "trace_id": trace_id,
                "span_id": span_id,
                "headers": _safe_headers(request),
            }
            if status_code >= 500:
                logger.error("request completed", extra={"request": log_payload})
            elif status_code >= 400:
                logger.warning("request completed", extra={"request": log_payload})
            else:
                logger.info("request completed", extra={"request": log_payload})

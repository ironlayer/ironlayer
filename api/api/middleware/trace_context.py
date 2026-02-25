"""W3C Trace Context middleware for distributed tracing readiness.

Parses incoming ``traceparent`` headers (W3C format) and propagates
``trace_id`` / ``span_id`` through the request lifecycle via
``contextvars``.  If no header is present, fresh identifiers are generated.

All responses include an ``X-Trace-ID`` header so that consumers can
correlate requests to internal logs without needing full OTel tooling.

Header format (W3C)::

    traceparent: {version}-{trace_id}-{parent_span_id}-{flags}
    Example:     00-4bf92f3577b16e8153e785e29fc5f28c-d75597dee50b0cac-01

See https://www.w3.org/TR/trace-context/ for the full specification.
"""

from __future__ import annotations

import contextvars
import logging
import os
import re

from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import Response

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Context variables (visible to all code in the same async task)
# ---------------------------------------------------------------------------

_trace_id_var: contextvars.ContextVar[str] = contextvars.ContextVar("trace_id", default="")
_span_id_var: contextvars.ContextVar[str] = contextvars.ContextVar("span_id", default="")
_trace_flags_var: contextvars.ContextVar[str] = contextvars.ContextVar("trace_flags", default="00")

# ---------------------------------------------------------------------------
# W3C traceparent regex
# ---------------------------------------------------------------------------

_TRACEPARENT_RE = re.compile(r"^([0-9a-f]{2})-([0-9a-f]{32})-([0-9a-f]{16})-([0-9a-f]{2})$")


# ---------------------------------------------------------------------------
# ID generation helpers
# ---------------------------------------------------------------------------


def _generate_trace_id() -> str:
    """Generate a 32-hex-character trace ID."""
    return os.urandom(16).hex()


def _generate_span_id() -> str:
    """Generate a 16-hex-character span ID."""
    return os.urandom(8).hex()


# ---------------------------------------------------------------------------
# Public accessors
# ---------------------------------------------------------------------------


def get_trace_id() -> str:
    """Return the current trace ID (or empty string outside a request)."""
    return _trace_id_var.get()


def get_span_id() -> str:
    """Return the current span ID (or empty string outside a request)."""
    return _span_id_var.get()


def get_trace_flags() -> str:
    """Return the current trace flags (or ``'00'`` outside a request)."""
    return _trace_flags_var.get()


def get_traceparent() -> str:
    """Reconstruct a W3C ``traceparent`` header value from context vars.

    Returns an empty string if no trace context is active.
    """
    trace_id = get_trace_id()
    span_id = get_span_id()
    if not trace_id or not span_id:
        return ""
    return f"00-{trace_id}-{span_id}-{get_trace_flags()}"


def get_trace_context(request: Request) -> dict[str, str]:
    """Convenience: extract trace context from ``request.state``.

    Falls back to context vars if ``request.state`` is not populated.
    """
    trace_id = getattr(request.state, "trace_id", None) or get_trace_id()
    span_id = getattr(request.state, "span_id", None) or get_span_id()
    return {"trace_id": trace_id, "span_id": span_id}


# ---------------------------------------------------------------------------
# Middleware
# ---------------------------------------------------------------------------


class TraceContextMiddleware(BaseHTTPMiddleware):
    """Parse or generate W3C trace context and inject into request lifecycle.

    Behaviour
    ---------
    1. If the incoming request contains a valid ``traceparent`` header, the
       trace ID and parent span ID are extracted.  A **new** span ID is
       generated for this service's span.
    2. If no valid header is present, both trace ID and span ID are freshly
       generated.
    3. ``request.state.trace_id`` and ``request.state.span_id`` are set for
       downstream handlers.
    4. ``X-Trace-ID`` is added to the response for client-side correlation.
    """

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        traceparent = request.headers.get("traceparent", "")
        trace_id, parent_span_id, flags = self._parse_traceparent(traceparent)

        # Always generate a new span_id for this service's span.
        span_id = _generate_span_id()

        if not trace_id:
            trace_id = _generate_trace_id()
            flags = "00"

        # Store on context vars (available to all coroutines in this task).
        _trace_id_var.set(trace_id)
        _span_id_var.set(span_id)
        _trace_flags_var.set(flags)

        # Store on request.state for handlers that receive the Request.
        request.state.trace_id = trace_id
        request.state.span_id = span_id
        request.state.parent_span_id = parent_span_id or ""

        response = await call_next(request)

        # Always include trace ID in response for client-side correlation.
        response.headers["X-Trace-ID"] = trace_id

        return response

    @staticmethod
    def _parse_traceparent(header: str) -> tuple[str, str, str]:
        """Parse a W3C traceparent header.

        Returns ``(trace_id, parent_span_id, flags)`` or ``("", "", "")``
        if the header is missing or invalid.
        """
        if not header:
            return ("", "", "")

        match = _TRACEPARENT_RE.match(header.strip().lower())
        if not match:
            logger.debug("Invalid traceparent header: %s", header)
            return ("", "", "")

        version, trace_id, parent_span_id, flags = match.groups()

        # W3C spec: version 255 (ff) is invalid.
        if version == "ff":
            logger.debug("Traceparent version ff is invalid")
            return ("", "", "")

        # All-zero trace_id or span_id is invalid.
        if trace_id == "0" * 32 or parent_span_id == "0" * 16:
            logger.debug("Traceparent has all-zero trace_id or span_id")
            return ("", "", "")

        return (trace_id, parent_span_id, flags)


# ---------------------------------------------------------------------------
# Logging filter
# ---------------------------------------------------------------------------


class TraceLoggingFilter(logging.Filter):
    """Inject ``trace_id`` and ``span_id`` into every log record.

    Attach to a logger or handler so that formatters can include
    ``%(trace_id)s`` and ``%(span_id)s`` in their format strings (or
    the JSON formatter can pull them from the record).
    """

    def filter(self, record: logging.LogRecord) -> bool:
        record.trace_id = _trace_id_var.get()  # type: ignore[attr-defined]
        record.span_id = _span_id_var.get()  # type: ignore[attr-defined]
        return True

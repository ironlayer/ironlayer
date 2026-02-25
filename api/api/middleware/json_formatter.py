"""JSON log formatter for SIEM integration.

Emits each log record as a single-line JSON object containing
structured fields that downstream aggregators (Datadog, Splunk,
CloudWatch Logs, ELK, etc.) can index without regex parsing.

Activate by setting ``API_STRUCTURED_LOGGING=true``.  When enabled
the application replaces the default text-based log handlers with a
``StreamHandler`` using this formatter.

Output schema per line::

    {
        "timestamp": "2025-05-15T12:34:56.789012+00:00",
        "level": "INFO",
        "logger": "api.access",
        "message": "request completed",
        "request": { ... },       // present when emitted by RequestLoggingMiddleware
        "exc_info": "Traceback ..."  // present only on exceptions
    }
"""

from __future__ import annotations

import json
import logging
import traceback
from datetime import UTC, datetime
from typing import Any


class JSONFormatter(logging.Formatter):
    """Format log records as single-line JSON for SIEM ingestion."""

    def format(self, record: logging.LogRecord) -> str:
        """Render *record* as a single JSON line."""
        payload: dict[str, Any] = {
            "timestamp": datetime.fromtimestamp(record.created, tz=UTC).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }

        # Include W3C trace context if injected by TraceLoggingFilter.
        trace_id = getattr(record, "trace_id", None)
        if trace_id:
            payload["trace_id"] = trace_id
        span_id = getattr(record, "span_id", None)
        if span_id:
            payload["span_id"] = span_id

        # Include structured request context emitted by
        # RequestLoggingMiddleware via ``extra={"request": ...}``.
        request_data = getattr(record, "request", None)
        if request_data is not None:
            payload["request"] = request_data

        # Include exception information when present.
        if record.exc_info and record.exc_info[0] is not None:
            payload["exc_info"] = "".join(traceback.format_exception(*record.exc_info))

        return json.dumps(payload, default=str, ensure_ascii=False)

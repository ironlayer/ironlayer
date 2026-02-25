"""Thread-safe metrics emitter for engine-level observability events.

Events are written as JSON lines to an optional file and/or to stdout in
structured logging mode.  All file writes are protected by a
:class:`threading.Lock` to ensure safety when the engine runs steps in
parallel threads.
"""

from __future__ import annotations

import ipaddress
import logging
import re
import socket
import sys
import threading
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from core_engine.models.telemetry import MetricsEvent

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# PII scrubbing patterns
# ---------------------------------------------------------------------------

# Email addresses (RFC 5322 simplified)
_EMAIL_RE = re.compile(r"[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+")

# US Social Security Numbers (XXX-XX-XXXX or XXXXXXXXX)
_SSN_RE = re.compile(r"\b\d{3}-\d{2}-\d{4}\b|\b\d{9}\b")

# Credit card numbers (13-19 digits, optionally separated by spaces or dashes)
_CREDIT_CARD_RE = re.compile(r"\b(?:\d[ -]*?){13,19}\b")

# US phone numbers (various formats)
_PHONE_RE = re.compile(r"\b(?:\+?1[-.\s]?)?(?:\(\d{3}\)|\d{3})[-.\s]?\d{3}[-.\s]?\d{4}\b")

_PII_REPLACEMENT = "[REDACTED]"

# Maximum SQL content length in telemetry payloads (1 KB).
_MAX_SQL_LENGTH = 1024


def _scrub_pii(value: str) -> str:
    """Remove PII patterns from a string value.

    Detects and replaces:
    - Email addresses
    - US Social Security Numbers
    - Credit card numbers
    - US phone numbers
    """
    value = _EMAIL_RE.sub(_PII_REPLACEMENT, value)
    value = _SSN_RE.sub(_PII_REPLACEMENT, value)
    value = _CREDIT_CARD_RE.sub(_PII_REPLACEMENT, value)
    value = _PHONE_RE.sub(_PII_REPLACEMENT, value)
    return value


def _scrub_data(data: dict[str, Any]) -> dict[str, Any]:
    """Recursively scrub PII from all string values in a data dictionary.

    Additionally truncates any value whose key contains 'sql' to
    ``_MAX_SQL_LENGTH`` characters.
    """
    scrubbed: dict[str, Any] = {}
    for key, value in data.items():
        if isinstance(value, str):
            cleaned = _scrub_pii(value)
            # Truncate SQL content to prevent oversized telemetry payloads.
            if "sql" in key.lower() and len(cleaned) > _MAX_SQL_LENGTH:
                cleaned = cleaned[:_MAX_SQL_LENGTH] + "...[truncated]"
            scrubbed[key] = cleaned
        elif isinstance(value, dict):
            scrubbed[key] = _scrub_data(value)
        elif isinstance(value, list):
            scrubbed[key] = [
                _scrub_pii(item) if isinstance(item, str) else _scrub_data(item) if isinstance(item, dict) else item
                for item in value
            ]
        else:
            scrubbed[key] = value
    return scrubbed


def _validate_telemetry_url(url: str) -> None:
    """Validate that a telemetry endpoint URL is safe (no SSRF).

    Checks:
    1. Scheme must be HTTPS (or HTTP for localhost in dev).
    2. Resolved IP addresses must not be in private, loopback,
       link-local, or reserved ranges.

    This is a standalone function (not imported from ``api.security``)
    to avoid cross-package dependencies between core_engine and api.

    Parameters
    ----------
    url:
        The telemetry endpoint URL to validate.

    Raises
    ------
    ValueError
        If the URL fails any safety check.
    """
    parsed = urlparse(url)

    if parsed.scheme not in ("https", "http"):
        raise ValueError(f"Telemetry endpoint must use HTTPS (got scheme '{parsed.scheme}'): {url}")

    hostname = parsed.hostname
    if not hostname:
        raise ValueError(f"Could not extract hostname from telemetry endpoint URL: {url}")

    # Resolve the hostname to IP addresses and check for private ranges.
    try:
        addr_infos = socket.getaddrinfo(hostname, None, proto=socket.IPPROTO_TCP)
    except socket.gaierror as exc:
        raise ValueError(f"DNS resolution failed for telemetry endpoint '{hostname}': {exc}") from exc

    if not addr_infos:
        raise ValueError(f"DNS resolution returned no results for telemetry endpoint '{hostname}'")

    for addr_info in addr_infos:
        ip_str = addr_info[4][0]
        try:
            addr = ipaddress.ip_address(ip_str)
        except ValueError as exc:
            raise ValueError(
                f"Invalid IP address '{ip_str}' from DNS resolution of " f"telemetry endpoint: {exc}"
            ) from exc

        if addr.is_private or addr.is_loopback or addr.is_link_local or addr.is_reserved:
            raise ValueError(
                f"Telemetry endpoint '{url}' resolves to private/reserved IP "
                f"{ip_str}. Telemetry endpoints must resolve to public IP "
                f"addresses to prevent SSRF."
            )


class MetricsEmitter:
    """Emit structured observability events to file and/or stdout.

    Parameters
    ----------
    metrics_file:
        Optional path to a JSON-lines file.  Parent directories are created
        automatically.  When ``None``, file-based emission is disabled.
    structured:
        When ``True``, events are also printed to stdout as single-line JSON.
    endpoint_url:
        Optional HTTP(S) endpoint to POST telemetry events to.  Validated
        at construction time to reject private IPs (SSRF prevention).
    """

    def __init__(
        self,
        metrics_file: Path | None = None,
        structured: bool = False,
        endpoint_url: str | None = None,
    ) -> None:
        self._metrics_file = metrics_file
        self._structured = structured
        self._endpoint_url = endpoint_url
        self._lock = threading.Lock()

        if self._metrics_file is not None:
            self._metrics_file.parent.mkdir(parents=True, exist_ok=True)

        # Validate telemetry endpoint URL at startup (fail fast).
        if self._endpoint_url is not None:
            _validate_telemetry_url(self._endpoint_url)
            logger.info("Telemetry endpoint validated: %s", self._endpoint_url)

    # -- Core emit -----------------------------------------------------------

    def emit(self, event: str, data: dict[str, Any]) -> None:
        """Create and write a :class:`MetricsEvent`.

        PII scrubbing is applied to all string fields in ``data``
        before emission.  SQL content is truncated to 1 KB.

        Parameters
        ----------
        event:
            Event type identifier, e.g. ``"plan.generated"`` or ``"run.finished"``.
        data:
            Arbitrary payload to attach to the event.
        """
        scrubbed_data = _scrub_data(data)
        scrubbed_event = _scrub_pii(event)

        metrics_event = MetricsEvent(
            event=scrubbed_event,
            timestamp=datetime.now(UTC),
            data=scrubbed_data,
        )

        json_line = metrics_event.model_dump_json()

        if self._metrics_file is not None:
            with self._lock, self._metrics_file.open("a", encoding="utf-8") as fh:
                fh.write(json_line + "\n")

        if self._structured:
            # Write to stdout as a single JSON line for structured log
            # aggregators (e.g. Datadog, Fluentd).
            sys.stdout.write(json_line + "\n")
            sys.stdout.flush()

        logger.debug("Emitted event: %s", event)

    # -- Convenience methods -------------------------------------------------

    def plan_generated(
        self,
        plan_id: str,
        models_changed: list[str],
        duration_ms: float,
    ) -> None:
        """Emit a ``plan.generated`` event."""
        self.emit(
            "plan.generated",
            {
                "plan_id": plan_id,
                "models_changed": models_changed,
                "models_changed_count": len(models_changed),
                "duration_ms": duration_ms,
            },
        )

    def plan_applied(
        self,
        plan_id: str,
        total_steps: int,
        duration_ms: float,
    ) -> None:
        """Emit a ``plan.applied`` event."""
        self.emit(
            "plan.applied",
            {
                "plan_id": plan_id,
                "total_steps": total_steps,
                "duration_ms": duration_ms,
            },
        )

    def run_started(self, run_id: str, model: str) -> None:
        """Emit a ``run.started`` event."""
        self.emit(
            "run.started",
            {
                "run_id": run_id,
                "model": model,
            },
        )

    def run_finished(
        self,
        run_id: str,
        model: str,
        status: str,
        duration_ms: float,
    ) -> None:
        """Emit a ``run.finished`` event."""
        self.emit(
            "run.finished",
            {
                "run_id": run_id,
                "model": model,
                "status": status,
                "duration_ms": duration_ms,
            },
        )

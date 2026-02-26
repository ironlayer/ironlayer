"""Privacy-by-design utilities for telemetry and logging.

Provides PII detection and scrubbing for all telemetry data before it
leaves the system boundary.  Implements:

1. **PII detection**: Regex-based scanning for common PII patterns
   (emails, phone numbers, SSNs, credit cards, IP addresses).
2. **PII scrubbing**: Replace detected PII with redacted placeholders.
3. **Anonymisation**: One-way hashing of identifiers for cross-customer
   aggregation (opt-in only).
4. **Telemetry consent**: Respect opt-in/opt-out flags per tenant.

All scrubbing is applied before telemetry is persisted or transmitted.
"""

from __future__ import annotations

import hashlib
import logging
import re
from enum import Enum
from typing import Any

logger = logging.getLogger(__name__)


class TelemetryConsent(str, Enum):
    """Telemetry sharing consent levels."""

    NONE = "none"  # No telemetry collected
    LOCAL_ONLY = "local_only"  # Telemetry stored locally, never shared
    ANONYMIZED = "anonymized"  # Anonymized aggregates shared
    FULL = "full"  # Full telemetry shared (with PII scrubbing)


# -- PII detection patterns --------------------------------------------------

_PII_PATTERNS: list[tuple[str, re.Pattern[str], str]] = [
    (
        "email",
        re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b"),
        "[REDACTED_EMAIL]",
    ),
    (
        "phone_us",
        re.compile(r"\b(?:\+?1[-.\s]?)?\(?\d{3}\)?[-.\s]?\d{3}[-.\s]?\d{4}\b"),
        "[REDACTED_PHONE]",
    ),
    (
        "ssn",
        re.compile(r"\b\d{3}-\d{2}-\d{4}\b"),
        "[REDACTED_SSN]",
    ),
    (
        "credit_card",
        re.compile(r"\b(?:4\d{3}|5[1-5]\d{2}|3[47]\d{2}|6(?:011|5\d{2}))" r"[-\s]?\d{4}[-\s]?\d{4}[-\s]?\d{1,4}\b"),
        "[REDACTED_CC]",
    ),
    (
        "ipv4",
        re.compile(r"\b(?:\d{1,3}\.){3}\d{1,3}\b"),
        "[REDACTED_IP]",
    ),
    (
        "ipv6",
        re.compile(r"\b(?:[0-9a-fA-F]{1,4}:){7}[0-9a-fA-F]{1,4}\b"),
        "[REDACTED_IP]",
    ),
    (
        "databricks_token",
        re.compile(r"\bdapi[a-f0-9\-_]{20,}\b", re.IGNORECASE),
        "[REDACTED_TOKEN]",
    ),
    (
        "generic_secret",
        re.compile(r"(?i)\b(?:password|secret|token|api_key|apikey)\s*[=:]\s*(?!\[REDACTED)\S+"),
        "[REDACTED_SECRET]",
    ),
]

# SQL patterns that might contain PII in WHERE clauses or values
_SQL_PII_PATTERNS: list[tuple[str, re.Pattern[str], str]] = [
    (
        "sql_email_literal",
        re.compile(r"'[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}'"),
        "'[REDACTED_EMAIL]'",
    ),
    (
        "sql_name_literal",
        re.compile(r"(?i)(?:first_name|last_name|full_name|username)\s*=\s*'[^']+'"),
        "[REDACTED_NAME_FILTER]",
    ),
]


def scrub_pii(text: str) -> str:
    """Remove all detected PII from a text string.

    Parameters
    ----------
    text:
        Input text that may contain PII.

    Returns
    -------
    str
        Text with all detected PII replaced by redaction placeholders.
    """
    result = text
    for _name, pattern, replacement in _PII_PATTERNS:
        result = pattern.sub(replacement, result)
    return result


def scrub_sql_pii(sql: str) -> str:
    """Remove PII from SQL strings, including string literals.

    Parameters
    ----------
    sql:
        SQL text that may contain PII in WHERE clauses, INSERT values, etc.

    Returns
    -------
    str
        SQL with PII-bearing literals redacted.
    """
    result = sql
    for _name, pattern, replacement in _SQL_PII_PATTERNS:
        result = pattern.sub(replacement, result)
    # Also apply general PII scrubbing
    result = scrub_pii(result)
    return result


def scrub_dict(data: dict[str, Any], *, deep: bool = True) -> dict[str, Any]:
    """Recursively scrub PII from all string values in a dictionary.

    Parameters
    ----------
    data:
        Dictionary to scrub.
    deep:
        Whether to recurse into nested dicts and lists.

    Returns
    -------
    dict
        A new dictionary with PII scrubbed from all string values.
    """
    result: dict[str, Any] = {}
    for key, value in data.items():
        if isinstance(value, str):
            result[key] = scrub_pii(value)
        elif deep and isinstance(value, dict):
            result[key] = scrub_dict(value, deep=True)
        elif deep and isinstance(value, list):
            result[key] = [
                (
                    scrub_dict(item, deep=True)
                    if isinstance(item, dict)
                    else scrub_pii(item) if isinstance(item, str) else item
                )
                for item in value
            ]
        else:
            result[key] = value
    return result


def anonymize_identifier(identifier: str, salt: str = "") -> str:
    """One-way hash an identifier for anonymised aggregation.

    Uses SHA-256 with a salt.  The result is irreversible.

    Parameters
    ----------
    identifier:
        The identifier to anonymize (tenant_id, model_name, etc.).
    salt:
        Salt to prevent rainbow table attacks.  An empty salt is accepted
        for backward compatibility but logs a warning.

    Returns
    -------
    str
        A 16-character hex digest (truncated for compactness).
    """
    if not salt:
        logger.warning(
            "anonymize_identifier called without a salt — hashes may be " "vulnerable to rainbow table attacks"
        )
    hasher = hashlib.sha256()
    hasher.update(salt.encode("utf-8"))
    hasher.update(identifier.encode("utf-8"))
    return hasher.hexdigest()[:16]


def check_consent(consent_level: TelemetryConsent, action: str) -> bool:
    """Check whether the given consent level permits a telemetry action.

    Parameters
    ----------
    consent_level:
        The tenant's current consent setting.
    action:
        One of: ``"collect"``, ``"store"``, ``"share"``, ``"aggregate"``.

    Returns
    -------
    bool
        True if the action is permitted.
    """
    permissions: dict[TelemetryConsent, set[str]] = {
        TelemetryConsent.NONE: set(),
        TelemetryConsent.LOCAL_ONLY: {"collect", "store"},
        TelemetryConsent.ANONYMIZED: {"collect", "store", "aggregate"},
        TelemetryConsent.FULL: {"collect", "store", "share", "aggregate"},
    }
    return action in permissions.get(consent_level, set())


class TelemetryScrubber:
    """Scrubbing pipeline that respects per-tenant consent.

    Parameters
    ----------
    consent:
        The tenant's telemetry consent level.
    anonymization_salt:
        Salt for identifier anonymization.
    """

    def __init__(
        self,
        consent: TelemetryConsent = TelemetryConsent.LOCAL_ONLY,
        anonymization_salt: str = "",
    ) -> None:
        self._consent = consent
        self._salt = anonymization_salt

    @property
    def consent(self) -> TelemetryConsent:
        return self._consent

    def should_collect(self) -> bool:
        """Return True if telemetry collection is permitted."""
        return check_consent(self._consent, "collect")

    def should_share(self) -> bool:
        """Return True if telemetry sharing is permitted."""
        return check_consent(self._consent, "share")

    def process_telemetry(self, data: dict[str, Any]) -> dict[str, Any] | None:
        """Process telemetry data according to consent level.

        Returns None if collection is not permitted.
        Scrubs PII from all data.
        Anonymizes identifiers if consent is ANONYMIZED.
        """
        if not self.should_collect():
            return None

        # Always scrub PII regardless of consent level
        scrubbed = scrub_dict(data)

        # Anonymize identifiers for aggregate-only consent
        if self._consent == TelemetryConsent.ANONYMIZED:
            if "model_name" in scrubbed:
                scrubbed["model_name"] = anonymize_identifier(str(scrubbed["model_name"]), self._salt)
            if "tenant_id" in scrubbed:
                scrubbed["tenant_id"] = anonymize_identifier(str(scrubbed["tenant_id"]), self._salt)
            if "run_id" in scrubbed:
                scrubbed["run_id"] = anonymize_identifier(str(scrubbed["run_id"]), self._salt)

        return scrubbed

    def process_sql_for_logging(self, sql: str) -> str:
        """Scrub SQL before writing to logs or telemetry."""
        return scrub_sql_pii(sql)

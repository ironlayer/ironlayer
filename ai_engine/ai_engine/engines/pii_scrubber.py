"""PII scrubbing for LLM inputs -- prevents sensitive data leakage to external APIs.

Self-contained within the ``ai_engine`` package so that it does not import
from ``core_engine``.  The patterns mirror those in
``core_engine.telemetry.privacy`` but are purpose-built for the LLM
submission path:

* General PII (emails, phones, SSNs, credit cards) is replaced with
  category-specific placeholders.
* SQL string literals are replaced with ``<LITERAL>`` to prevent leaking
  data values while preserving query structure.
* Large numeric literals (>6 digits) that look like IDs are replaced with
  ``<ID>``.
* Databricks personal access tokens (``dapi...``) and generic secret
  key-value patterns are redacted.

All functions are pure and side-effect-free; logging is handled by the
calling code in :mod:`ai_engine.engines.llm_client`.
"""

from __future__ import annotations

import re

# ---------------------------------------------------------------------------
# General PII patterns
# ---------------------------------------------------------------------------

_EMAIL_RE = re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b")
_PHONE_RE = re.compile(r"\b(?:\+?1[-.\s]?)?\(?\d{3}\)?[-.\s]?\d{3}[-.\s]?\d{4}\b")
_SSN_RE = re.compile(r"\b\d{3}-\d{2}-\d{4}\b")
_CC_RE = re.compile(r"\b(?:\d[ -]*?){13,19}\b")
_DATABRICKS_TOKEN_RE = re.compile(r"\bdapi[a-f0-9]{32}\b", re.IGNORECASE)
_GENERIC_SECRET_RE = re.compile(r"(?i)\b(?:password|secret|token|api_key|apikey|api[-_]?secret)\s*[=:]\s*\S+")

_GENERAL_PII_PATTERNS: list[tuple[re.Pattern[str], str]] = [
    (_EMAIL_RE, "<EMAIL>"),
    (_SSN_RE, "<SSN>"),
    (_CC_RE, "<CC>"),
    (_PHONE_RE, "<PHONE>"),
    (_DATABRICKS_TOKEN_RE, "<TOKEN>"),
    (_GENERIC_SECRET_RE, "<SECRET>"),
]

# ---------------------------------------------------------------------------
# SQL-specific patterns
# ---------------------------------------------------------------------------

# Matches single-quoted string literals, handling escaped quotes ('').
_SQL_STRING_LITERAL_RE = re.compile(r"'(?:[^']|'')*'")
# Matches numeric literals with > 6 digits that are likely IDs.
_SQL_LARGE_NUMERIC_RE = re.compile(r"\b\d{7,}\b")


def scrub_for_llm(text: str) -> str:
    """Remove PII, string literals, and sensitive identifiers from text before LLM submission.

    Applies a sequence of regex substitutions to strip:

    * Email addresses
    * Phone numbers (US format)
    * Social Security Numbers
    * Credit card numbers
    * Databricks personal access tokens
    * Generic secret patterns (``password=..., key=..., token=...``)

    Parameters
    ----------
    text:
        Arbitrary text that may contain PII.

    Returns
    -------
    str
        The scrubbed text with PII replaced by category placeholders.
    """
    result = text
    for pattern, replacement in _GENERAL_PII_PATTERNS:
        result = pattern.sub(replacement, result)
    return result


def scrub_sql_for_llm(sql: str) -> str:
    """Scrub SQL specifically -- replaces string literals and large numeric IDs.

    Preserves SQL keywords, table names, column names, and overall query
    structure while replacing:

    * All single-quoted string literals with ``<LITERAL>``
    * Numeric literals exceeding 6 digits (likely row IDs) with ``<ID>``

    General PII scrubbing is applied afterwards to catch any remaining
    sensitive patterns (emails in comments, tokens in CTEs, etc.).

    Parameters
    ----------
    sql:
        A SQL statement that may contain PII-bearing literals.

    Returns
    -------
    str
        The scrubbed SQL with sensitive values replaced.
    """
    result = _SQL_STRING_LITERAL_RE.sub("<LITERAL>", sql)
    result = _SQL_LARGE_NUMERIC_RE.sub("<ID>", result)
    result = scrub_for_llm(result)
    return result


def contains_pii(text: str) -> bool:
    """Return True if *text* matches any known PII pattern.

    Useful for deciding whether to emit a DEBUG log line when scrubbing
    is applied.  Does **not** log the matched content itself.

    Parameters
    ----------
    text:
        The text to scan.

    Returns
    -------
    bool
        True if any PII pattern matches.
    """
    for pattern, _replacement in _GENERAL_PII_PATTERNS:
        if pattern.search(text):
            return True
    return _SQL_STRING_LITERAL_RE.search(text) is not None

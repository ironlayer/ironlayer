"""Versioned SQL canonicalisation and deterministic hashing.

The normaliser transpiles SQL through SQLGlot to produce a canonical form
with deterministic keyword casing, whitespace, and formatting.  Every
canonicalisation rule-set is versioned so that hash stability can be
guaranteed across releases.

**Canonicalisation rules (v1)**:
1. Parse and regenerate SQL via ``sqlglot.transpile`` (Databricks dialect).
2. Normalise all whitespace to single spaces; strip leading/trailing.
3. Uppercase all SQL keywords (handled by SQLGlot's generator).
4. Fully qualify table references where possible.
5. Order CTE definitions alphabetically by name when safe (no forward refs).
6. Strip all comments.

The canonicaliser version is embedded in every hash so that if rules change
in a future version, hashes are naturally incompatible and plans are
regenerated.
"""

from __future__ import annotations

import hashlib
import logging
import re
from enum import Enum

from core_engine.sql_toolkit import Dialect, SqlNormalizationError, get_sql_toolkit
from core_engine.telemetry.profiling import profile_operation

logger = logging.getLogger(__name__)


class NormalizationError(Exception):
    """Raised when SQL cannot be canonicalised to a deterministic form.

    Callers that need graceful degradation should catch this exception
    and handle the non-canonical SQL explicitly (e.g. logging a warning
    and skipping the model).
    """


class CanonicalizerVersion(str, Enum):
    """Versioned canonicalisation rule-sets.

    Adding a new version here and updating ``CURRENT_VERSION`` will
    automatically invalidate all cached hashes, forcing plan regeneration.
    """

    V1 = "v1"


CURRENT_VERSION: CanonicalizerVersion = CanonicalizerVersion.V1

# Regex to strip SQL comments (both line and block)
_LINE_COMMENT_RE = re.compile(r"--[^\n]*")
_BLOCK_COMMENT_RE = re.compile(r"/\*.*?\*/", re.DOTALL)
_MULTI_SPACE_RE = re.compile(r"\s+")


@profile_operation("sql.normalize")
def normalize_sql(sql: str, *, version: CanonicalizerVersion | None = None) -> str:
    """Return a canonical representation of *sql* under the given rule-set version.

    Parameters
    ----------
    sql:
        Raw SQL text to normalise.
    version:
        Canonicalisation version to use.  Defaults to ``CURRENT_VERSION``.

    Returns
    -------
    str
        The normalised SQL string.
    """
    if version is None:
        version = CURRENT_VERSION

    if version == CanonicalizerVersion.V1:
        return _normalize_v1(sql)

    # Defensive fallback for unknown versions.
    logger.warning("Unknown canonicalizer version %s; falling back to V1", version)
    return _normalize_v1(sql)


def _normalize_v1(sql: str) -> str:
    """Canonicalisation rule-set V1.

    Delegates to the SQL toolkit normaliser which handles:
    1. Comment stripping (line and block)
    2. Parse and regenerate via SQLGlot for canonical form
    3. CTE reordering (alphabetical when no forward references)
    4. Keyword uppercasing and whitespace normalisation
    """
    # Fast path: empty or whitespace-only input.
    cleaned = _LINE_COMMENT_RE.sub("", sql)
    cleaned = _BLOCK_COMMENT_RE.sub("", cleaned)
    cleaned = cleaned.strip()

    if not cleaned:
        return ""

    tk = get_sql_toolkit()
    try:
        result = tk.normalizer.normalize(sql, Dialect.DATABRICKS, canonicalization_version="v1")
        if result.normalized_sql:
            return result.normalized_sql
        raise NormalizationError(f"Failed to canonicalize SQL: {cleaned[:200]}")
    except SqlNormalizationError as exc:
        raise NormalizationError(str(exc)) from exc


@profile_operation("sql.hash")
def compute_canonical_hash(
    sql: str,
    *,
    version: CanonicalizerVersion | None = None,
    metadata: dict[str, str] | None = None,
) -> str:
    """Return the SHA-256 hex digest of the versioned canonical SQL + metadata.

    The hash incorporates:
    1. The canonicaliser version string.
    2. The normalised SQL.
    3. Sorted normalised metadata key-value pairs (if provided).

    This ensures that:
    - Same SQL always produces the same hash.
    - A version bump invalidates all prior hashes.
    - Metadata changes (e.g. materialization) also invalidate the hash.

    Parameters
    ----------
    sql:
        Raw SQL text.  Normalisation is applied internally.
    version:
        Canonicalisation version.  Defaults to ``CURRENT_VERSION``.
    metadata:
        Optional metadata dictionary (e.g. kind, materialization, time_column)
        to include in the hash computation.

    Returns
    -------
    str
        A 64-character lowercase hexadecimal SHA-256 digest.
    """
    if version is None:
        version = CURRENT_VERSION

    normalised = normalize_sql(sql, version=version)

    hasher = hashlib.sha256()
    # Include version prefix so hashes are scoped to the rule-set.
    hasher.update(f"ironlayer-canon-{version.value}:".encode())
    hasher.update(normalised.encode("utf-8"))

    # Include sorted metadata if provided.
    if metadata:
        for key in sorted(metadata.keys()):
            value = metadata[key] or ""
            hasher.update(f"\n{key}={value}".encode())

    return hasher.hexdigest()


def get_canonicalizer_version() -> str:
    """Return the current canonicaliser version string.

    This is stored alongside model versions in the database so that
    hash comparisons across canonicaliser upgrades are handled correctly.
    """
    return CURRENT_VERSION.value

"""Feature extraction for the cost prediction model.

Converts raw telemetry records (dicts) into numpy arrays suitable for
scikit-learn.  Handles missing values with sensible defaults so that
callers do not need to pre-clean data.

The feature set includes:
  1. partition_count
  2. log1p_data_volume_bytes
  3. num_workers
  4. sql_complexity_score (AST node count, if SQL provided)
  5. join_count
  6. cte_count
  7. has_window_functions (0 or 1)
  8. distinct_table_count

Features 4–8 default to 0 if the SQL text is not provided in the
telemetry record, maintaining backward compatibility with records
that lack SQL metadata.
"""

from __future__ import annotations

import logging
import re

import numpy as np

logger = logging.getLogger(__name__)

# Feature count — update this when adding/removing features.
FEATURE_COUNT = 8

# Default values for missing fields
_DEFAULT_PARTITION_COUNT = 1
_DEFAULT_DATA_VOLUME_BYTES = 0
_DEFAULT_NUM_WORKERS = 1
_DEFAULT_RUNTIME_SECONDS = 300.0


def extract_features(
    telemetry_records: list[dict],
) -> tuple[np.ndarray, np.ndarray]:
    """Extract feature matrix and target vector from telemetry records.

    Each record is expected to contain some subset of:

    * ``partition_count`` (int)
    * ``data_volume_bytes`` (int)
    * ``num_workers`` (int)
    * ``sql`` (str, optional) — model SQL for complexity features
    * ``sql_complexity_score`` (int, optional) — pre-computed AST node count
    * ``join_count`` (int, optional)
    * ``cte_count`` (int, optional)
    * ``has_window_functions`` (bool, optional)
    * ``distinct_table_count`` (int, optional)
    * ``runtime_seconds`` (float) — **target**

    Missing values are replaced with safe defaults.  ``data_volume_bytes``
    is transformed to ``log1p`` scale for better linear fit.

    Parameters
    ----------
    telemetry_records:
        List of telemetry dicts, one per historical model run.

    Returns
    -------
    tuple[np.ndarray, np.ndarray]
        ``(X, y)`` where *X* has shape ``(n, 8)`` with columns
        ``[partition_count, log1p_data_volume_bytes, num_workers,
        sql_complexity_score, join_count, cte_count,
        has_window_functions, distinct_table_count]``
        and *y* has shape ``(n,)`` with values ``runtime_seconds``.
    """
    if not telemetry_records:
        return (
            np.empty((0, FEATURE_COUNT), dtype=np.float64),
            np.empty((0,), dtype=np.float64),
        )

    rows: list[list[float]] = []
    targets: list[float] = []

    for idx, record in enumerate(telemetry_records):
        if not isinstance(record, dict):
            logger.debug("Skipping non-dict record at index %d", idx)
            continue

        # --- Core features (backward-compatible) ---
        partition_count = _safe_float(record.get("partition_count"), _DEFAULT_PARTITION_COUNT)
        data_volume_bytes = _safe_float(record.get("data_volume_bytes"), _DEFAULT_DATA_VOLUME_BYTES)
        num_workers = _safe_float(record.get("num_workers"), _DEFAULT_NUM_WORKERS)
        runtime_seconds = _safe_float(record.get("runtime_seconds"), _DEFAULT_RUNTIME_SECONDS)

        # Transform data volume to log scale.
        log_volume = float(np.log1p(max(data_volume_bytes, 0.0)))

        # --- SQL complexity features ---
        sql_text = record.get("sql", "")
        if isinstance(sql_text, str) and sql_text.strip():
            sql_features = _extract_sql_features(sql_text)
        else:
            sql_features = _extract_sql_features_from_record(record)

        rows.append(
            [
                partition_count,
                log_volume,
                max(num_workers, 1.0),
                sql_features["sql_complexity_score"],
                sql_features["join_count"],
                sql_features["cte_count"],
                sql_features["has_window_functions"],
                sql_features["distinct_table_count"],
            ]
        )
        targets.append(max(runtime_seconds, 0.0))

    if not rows:
        return (
            np.empty((0, FEATURE_COUNT), dtype=np.float64),
            np.empty((0,), dtype=np.float64),
        )

    features = np.array(rows, dtype=np.float64)
    target_array = np.array(targets, dtype=np.float64)

    logger.info(
        "Extracted %d feature rows (%d features) from %d records",
        features.shape[0],
        FEATURE_COUNT,
        len(telemetry_records),
    )
    return features, target_array


def _extract_sql_features(sql: str) -> dict[str, float]:
    """Extract SQL complexity features from raw SQL text.

    Uses regex-based heuristics (not a full AST parse) for speed and
    to avoid external parser dependencies in the feature extraction
    hot path.
    """
    sql_upper = sql.upper()

    # Approximate AST node count: count SQL keywords as a proxy.
    keywords = {
        "SELECT",
        "FROM",
        "WHERE",
        "JOIN",
        "LEFT",
        "RIGHT",
        "INNER",
        "OUTER",
        "FULL",
        "CROSS",
        "ON",
        "GROUP",
        "BY",
        "HAVING",
        "ORDER",
        "LIMIT",
        "UNION",
        "INTERSECT",
        "EXCEPT",
        "INSERT",
        "UPDATE",
        "DELETE",
        "WITH",
        "AS",
        "CASE",
        "WHEN",
        "THEN",
        "ELSE",
        "END",
        "AND",
        "OR",
        "NOT",
        "IN",
        "EXISTS",
        "BETWEEN",
        "LIKE",
        "IS",
        "NULL",
        "DISTINCT",
        "PARTITION",
        "OVER",
        "ROW",
        "ROWS",
        "RANGE",
        "WINDOW",
    }
    tokens = re.findall(r"\b[A-Z_]+\b", sql_upper)
    complexity_score = float(sum(1 for t in tokens if t in keywords))

    # Join count.
    join_count = float(len(re.findall(r"\bJOIN\b", sql_upper)))

    # CTE count (WITH ... AS).
    cte_count = float(len(re.findall(r"\bWITH\b", sql_upper)))
    # Adjust: each additional AS within a WITH block is another CTE.
    # Approximation: count commas between CTEs.
    # Simple approach: count occurrences of ") , identifier AS (".
    # Just use the initial WITH count as a floor.

    # Window functions.
    has_window = 1.0 if re.search(r"\bOVER\s*\(", sql_upper) else 0.0

    # Distinct table references (FROM/JOIN targets).
    table_refs = set()
    # Match FROM <table> and JOIN <table> patterns.
    from_matches = re.findall(r"\bFROM\s+([a-zA-Z_][a-zA-Z0-9_.]*)", sql, re.IGNORECASE)
    join_matches = re.findall(r"\bJOIN\s+([a-zA-Z_][a-zA-Z0-9_.]*)", sql, re.IGNORECASE)
    for t in from_matches + join_matches:
        table_refs.add(t.lower())
    distinct_table_count = float(len(table_refs))

    return {
        "sql_complexity_score": complexity_score,
        "join_count": join_count,
        "cte_count": cte_count,
        "has_window_functions": has_window,
        "distinct_table_count": distinct_table_count,
    }


def _extract_sql_features_from_record(record: dict) -> dict[str, float]:
    """Extract SQL features from pre-computed record fields.

    Used when the raw SQL text is not available but the caller has
    pre-computed the feature values.  All fields default to 0.0 if
    absent, maintaining backward compatibility.
    """
    return {
        "sql_complexity_score": _safe_float(record.get("sql_complexity_score"), 0.0),
        "join_count": _safe_float(record.get("join_count"), 0.0),
        "cte_count": _safe_float(record.get("cte_count"), 0.0),
        "has_window_functions": 1.0 if record.get("has_window_functions") else 0.0,
        "distinct_table_count": _safe_float(record.get("distinct_table_count"), 0.0),
    }


def _safe_float(value: object, default: float) -> float:
    """Coerce *value* to float, returning *default* on failure."""
    if value is None:
        return default
    try:
        result = float(value)  # type: ignore[arg-type]
        if np.isnan(result) or np.isinf(result):
            return default
        return result
    except (TypeError, ValueError):
        return default

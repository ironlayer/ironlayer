"""SQL parsing and AST analysis."""

from core_engine.parser.ast_parser import (
    ModelASTMetadata,
    SQLParseError,
    extract_ctes,
    extract_output_columns,
    extract_referenced_tables,
    parse_sql,
)
from core_engine.parser.normalizer import (
    CURRENT_VERSION,
    CanonicalizerVersion,
    NormalizationError,
    compute_canonical_hash,
    get_canonicalizer_version,
    normalize_sql,
)
from core_engine.parser.sql_guard import (
    DangerousOperation,
    Severity,
    SQLGuardConfig,
    SQLGuardViolation,
    UnsafeSQLError,
    assert_sql_safe,
    check_sql_safety,
)

__all__ = [
    "CURRENT_VERSION",
    "CanonicalizerVersion",
    "DangerousOperation",
    "ModelASTMetadata",
    "NormalizationError",
    "SQLGuardConfig",
    "SQLGuardViolation",
    "SQLParseError",
    "Severity",
    "UnsafeSQLError",
    "assert_sql_safe",
    "check_sql_safety",
    "compute_canonical_hash",
    "extract_ctes",
    "extract_output_columns",
    "extract_referenced_tables",
    "get_canonicalizer_version",
    "normalize_sql",
    "parse_sql",
]

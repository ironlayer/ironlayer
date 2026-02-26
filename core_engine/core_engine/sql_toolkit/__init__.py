"""SQL Toolkit — implementation-agnostic SQL parsing, analysis, and transpilation.

Usage::

    from core_engine.sql_toolkit import get_sql_toolkit, Dialect

    tk = get_sql_toolkit()
    result = tk.parser.parse_one("SELECT * FROM orders", Dialect.DATABRICKS)
    tables = tk.scope_analyzer.extract_tables(sql, Dialect.DATABRICKS)
    transpiled = tk.transpiler.transpile(sql, Dialect.DATABRICKS, Dialect.DUCKDB)
    lineage = tk.lineage_analyzer.trace_column_lineage(sql, Dialect.DATABRICKS)

The default implementation delegates to SQLGlot.  A different backend can be
swapped in via ``register_implementation()`` without touching consumer code.
"""

from ._factory import get_sql_toolkit, register_implementation, reset_toolkit
from ._protocols import (
    SqlDiffer,
    SqlLineageAnalyzer,
    SqlNormalizer,
    SqlParser,
    SqlQualifier,
    SqlRenderer,
    SqlRewriter,
    SqlSafetyGuard,
    SqlScopeAnalyzer,
    SqlToolkit,
    SqlTranspiler,
)
from ._types import (
    AstDiffResult,
    ColumnExtractionResult,
    ColumnLineageNode,
    ColumnLineageResult,
    ColumnRef,
    CrossModelColumnLineage,
    Dialect,
    DiffEdit,
    DiffEditKind,
    NormalizationResult,
    ParseResult,
    QualifyResult,
    RewriteResult,
    RewriteRule,
    SafetyCheckResult,
    SafetyViolation,
    ScopeResult,
    SimplifyResult,
    SqlLineageError,
    SqlNode,
    SqlNodeKind,
    SqlNormalizationError,
    SqlParseError,
    SqlToolkitError,
    SqlTranspileError,
    TableRef,
    TranspileResult,
)

__all__ = [
    # Factory
    "get_sql_toolkit",
    "register_implementation",
    "reset_toolkit",
    # Protocols
    "SqlToolkit",
    "SqlParser",
    "SqlRenderer",
    "SqlScopeAnalyzer",
    "SqlTranspiler",
    "SqlNormalizer",
    "SqlDiffer",
    "SqlSafetyGuard",
    "SqlRewriter",
    "SqlLineageAnalyzer",
    "SqlQualifier",
    # Types
    "Dialect",
    "SqlNodeKind",
    "SqlNode",
    "TableRef",
    "ColumnRef",
    "ParseResult",
    "ScopeResult",
    "NormalizationResult",
    "TranspileResult",
    "AstDiffResult",
    "DiffEdit",
    "DiffEditKind",
    "ColumnExtractionResult",
    "SafetyCheckResult",
    "SafetyViolation",
    "RewriteResult",
    "RewriteRule",
    "ColumnLineageNode",
    "ColumnLineageResult",
    "CrossModelColumnLineage",
    "QualifyResult",
    "SimplifyResult",
    # Exceptions
    "SqlToolkitError",
    "SqlParseError",
    "SqlTranspileError",
    "SqlNormalizationError",
    "SqlLineageError",
]

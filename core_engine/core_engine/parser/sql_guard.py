"""SQL safety guard -- AST-based deny-list for dangerous SQL operations.

Detects and blocks destructive or privilege-escalating SQL before it reaches
any execution backend.  The guard is designed to sit in front of both the
local DuckDB executor and the remote Databricks executor, catching dangerous
operations at plan-generation time *and* again immediately before execution.

All detection uses structural AST analysis (via the SQL toolkit) -- never
regex on raw SQL text -- so that obfuscation via whitespace, comments, or
casing is ineffective.

All SQL parsing is delegated to :mod:`core_engine.sql_toolkit`.
"""

from __future__ import annotations

import enum
import logging

from pydantic import BaseModel, Field

from core_engine.sql_toolkit import Dialect, get_sql_toolkit

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------


class Severity(str, enum.Enum):
    """Severity level for a SQL guard violation."""

    CRITICAL = "CRITICAL"
    HIGH = "HIGH"
    MEDIUM = "MEDIUM"


class DangerousOperation(str, enum.Enum):
    """Catalogue of operations the SQL guard can detect and block."""

    DROP_TABLE = "DROP_TABLE"
    DROP_VIEW = "DROP_VIEW"
    DROP_SCHEMA = "DROP_SCHEMA"
    TRUNCATE = "TRUNCATE"
    DELETE_WITHOUT_WHERE = "DELETE_WITHOUT_WHERE"
    ALTER_DROP_COLUMN = "ALTER_DROP_COLUMN"
    GRANT = "GRANT"
    REVOKE = "REVOKE"
    CREATE_USER = "CREATE_USER"
    RAW_EXEC = "RAW_EXEC"
    INSERT_OVERWRITE_ALL = "INSERT_OVERWRITE_ALL"


# Mapping from operation to its default severity.
_DEFAULT_SEVERITY: dict[DangerousOperation, Severity] = {
    DangerousOperation.DROP_TABLE: Severity.CRITICAL,
    DangerousOperation.DROP_VIEW: Severity.CRITICAL,
    DangerousOperation.DROP_SCHEMA: Severity.CRITICAL,
    DangerousOperation.TRUNCATE: Severity.CRITICAL,
    DangerousOperation.DELETE_WITHOUT_WHERE: Severity.HIGH,
    DangerousOperation.ALTER_DROP_COLUMN: Severity.HIGH,
    DangerousOperation.GRANT: Severity.CRITICAL,
    DangerousOperation.REVOKE: Severity.CRITICAL,
    DangerousOperation.CREATE_USER: Severity.CRITICAL,
    DangerousOperation.RAW_EXEC: Severity.CRITICAL,
    DangerousOperation.INSERT_OVERWRITE_ALL: Severity.HIGH,
}


# ---------------------------------------------------------------------------
# Models
# ---------------------------------------------------------------------------


class SQLGuardViolation(BaseModel):
    """A single detected violation of the SQL safety policy."""

    operation: DangerousOperation = Field(
        description="The dangerous operation that was detected.",
    )
    description: str = Field(
        description="Human-readable explanation of the violation.",
    )
    line_number: int | None = Field(
        default=None,
        description="Approximate source line number, if available.",
    )
    severity: Severity = Field(
        description="Impact severity of the violation.",
    )


class SQLGuardConfig(BaseModel):
    """Configuration controlling which operations the guard blocks.

    By default every dangerous operation is blocked.  Individual escape
    hatches are provided for controlled maintenance scenarios; setting
    ``maintenance_mode=True`` disables all checks.
    """

    enabled: bool = Field(
        default=True,
        description="Master switch -- set False to bypass all checks.",
    )
    allow_drop: bool = Field(
        default=False,
        description="When True, DROP TABLE/VIEW/SCHEMA operations are permitted.",
    )
    allow_truncate: bool = Field(
        default=False,
        description="When True, TRUNCATE TABLE operations are permitted.",
    )
    allow_alter_drop_column: bool = Field(
        default=False,
        description="When True, ALTER TABLE ... DROP COLUMN is permitted.",
    )
    allow_delete_without_where: bool = Field(
        default=False,
        description="When True, DELETE without a WHERE clause is permitted.",
    )
    allowed_operations: set[DangerousOperation] = Field(
        default_factory=set,
        description="Explicit set of operations to allow regardless of other flags.",
    )
    maintenance_mode: bool = Field(
        default=False,
        description="When True, all checks are bypassed (use for schema migrations).",
    )


# ---------------------------------------------------------------------------
# Exception
# ---------------------------------------------------------------------------


class UnsafeSQLError(Exception):
    """Raised when SQL contains one or more CRITICAL safety violations."""

    def __init__(self, violations: list[SQLGuardViolation]) -> None:
        self.violations = violations
        descriptions = "; ".join(v.description for v in violations)
        super().__init__(f"Unsafe SQL detected: {descriptions}")


# ---------------------------------------------------------------------------
# Internal detection helpers
# ---------------------------------------------------------------------------


def _is_allowed(
    operation: DangerousOperation,
    config: SQLGuardConfig,
) -> bool:
    """Return True if *operation* is explicitly allowed by *config*."""
    if operation in config.allowed_operations:
        return True

    if (
        operation
        in {
            DangerousOperation.DROP_TABLE,
            DangerousOperation.DROP_VIEW,
            DangerousOperation.DROP_SCHEMA,
        }
        and config.allow_drop
    ):
        return True

    if operation is DangerousOperation.TRUNCATE and config.allow_truncate:
        return True

    if operation is DangerousOperation.ALTER_DROP_COLUMN and config.allow_alter_drop_column:
        return True

    return bool(operation is DangerousOperation.DELETE_WITHOUT_WHERE and config.allow_delete_without_where)


# Mapping from toolkit violation_type strings to DangerousOperation enum values.
_VIOLATION_TYPE_MAP: dict[str, DangerousOperation] = {
    "DROP_TABLE": DangerousOperation.DROP_TABLE,
    "DROP_VIEW": DangerousOperation.DROP_VIEW,
    "DROP_SCHEMA": DangerousOperation.DROP_SCHEMA,
    "TRUNCATE": DangerousOperation.TRUNCATE,
    "DELETE_WITHOUT_WHERE": DangerousOperation.DELETE_WITHOUT_WHERE,
    "ALTER_DROP_COLUMN": DangerousOperation.ALTER_DROP_COLUMN,
    "GRANT": DangerousOperation.GRANT,
    "REVOKE": DangerousOperation.REVOKE,
    "CREATE_USER": DangerousOperation.CREATE_USER,
    "RAW_EXEC": DangerousOperation.RAW_EXEC,
    "INSERT_OVERWRITE_ALL": DangerousOperation.INSERT_OVERWRITE_ALL,
    "UNPARSEABLE": DangerousOperation.RAW_EXEC,
}


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def check_sql_safety(
    sql: str,
    config: SQLGuardConfig | None = None,
) -> list[SQLGuardViolation]:
    """Analyse *sql* for dangerous operations and return any violations.

    The SQL string may contain one or more semicolon-separated statements.
    Each statement is independently parsed and inspected.

    Parameters
    ----------
    sql:
        Raw SQL text (Databricks dialect).
    config:
        Optional configuration overriding the default deny-all policy.
        When ``None``, a default :class:`SQLGuardConfig` (everything blocked)
        is used.

    Returns
    -------
    list[SQLGuardViolation]
        Detected violations.  An empty list indicates the SQL is considered
        safe under the active configuration.
    """
    if config is None:
        config = SQLGuardConfig()

    if not config.enabled or config.maintenance_mode:
        return []

    # Delegate detection to the SQL toolkit's safety guard.
    # allow_create=True and allow_insert=True so the toolkit reports only
    # genuinely dangerous operations (CREATE USER, INSERT OVERWRITE are
    # detected separately regardless of these flags).
    tk = get_sql_toolkit()
    try:
        safety_result = tk.safety_guard.check(
            sql,
            Dialect.DATABRICKS,
            allow_create=True,
            allow_insert=True,
        )
    except Exception as exc:
        logger.warning("SQL guard could not analyse input: %s", exc)
        return [
            SQLGuardViolation(
                operation=DangerousOperation.RAW_EXEC,
                description=f"SQL could not be parsed for safety analysis: {exc}",
                severity=Severity.CRITICAL,
            )
        ]

    # Map toolkit violations to our rich model and apply config filtering.
    violations: list[SQLGuardViolation] = []
    for v in safety_result.violations:
        operation = _VIOLATION_TYPE_MAP.get(v.violation_type)
        if operation is None:
            # Unknown violation type — skip silently.
            continue
        if _is_allowed(operation, config):
            continue
        severity = _DEFAULT_SEVERITY.get(operation, Severity.HIGH)
        violations.append(
            SQLGuardViolation(
                operation=operation,
                description=v.detail,
                severity=severity,
            )
        )

    return violations


def assert_sql_safe(
    sql: str,
    config: SQLGuardConfig | None = None,
) -> None:
    """Raise :class:`UnsafeSQLError` if *sql* contains CRITICAL violations.

    This is the primary integration point for executors.  Non-critical
    violations are logged as warnings but do not prevent execution.

    Parameters
    ----------
    sql:
        Raw SQL text to validate.
    config:
        Optional guard configuration.

    Raises
    ------
    UnsafeSQLError
        If any violation with severity ``CRITICAL`` is found.
    """
    violations = check_sql_safety(sql, config)
    if not violations:
        return

    critical = [v for v in violations if v.severity == Severity.CRITICAL]
    non_critical = [v for v in violations if v.severity != Severity.CRITICAL]

    for v in non_critical:
        logger.warning(
            "SQL guard warning (%s): %s [%s]",
            v.severity.value,
            v.description,
            v.operation.value,
        )

    if critical:
        logger.error(
            "SQL guard blocked execution: %d critical violation(s) found",
            len(critical),
        )
        raise UnsafeSQLError(critical)

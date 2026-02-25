"""Load SQL model files from disk and parse their YAML-style comment headers.

Each ``.sql`` model file begins with a block of ``-- key: value`` comment
lines that declare the model's metadata (name, kind, materialization, etc.).
The remainder of the file is the SQL body.

Typical usage::

    models = load_models_from_directory(Path("models/"))
"""

from __future__ import annotations

import hashlib
import logging
from pathlib import Path
from typing import Any

from core_engine.loader.ref_resolver import (
    build_model_registry,
    extract_ref_names,
    resolve_refs,
)
from core_engine.models.model_definition import (
    ColumnContract,
    Materialization,
    ModelDefinition,
    ModelKind,
    ModelTestDefinition,
    ModelTestType,
    SchemaContractMode,
    TestSeverity,
)

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Header field configuration
# ---------------------------------------------------------------------------
# Fields that MUST be present in every model header.
_REQUIRED_FIELDS: frozenset[str] = frozenset({"name", "kind"})

# Fields whose values should be split on commas into a ``list[str]``.
_LIST_FIELDS: frozenset[str] = frozenset({"tags", "dependencies"})

# All recognised header keys.  Unrecognised keys are silently ignored so that
# forward-compatible extensions can be added without breaking older loaders.
_KNOWN_FIELDS: frozenset[str] = frozenset(
    {
        "name",
        "kind",
        "materialization",
        "time_column",
        "unique_key",
        "partition_by",
        "incremental_strategy",
        "owner",
        "tags",
        "dependencies",
        "contract_mode",
        "contract_columns",
        "tests",
    }
)


# Fields requiring custom parsing (not simple strings or comma-separated lists).
_CUSTOM_PARSED_FIELDS: frozenset[str] = frozenset({"contract_columns", "tests"})


# ---------------------------------------------------------------------------
# Contract column parsing
# ---------------------------------------------------------------------------


def _parse_contract_columns(value: str) -> list[ColumnContract]:
    """Parse a ``contract_columns`` header value into :class:`ColumnContract` objects.

    The expected syntax is a comma-separated list of column declarations::

        id:INT:NOT_NULL, name:STRING, created_at:TIMESTAMP:NOT_NULL

    Each declaration has the form ``name:TYPE`` or ``name:TYPE:NOT_NULL``.
    The ``:NOT_NULL`` suffix marks the column as non-nullable.

    Parameters
    ----------
    value:
        Raw header value string.

    Returns
    -------
    list[ColumnContract]
        Parsed column contracts.

    Raises
    ------
    HeaderParseError
        If any column declaration is malformed.
    """
    if not value.strip():
        return []

    contracts: list[ColumnContract] = []
    for item in value.split(","):
        item = item.strip()
        if not item:
            continue

        parts = item.split(":")
        if len(parts) < 2:
            raise HeaderParseError(
                f"Invalid contract_columns entry '{item}': expected " f"'name:TYPE' or 'name:TYPE:NOT_NULL'."
            )

        col_name = parts[0].strip()
        data_type = parts[1].strip().upper()
        nullable = True

        if len(parts) >= 3:
            modifier = parts[2].strip().upper()
            if modifier == "NOT_NULL":
                nullable = False
            elif modifier:
                raise HeaderParseError(
                    f"Invalid contract_columns modifier '{parts[2].strip()}' "
                    f"for column '{col_name}'. Expected 'NOT_NULL'."
                )

        if not col_name:
            raise HeaderParseError("Empty column name in contract_columns declaration.")
        if not data_type:
            raise HeaderParseError(f"Empty data type for column '{col_name}' in contract_columns.")

        contracts.append(ColumnContract(name=col_name, data_type=data_type, nullable=nullable))

    return contracts


# ---------------------------------------------------------------------------
# Test declaration parsing
# ---------------------------------------------------------------------------


# Maps lowercase test type names to their ModelTestType enum values.
_TEST_TYPE_LOOKUP: dict[str, ModelTestType] = {
    "not_null": ModelTestType.NOT_NULL,
    "unique": ModelTestType.UNIQUE,
    "row_count_min": ModelTestType.ROW_COUNT_MIN,
    "row_count_max": ModelTestType.ROW_COUNT_MAX,
    "accepted_values": ModelTestType.ACCEPTED_VALUES,
    "custom_sql": ModelTestType.CUSTOM_SQL,
}


def _parse_test_declarations(value: str) -> list[ModelTestDefinition]:
    """Parse test declarations from a ``tests`` header value.

    The expected syntax is a comma-separated list of test declarations::

        not_null(id), unique(id), row_count_min(100),
        accepted_values(status:active|inactive|pending),
        custom_sql(SELECT * FROM {model} WHERE amount < 0)

    Each declaration is ``test_type(arg)`` where:

    * ``not_null(column_name)``
    * ``unique(column_name)``
    * ``row_count_min(threshold)``
    * ``row_count_max(threshold)``
    * ``accepted_values(column:val1|val2|val3)``
    * ``custom_sql(SQL statement)``

    Optionally a severity suffix ``@WARN`` can be added to any test::

        not_null(id)@WARN, unique(email)

    A state-machine parser tracks parenthesis depth so that ``custom_sql``
    arguments containing commas and nested parentheses are handled correctly.

    Parameters
    ----------
    value:
        Raw header value string.

    Returns
    -------
    list[ModelTestDefinition]
        Parsed test definitions, sorted by (test_type, column/sql) for
        deterministic ordering.

    Raises
    ------
    HeaderParseError
        If a declaration is malformed or uses an unknown test type.
    """
    if not value.strip():
        return []

    # Split into individual declarations using a paren-depth-aware parser.
    declarations: list[str] = []
    current: list[str] = []
    depth = 0

    for ch in value:
        if ch == "(":
            depth += 1
            current.append(ch)
        elif ch == ")":
            depth -= 1
            current.append(ch)
        elif ch == "," and depth == 0:
            declarations.append("".join(current).strip())
            current = []
        else:
            current.append(ch)

    # Capture trailing declaration.
    trailing = "".join(current).strip()
    if trailing:
        declarations.append(trailing)

    tests: list[ModelTestDefinition] = []

    for decl in declarations:
        if not decl:
            continue

        # Check for severity suffix: test_type(arg)@WARN
        severity = TestSeverity.BLOCK
        base_decl = decl
        if ")@" in decl:
            base_decl, severity_str = decl.rsplit(")@", 1)
            base_decl = base_decl + ")"
            severity_str = severity_str.strip().upper()
            try:
                severity = TestSeverity(severity_str)
            except ValueError:
                valid = ", ".join(s.value for s in TestSeverity)
                raise HeaderParseError(
                    f"Invalid test severity '{severity_str}' in '{decl}'. " f"Valid options: {valid}."
                )

        # Extract test_type and arg from ``test_type(arg)``.
        paren_idx = base_decl.find("(")
        if paren_idx == -1 or not base_decl.endswith(")"):
            raise HeaderParseError(f"Invalid test declaration '{decl}': expected 'test_type(arg)' syntax.")

        test_name = base_decl[:paren_idx].strip().lower()
        arg = base_decl[paren_idx + 1 : -1].strip()

        if test_name not in _TEST_TYPE_LOOKUP:
            valid = ", ".join(sorted(_TEST_TYPE_LOOKUP))
            raise HeaderParseError(f"Unknown test type '{test_name}' in '{decl}'. " f"Valid types: {valid}.")

        test_type = _TEST_TYPE_LOOKUP[test_name]

        if test_type in (ModelTestType.NOT_NULL, ModelTestType.UNIQUE):
            if not arg:
                raise HeaderParseError(f"Test '{test_name}' requires a column name argument.")
            tests.append(ModelTestDefinition(test_type=test_type, column=arg, severity=severity))

        elif test_type in (ModelTestType.ROW_COUNT_MIN, ModelTestType.ROW_COUNT_MAX):
            if not arg:
                raise HeaderParseError(f"Test '{test_name}' requires a numeric threshold argument.")
            try:
                threshold = int(arg)
            except ValueError:
                raise HeaderParseError(f"Test '{test_name}' threshold must be an integer, got '{arg}'.")
            tests.append(ModelTestDefinition(test_type=test_type, threshold=threshold, severity=severity))

        elif test_type == ModelTestType.ACCEPTED_VALUES:
            if ":" not in arg:
                raise HeaderParseError(
                    f"Test 'accepted_values' requires 'column:val1|val2|...' syntax, " f"got '{arg}'."
                )
            col, vals_str = arg.split(":", 1)
            col = col.strip()
            if not col:
                raise HeaderParseError("Empty column name in accepted_values declaration.")
            vals = sorted(v.strip() for v in vals_str.split("|") if v.strip())
            if not vals:
                raise HeaderParseError(f"No values provided in accepted_values for column '{col}'.")
            tests.append(
                ModelTestDefinition(
                    test_type=test_type,
                    column=col,
                    values=vals,
                    severity=severity,
                )
            )

        elif test_type == ModelTestType.CUSTOM_SQL:
            if not arg:
                raise HeaderParseError("Test 'custom_sql' requires a SQL statement argument.")
            tests.append(ModelTestDefinition(test_type=test_type, sql=arg, severity=severity))

    # Sort deterministically by (test_type, column, sql) for repeatability.
    tests.sort(key=lambda t: (t.test_type.value, t.column or "", t.sql or ""))

    return tests


# ---------------------------------------------------------------------------
# Exceptions
# ---------------------------------------------------------------------------


class HeaderParseError(Exception):
    """Raised when required header fields are missing or invalid."""


class ModelLoadError(Exception):
    """Raised when a model file cannot be read from disk."""


# ---------------------------------------------------------------------------
# Header parsing
# ---------------------------------------------------------------------------


def parse_yaml_header(sql_content: str) -> dict[str, Any]:
    """Extract ``-- key: value`` metadata from the top of a SQL file.

    The parser reads lines sequentially from the start of the file.  A line
    is considered part of the header if it matches one of:

    * ``-- key: value``   (a metadata declaration)
    * ``--``              (an empty comment, treated as a blank separator)
    * an empty/whitespace-only line

    The first line that does **not** match any of the above terminates the
    header block.  Everything after that first non-header line is the SQL
    body.

    Parameters
    ----------
    sql_content:
        The full text content of a ``.sql`` file.

    Returns
    -------
    dict[str, Any]
        Parsed header values.  List fields (``tags``, ``dependencies``)
        are returned as ``list[str]``; all other values are ``str``.

    Raises
    ------
    HeaderParseError
        If any of the required fields (``name``, ``kind``) are absent.
    """
    header: dict[str, Any] = {}

    for line in sql_content.splitlines():
        stripped = line.strip()

        # Empty lines and bare comments are allowed inside the header block.
        if stripped == "" or stripped == "--":
            continue

        # Check for ``-- key: value`` pattern.
        if stripped.startswith("--"):
            payload = stripped[2:].strip()
            if ":" in payload:
                key, _, value = payload.partition(":")
                key = key.strip().lower()
                value = value.strip()

                if key in _KNOWN_FIELDS:
                    if key in _CUSTOM_PARSED_FIELDS:
                        if key == "contract_columns":
                            header[key] = _parse_contract_columns(value)
                        elif key == "tests":
                            header[key] = _parse_test_declarations(value)
                    elif key in _LIST_FIELDS:
                        header[key] = [item.strip() for item in value.split(",") if item.strip()]
                    else:
                        header[key] = value
                continue
            # A comment line without a colon (e.g. ``-- this is a note``)
            # is still a comment; it does not terminate the header.
            continue

        # First non-comment, non-empty line -> end of header block.
        break

    # Validate required fields.
    missing = _REQUIRED_FIELDS - header.keys()
    if missing:
        raise HeaderParseError(
            f"Missing required header fields: {sorted(missing)}. "
            f"Every SQL model file must declare at least: "
            f"{sorted(_REQUIRED_FIELDS)}."
        )

    return header


# ---------------------------------------------------------------------------
# Single-file parsing
# ---------------------------------------------------------------------------


def _extract_sql_body(sql_content: str) -> str:
    """Return the SQL body with the header comment block stripped.

    Everything up to (and including) the last consecutive header line is
    removed.  The SQL body is the remaining content, leading-whitespace
    stripped.
    """
    body_lines: list[str] = []
    in_header = True

    for line in sql_content.splitlines():
        if in_header:
            stripped = line.strip()
            # Same rules as parse_yaml_header for identifying header lines.
            if stripped == "" or stripped == "--":
                continue
            if stripped.startswith("--"):
                payload = stripped[2:].strip()
                if ":" in payload:
                    # This is a ``-- key: value`` header line; skip it.
                    continue
                # A plain comment line inside the header region; skip it.
                continue
            # First non-header line: exit header mode and keep the line.
            in_header = False

        body_lines.append(line)

    return "\n".join(body_lines).strip()


def _compute_content_hash(sql: str) -> str:
    """Return the SHA-256 hex digest of the given SQL string."""
    return hashlib.sha256(sql.encode("utf-8")).hexdigest()


def parse_model_file(
    file_path: Path,
    model_registry: dict[str, str] | None = None,
) -> ModelDefinition:
    """Read a single ``.sql`` model file and return a :class:`ModelDefinition`.

    Parameters
    ----------
    file_path:
        Path to the ``.sql`` file on disk.
    model_registry:
        Optional mapping from model short names to canonical names.  When
        provided, ``{{ ref('...') }}`` macros in the SQL body are resolved.
        When ``None``, the raw SQL is kept as-is and ``clean_sql`` is set
        to the body with the header stripped but refs unresolved.

    Returns
    -------
    ModelDefinition

    Raises
    ------
    ModelLoadError
        If the file cannot be read.
    HeaderParseError
        If required header fields are missing.
    """
    try:
        raw_sql = file_path.read_text(encoding="utf-8")
    except OSError as exc:
        raise ModelLoadError(f"Failed to read model file '{file_path}': {exc}") from exc

    header = parse_yaml_header(raw_sql)
    sql_body = _extract_sql_body(raw_sql)

    # Resolve refs if a registry is available, otherwise keep the raw body.
    if model_registry is not None:
        clean_sql = resolve_refs(sql_body, model_registry)
    else:
        clean_sql = sql_body

    content_hash = _compute_content_hash(clean_sql)

    # Extract the list of referenced model names from the raw SQL body
    # (before resolution) so that ``referenced_tables`` captures the
    # original ref targets.
    ref_names = extract_ref_names(sql_body)

    # If a registry is available, map ref names to canonical table names.
    if model_registry is not None:
        referenced_tables = [model_registry.get(name, name) for name in ref_names]
    else:
        referenced_tables = ref_names

    # Parse contract_mode if present.
    contract_mode = SchemaContractMode.DISABLED
    if "contract_mode" in header:
        try:
            contract_mode = SchemaContractMode(header["contract_mode"].upper())
        except ValueError:
            valid = ", ".join(m.value for m in SchemaContractMode)
            raise HeaderParseError(f"Invalid contract_mode '{header['contract_mode']}'. " f"Valid options: {valid}.")

    return ModelDefinition(
        name=header["name"],
        kind=ModelKind(header["kind"]),
        materialization=(
            Materialization(header["materialization"]) if "materialization" in header else Materialization.TABLE
        ),
        time_column=header.get("time_column"),
        unique_key=header.get("unique_key"),
        partition_by=header.get("partition_by"),
        incremental_strategy=header.get("incremental_strategy"),
        owner=header.get("owner"),
        tags=header.get("tags", []),
        dependencies=header.get("dependencies", []),
        file_path=str(file_path),
        raw_sql=raw_sql,
        clean_sql=clean_sql,
        content_hash=content_hash,
        referenced_tables=referenced_tables,
        contract_mode=contract_mode,
        contract_columns=header.get("contract_columns", []),
        tests=header.get("tests", []),
    )


# ---------------------------------------------------------------------------
# Directory scanning (two-pass)
# ---------------------------------------------------------------------------


def load_models_from_directory(models_dir: Path) -> list[ModelDefinition]:
    """Discover, parse, and resolve all ``.sql`` model files under *models_dir*.

    The loading happens in two passes:

    1. **Scan pass** -- Iterate over every ``.sql`` file, parse its header
       only (no ref resolution), and build a model registry.
    2. **Full-parse pass** -- Re-parse every file with the complete model
       registry so that all ``{{ ref() }}`` macros can be resolved.

    Parameters
    ----------
    models_dir:
        Root directory to search for ``.sql`` files.  The search is
        recursive.

    Returns
    -------
    list[ModelDefinition]
        Fully-parsed model definitions with refs resolved, sorted
        alphabetically by model name for deterministic ordering.

    Raises
    ------
    ModelLoadError
        If *models_dir* does not exist or is not a directory.
    """
    if not models_dir.is_dir():
        raise ModelLoadError(f"Models directory does not exist or is not a directory: " f"'{models_dir}'")

    sql_files = sorted(models_dir.rglob("*.sql"))
    if not sql_files:
        logger.warning("No .sql files found under '%s'.", models_dir)
        return []

    logger.info(
        "Pass 1: scanning %d SQL file(s) under '%s'.",
        len(sql_files),
        models_dir,
    )

    # -- Pass 1: headers only, no ref resolution --------------------------
    header_models: list[ModelDefinition] = []
    for path in sql_files:
        try:
            model = parse_model_file(path, model_registry=None)
            header_models.append(model)
        except (HeaderParseError, ModelLoadError) as exc:
            logger.error("Skipping '%s': %s", path, exc)

    registry = build_model_registry(header_models)
    logger.info(
        "Built model registry with %d entries from %d model(s).",
        len(registry),
        len(header_models),
    )

    # -- Pass 2: full parse with ref resolution ---------------------------
    logger.info("Pass 2: resolving refs for %d model(s).", len(sql_files))

    resolved_models: list[ModelDefinition] = []
    for path in sql_files:
        try:
            model = parse_model_file(path, model_registry=registry)
            resolved_models.append(model)
        except (HeaderParseError, ModelLoadError) as exc:
            logger.error("Skipping '%s' during ref resolution: %s", path, exc)

    # Sort by name for deterministic graph construction downstream.
    resolved_models.sort(key=lambda m: m.name)

    logger.info("Loaded %d model(s) from '%s'.", len(resolved_models), models_dir)
    return resolved_models

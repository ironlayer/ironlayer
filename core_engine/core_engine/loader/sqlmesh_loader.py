"""SQLMesh project loader -- bridge SQLMesh projects into IronLayer.

Parses SQLMesh project configuration (``config.yaml``) and model files
(both SQL with ``MODEL`` headers and Python ``@model`` definitions) to
produce :class:`ModelDefinition` instances suitable for IronLayer
migration.

Supported SQLMesh model kinds:
    * ``FULL`` → ``FULL_REFRESH / TABLE``
    * ``VIEW`` → ``FULL_REFRESH / VIEW``
    * ``INCREMENTAL_BY_TIME_RANGE`` → ``INCREMENTAL_BY_TIME_RANGE / INSERT_OVERWRITE``
    * ``INCREMENTAL_BY_UNIQUE_KEY`` → ``MERGE_BY_KEY / MERGE``
    * ``INCREMENTAL_BY_PARTITION`` → ``INCREMENTAL_BY_TIME_RANGE / INSERT_OVERWRITE``
    * ``SEED`` → ``FULL_REFRESH / TABLE``
    * ``SCD_TYPE_2`` → ``MERGE_BY_KEY / MERGE``

This loader does NOT require SQLMesh to be installed -- it reads model
files directly using lightweight parsing.
"""

from __future__ import annotations

import hashlib
import logging
import re
from pathlib import Path
from typing import Any

import yaml  # type: ignore[import-untyped]

from core_engine.models.model_definition import (
    Materialization,
    ModelDefinition,
    ModelKind,
)

logger = logging.getLogger(__name__)


class SQLMeshLoadError(Exception):
    """Raised when a SQLMesh project cannot be loaded."""


# ---------------------------------------------------------------------------
# Kind mapping
# ---------------------------------------------------------------------------

_KIND_MAP: dict[str, tuple[ModelKind, Materialization]] = {
    "FULL": (ModelKind.FULL_REFRESH, Materialization.TABLE),
    "VIEW": (ModelKind.FULL_REFRESH, Materialization.VIEW),
    "INCREMENTAL_BY_TIME_RANGE": (ModelKind.INCREMENTAL_BY_TIME_RANGE, Materialization.INSERT_OVERWRITE),
    "INCREMENTAL_BY_UNIQUE_KEY": (ModelKind.MERGE_BY_KEY, Materialization.MERGE),
    "INCREMENTAL_BY_PARTITION": (ModelKind.INCREMENTAL_BY_TIME_RANGE, Materialization.INSERT_OVERWRITE),
    "SEED": (ModelKind.FULL_REFRESH, Materialization.TABLE),
    "SCD_TYPE_2": (ModelKind.MERGE_BY_KEY, Materialization.MERGE),
    "EMBEDDED": (ModelKind.FULL_REFRESH, Materialization.VIEW),
    "EXTERNAL": (ModelKind.FULL_REFRESH, Materialization.TABLE),
}

# Regex patterns for SQL MODEL block parsing
_MODEL_BLOCK_RE = re.compile(
    r"MODEL\s*\((.*?)\)\s*;",
    re.DOTALL | re.IGNORECASE,
)

# Attribute patterns inside MODEL block
_ATTR_NAME_RE = re.compile(r"name\s+(\S+)", re.IGNORECASE)
_ATTR_KIND_RE = re.compile(r"kind\s+(\w+)", re.IGNORECASE)
_ATTR_OWNER_RE = re.compile(r"owner\s+(\S+)", re.IGNORECASE)
_ATTR_CRON_RE = re.compile(r"cron\s+['\"](.+?)['\"]", re.IGNORECASE)
_ATTR_GRAIN_RE = re.compile(r"grain\s*\(?\s*([^)]+)\s*\)?", re.IGNORECASE)
_ATTR_TAGS_RE = re.compile(r"tags\s*\(([^)]+)\)", re.IGNORECASE)
_ATTR_DEPENDS_ON_RE = re.compile(r"depends_on\s*\(([^)]+)\)", re.IGNORECASE)
_ATTR_TIME_COLUMN_RE = re.compile(r"time_column\s*\(?\s*(\S+)\s*\)?", re.IGNORECASE)

# Python @model decorator parsing
_PY_MODEL_RE = re.compile(
    r"@model\s*\((.*?)\)",
    re.DOTALL,
)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def discover_sqlmesh_project(project_path: Path) -> Path | None:
    """Locate the SQLMesh config file within a project directory.

    Searches for:
    - ``config.yaml``
    - ``config.yml``
    - ``config.py``

    Returns
    -------
    Path | None
        Path to the config file, or None if not found.
    """
    for name in ("config.yaml", "config.yml", "config.py"):
        candidate = project_path / name
        if candidate.exists():
            return candidate
    return None


def load_models_from_sqlmesh_project(
    project_path: Path,
    *,
    tag_filter: str | None = None,
) -> list[ModelDefinition]:
    """Load all model definitions from a SQLMesh project.

    Parameters
    ----------
    project_path:
        Root directory of the SQLMesh project.
    tag_filter:
        Optional tag to filter models by (only models with this tag
        are returned).

    Returns
    -------
    list[ModelDefinition]
        Sorted list of parsed model definitions.

    Raises
    ------
    SQLMeshLoadError
        If the project cannot be loaded.
    """
    if not project_path.is_dir():
        raise SQLMeshLoadError(f"Project path does not exist: {project_path}")

    config_path = discover_sqlmesh_project(project_path)
    if config_path is None:
        raise SQLMeshLoadError(
            f"No SQLMesh config file found in {project_path}. Expected config.yaml, config.yml, or config.py"
        )

    # Parse config for model_defaults and model paths
    config = _parse_config(config_path)
    model_defaults = config.get("model_defaults", {})
    model_paths = config.get("model_paths", ["models"])

    # Discover model files
    models: list[ModelDefinition] = []
    skip_count = 0

    for model_dir_name in model_paths:
        model_dir = project_path / model_dir_name
        if not model_dir.is_dir():
            logger.debug("Model directory does not exist: %s", model_dir)
            continue

        # SQL model files
        for sql_file in sorted(model_dir.rglob("*.sql")):
            try:
                model_def = _parse_sql_model_file(
                    sql_file,
                    model_dir,
                    model_defaults,
                )
                if model_def is not None:
                    if tag_filter and tag_filter not in (model_def.tags or []):
                        skip_count += 1
                        continue
                    models.append(model_def)
            except Exception as exc:
                logger.warning("Failed to parse %s: %s", sql_file, exc)
                skip_count += 1

        # Python model files
        for py_file in sorted(model_dir.rglob("*.py")):
            if py_file.name.startswith("_"):
                continue
            try:
                model_def = _parse_python_model_file(
                    py_file,
                    model_dir,
                    model_defaults,
                )
                if model_def is not None:
                    if tag_filter and tag_filter not in (model_def.tags or []):
                        skip_count += 1
                        continue
                    models.append(model_def)
            except Exception as exc:
                logger.warning("Failed to parse %s: %s", py_file, exc)
                skip_count += 1

    models.sort(key=lambda m: m.name)

    logger.info(
        "Loaded %d models from SQLMesh project (skipped %d)",
        len(models),
        skip_count,
    )

    return models


# ---------------------------------------------------------------------------
# Internals
# ---------------------------------------------------------------------------


def _parse_config(config_path: Path) -> dict[str, Any]:
    """Parse a SQLMesh config.yaml / config.yml file.

    For config.py files, we extract what we can via regex but don't
    execute the Python.
    """
    if config_path.suffix == ".py":
        return _parse_python_config(config_path)

    try:
        text = config_path.read_text(encoding="utf-8")
        data = yaml.safe_load(text) or {}
        if not isinstance(data, dict):
            return {}
        return data
    except yaml.YAMLError as exc:
        raise SQLMeshLoadError(f"Failed to parse {config_path}: {exc}") from exc


def _parse_python_config(config_path: Path) -> dict[str, Any]:
    """Best-effort extraction from a Python config file."""
    text = config_path.read_text(encoding="utf-8")
    config: dict[str, Any] = {}

    # Try to find model_defaults
    model_defaults_match = re.search(
        r"model_defaults\s*=\s*\{([^}]+)\}",
        text,
        re.DOTALL,
    )
    if model_defaults_match:
        config["model_defaults"] = {}

    # Try to find model_paths
    model_paths_match = re.search(
        r"model_paths?\s*=\s*\[([^\]]+)\]",
        text,
    )
    if model_paths_match:
        paths = re.findall(r'["\']([^"\']+)["\']', model_paths_match.group(1))
        if paths:
            config["model_paths"] = paths

    return config


def _parse_sql_model_file(
    file_path: Path,
    model_dir: Path,
    defaults: dict[str, Any],
) -> ModelDefinition | None:
    """Parse a SQLMesh SQL model file with MODEL block header."""
    text = file_path.read_text(encoding="utf-8")
    if not text.strip():
        return None

    # Extract MODEL block
    model_match = _MODEL_BLOCK_RE.search(text)

    if model_match:
        block = model_match.group(1)
        attrs = _parse_model_block(block)

        # SQL body is everything after the MODEL block
        end_pos = model_match.end()
        sql_body = text[end_pos:].strip()
    else:
        # No MODEL block -- treat as a raw SQL file with name from path
        attrs = {}
        sql_body = text.strip()

    # Determine model name
    name = attrs.get("name")
    if not name:
        # Derive from file path relative to model dir
        rel = file_path.relative_to(model_dir)
        parts = list(rel.parent.parts) + [rel.stem]
        name = ".".join(parts)

    # Determine kind
    kind_str = attrs.get("kind", defaults.get("kind", "FULL")).upper()
    kind, materialization = _KIND_MAP.get(kind_str, (ModelKind.FULL_REFRESH, Materialization.TABLE))

    # Extract metadata
    time_column = attrs.get("time_column")
    unique_key = attrs.get("grain")
    owner = attrs.get("owner", defaults.get("owner"))
    tags = attrs.get("tags", [])
    dependencies = attrs.get("depends_on", [])

    # Handle kind-specific requirements
    if kind == ModelKind.INCREMENTAL_BY_TIME_RANGE and not time_column:
        kind = ModelKind.FULL_REFRESH
        materialization = Materialization.TABLE
    if kind == ModelKind.MERGE_BY_KEY and not unique_key:
        kind = ModelKind.FULL_REFRESH
        materialization = Materialization.TABLE

    # Compute content_hash for change detection.
    content_hash = hashlib.sha256(sql_body.encode("utf-8")).hexdigest()

    return ModelDefinition(
        name=name,
        kind=kind,
        materialization=materialization,
        time_column=time_column,
        unique_key=unique_key,
        owner=owner,
        tags=tags,
        dependencies=dependencies,
        file_path=str(file_path),
        raw_sql=sql_body,
        clean_sql=sql_body,
        content_hash=content_hash,
    )


def _parse_model_block(block_text: str) -> dict[str, Any]:
    """Extract attributes from a MODEL(...) block."""
    attrs: dict[str, Any] = {}

    # Name
    name_match = _ATTR_NAME_RE.search(block_text)
    if name_match:
        name = name_match.group(1).strip("'\"").strip(",")
        attrs["name"] = name

    # Kind
    kind_match = _ATTR_KIND_RE.search(block_text)
    if kind_match:
        kind = kind_match.group(1).strip("'\"").strip(",")
        attrs["kind"] = kind

    # Owner
    owner_match = _ATTR_OWNER_RE.search(block_text)
    if owner_match:
        owner = owner_match.group(1).strip("'\"").strip(",")
        attrs["owner"] = owner

    # Cron (stored but not mapped to ModelDefinition field)
    cron_match = _ATTR_CRON_RE.search(block_text)
    if cron_match:
        attrs["cron"] = cron_match.group(1)

    # Grain -> unique_key
    grain_match = _ATTR_GRAIN_RE.search(block_text)
    if grain_match:
        grain_text = grain_match.group(1).strip()
        # Clean up: remove quotes and commas
        grains = [g.strip().strip("'\"").strip(",") for g in grain_text.split(",") if g.strip().strip("'\"").strip(",")]
        if grains:
            attrs["grain"] = ", ".join(grains)

    # Tags
    tags_match = _ATTR_TAGS_RE.search(block_text)
    if tags_match:
        tags_text = tags_match.group(1)
        tags = [t.strip().strip("'\"") for t in tags_text.split(",") if t.strip().strip("'\"")]
        attrs["tags"] = tags

    # Dependencies
    deps_match = _ATTR_DEPENDS_ON_RE.search(block_text)
    if deps_match:
        deps_text = deps_match.group(1)
        deps = [d.strip().strip("'\"") for d in deps_text.split(",") if d.strip().strip("'\"")]
        attrs["depends_on"] = deps

    # Time column
    tc_match = _ATTR_TIME_COLUMN_RE.search(block_text)
    if tc_match:
        tc = tc_match.group(1).strip("'\"").strip(",")
        attrs["time_column"] = tc

    return attrs


def _parse_python_model_file(
    file_path: Path,
    model_dir: Path,
    defaults: dict[str, Any],
) -> ModelDefinition | None:
    """Parse a SQLMesh Python model file with @model decorator."""
    text = file_path.read_text(encoding="utf-8")
    if not text.strip():
        return None

    # Find @model decorator
    model_match = _PY_MODEL_RE.search(text)
    if model_match is None:
        return None

    block = model_match.group(1)

    # Extract name from decorator args
    name_match = re.search(r'["\'](\S+?)["\']', block)
    name = name_match.group(1) if name_match else None

    if not name:
        rel = file_path.relative_to(model_dir)
        parts = list(rel.parent.parts) + [rel.stem]
        name = ".".join(parts)

    # Extract kind
    kind_match = re.search(r'kind\s*=\s*["\']?(\w+)', block)
    kind_str = kind_match.group(1).upper() if kind_match else defaults.get("kind", "FULL")
    kind, materialization = _KIND_MAP.get(kind_str.upper(), (ModelKind.FULL_REFRESH, Materialization.TABLE))

    # Extract owner
    owner_match = re.search(r'owner\s*=\s*["\'](\S+?)["\']', block)
    owner = owner_match.group(1) if owner_match else defaults.get("owner")

    # Python models don't have SQL bodies we can extract easily
    sql_body = f"-- Python model: see source at {file_path.name}"

    # Handle kind-specific requirements (fall back to safe defaults)
    if kind == ModelKind.INCREMENTAL_BY_TIME_RANGE:
        kind = ModelKind.FULL_REFRESH
        materialization = Materialization.TABLE
    if kind == ModelKind.MERGE_BY_KEY:
        kind = ModelKind.FULL_REFRESH
        materialization = Materialization.TABLE

    # Compute content_hash for change detection.
    content_hash = hashlib.sha256(sql_body.encode("utf-8")).hexdigest()

    return ModelDefinition(
        name=name,
        kind=kind,
        materialization=materialization,
        owner=owner,
        file_path=str(file_path),
        raw_sql=sql_body,
        clean_sql=sql_body,
        content_hash=content_hash,
    )

"""Load model definitions from a dbt ``manifest.json`` file.

This module bridges dbt projects into IronLayer by parsing the dbt manifest
artifact and converting each model node into a :class:`ModelDefinition`.
Ephemeral models, tests, sources, and other non-model resources are skipped.

Typical usage::

    models = load_models_from_dbt_manifest(Path("target/manifest.json"))

The mapping between dbt and IronLayer concepts is deterministic and follows
a well-defined rule set documented in :func:`_map_dbt_materialization`.
"""

from __future__ import annotations

import hashlib
import json
import logging
from pathlib import Path
from typing import Any

from core_engine.models.model_definition import (
    Materialization,
    ModelDefinition,
    ModelKind,
)

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Exceptions
# ---------------------------------------------------------------------------


class DbtManifestError(Exception):
    """Raised when a dbt manifest.json file is invalid or cannot be parsed."""


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _map_dbt_materialization(
    config: dict[str, Any],
) -> tuple[ModelKind, Materialization]:
    """Map a dbt node config to IronLayer ``(ModelKind, Materialization)``.

    Parameters
    ----------
    config:
        The ``config`` dict from a dbt manifest node.

    Returns
    -------
    tuple[ModelKind, Materialization]

    Raises
    ------
    DbtManifestError
        If the materialization value is unrecognised and not ``ephemeral``.
    """
    materialized = config.get("materialized", "table")
    strategy = config.get("incremental_strategy") or ""

    if materialized == "table":
        return ModelKind.FULL_REFRESH, Materialization.TABLE

    if materialized == "view":
        return ModelKind.FULL_REFRESH, Materialization.VIEW

    if materialized == "incremental":
        strategy_lower = strategy.lower().strip()

        if strategy_lower == "merge":
            return ModelKind.MERGE_BY_KEY, Materialization.MERGE

        if strategy_lower == "insert_overwrite":
            return ModelKind.INCREMENTAL_BY_TIME_RANGE, Materialization.INSERT_OVERWRITE

        if strategy_lower == "delete+insert":
            return ModelKind.INCREMENTAL_BY_TIME_RANGE, Materialization.TABLE

        if strategy_lower == "append":
            return ModelKind.APPEND_ONLY, Materialization.TABLE

        # Default incremental (no explicit strategy or unknown strategy)
        return ModelKind.INCREMENTAL_BY_TIME_RANGE, Materialization.TABLE

    if materialized == "ephemeral":
        # Caller should check before invoking, but be defensive.
        raise DbtManifestError("Ephemeral models should be skipped before mapping materialisation.")

    raise DbtManifestError(
        f"Unrecognised dbt materialisation: '{materialized}'. " f"Expected one of: table, view, incremental, ephemeral."
    )


def _extract_time_column(config: dict[str, Any]) -> str | None:
    """Extract the time/partition column from a dbt node config.

    dbt expresses ``partition_by`` in several forms depending on the adapter:

    * ``{"field": "event_date", "data_type": "date"}`` (BigQuery style)
    * ``"event_date"`` (plain string, Databricks/Spark style)
    * A list of partition columns (Spark) -- we take the first one.

    Returns
    -------
    str or None
        The extracted field name, or ``None`` if no partition config exists.
    """
    partition_by = config.get("partition_by")

    if partition_by is None:
        return None

    if isinstance(partition_by, str):
        stripped = partition_by.strip()
        return stripped if stripped else None

    if isinstance(partition_by, dict):
        field = partition_by.get("field")
        if isinstance(field, str) and field.strip():
            return field.strip()
        return None

    if isinstance(partition_by, list) and partition_by:
        first = partition_by[0]
        if isinstance(first, str) and first.strip():
            return first.strip()
        if isinstance(first, dict):
            field = first.get("field")
            if isinstance(field, str) and field.strip():
                return field.strip()
        return None

    return None


def _resolve_dbt_dependencies(
    depends_on: dict[str, Any],
    manifest: dict[str, Any],
) -> list[str]:
    """Convert dbt ``depends_on.nodes`` unique IDs to IronLayer canonical names.

    Only model-type dependencies are included.  Sources are resolved to their
    ``schema.name`` canonical form.  Tests, snapshots, and other resource types
    are excluded since they are not part of the IronLayer DAG.

    Parameters
    ----------
    depends_on:
        The ``depends_on`` dict from a dbt manifest node.
    manifest:
        The full manifest dict (used to look up referenced nodes).

    Returns
    -------
    list[str]
        Deduplicated, sorted list of canonical dependency names.
    """
    node_ids: list[str] = depends_on.get("nodes", [])
    nodes = manifest.get("nodes", {})
    sources = manifest.get("sources", {})
    seen: set[str] = set()
    deps: list[str] = []

    for uid in node_ids:
        if uid in seen:
            continue
        seen.add(uid)

        # Look up the referenced node or source to get its canonical name.
        if uid in nodes:
            ref_node = nodes[uid]
            canonical = _build_canonical_name(ref_node)
            deps.append(canonical)
        elif uid in sources:
            source_node = sources[uid]
            source_schema = source_node.get("schema", source_node.get("source_name", ""))
            source_name = source_node.get("name", "")
            if source_schema and source_name:
                deps.append(f"{source_schema}.{source_name}")
            elif source_name:
                deps.append(source_name)
        else:
            # The ID might reference a resource type we don't have in our
            # lookup (e.g. a seed, snapshot, or metric).  Derive a canonical
            # name from the unique_id structure: ``type.project.name``.
            parts = uid.split(".")
            if len(parts) >= 3:
                deps.append(parts[-1])
            else:
                logger.debug(
                    "Skipping unresolvable dependency '%s': not found in " "manifest nodes or sources.",
                    uid,
                )

    deps.sort()
    return deps


def _build_canonical_name(node: dict[str, Any]) -> str:
    """Combine schema and model name into a IronLayer canonical identifier.

    The canonical format is ``schema.name`` when a schema is present,
    otherwise just ``name``.

    Parameters
    ----------
    node:
        A single node dict from the dbt manifest.

    Returns
    -------
    str
        The canonical model name, e.g. ``"analytics.orders_daily"``.
    """
    schema = (node.get("schema") or "").strip()
    name = (node.get("name") or "").strip()

    if not name:
        # Fall back to unique_id parsing if name is missing.
        uid = node.get("unique_id", "")
        parts = uid.split(".")
        name = parts[-1] if parts else ""

    if schema:
        return f"{schema}.{name}"
    return name


def _compute_content_hash(sql: str) -> str:
    """Return the SHA-256 hex digest of the given SQL string."""
    return hashlib.sha256(sql.encode("utf-8")).hexdigest()


def _extract_columns(node: dict[str, Any]) -> list[str]:
    """Extract output column names from a dbt node.

    Parameters
    ----------
    node:
        A single node dict from the dbt manifest.

    Returns
    -------
    list[str]
        Sorted list of column names for deterministic output.
    """
    columns = node.get("columns", {})
    if not isinstance(columns, dict):
        return []
    return sorted(columns.keys())


def _extract_tags(config: dict[str, Any], node: dict[str, Any]) -> list[str]:
    """Extract tags from both the node config and top-level node fields.

    dbt stores tags in ``config.tags`` and sometimes in the top-level
    ``tags`` field.  We merge both, deduplicate, and sort.

    Parameters
    ----------
    config:
        The ``config`` dict from a dbt manifest node.
    node:
        The full dbt manifest node.

    Returns
    -------
    list[str]
        Sorted, deduplicated tag list.
    """
    config_tags = config.get("tags", [])
    node_tags = node.get("tags", [])

    if not isinstance(config_tags, list):
        config_tags = []
    if not isinstance(node_tags, list):
        node_tags = []

    all_tags: set[str] = set()
    for tag in config_tags + node_tags:
        if isinstance(tag, str) and tag.strip():
            all_tags.add(tag.strip())

    return sorted(all_tags)


def _extract_owner(node: dict[str, Any]) -> str | None:
    """Extract the model owner from a dbt node's meta config.

    dbt models can declare ownership via ``meta.owner`` at the node level
    or inside the config block.  We check both locations.

    Parameters
    ----------
    node:
        A single node dict from the dbt manifest.

    Returns
    -------
    str or None
    """
    # Check node-level meta first, then config-level meta.
    for meta_source in (node.get("meta"), node.get("config", {}).get("meta")):
        if isinstance(meta_source, dict):
            owner = meta_source.get("owner")
            if isinstance(owner, str) and owner.strip():
                return owner.strip()
    return None


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def parse_dbt_node(
    node: dict[str, Any],
    manifest: dict[str, Any],
) -> ModelDefinition | None:
    """Convert a single dbt manifest node to a IronLayer ModelDefinition.

    Parameters
    ----------
    node:
        A single node dict from manifest["nodes"].
    manifest:
        The full manifest dict (needed to resolve depends_on references).

    Returns
    -------
    ModelDefinition or None
        Returns None if the node should be skipped (e.g., ephemeral models,
        non-model resources).
    """
    resource_type = node.get("resource_type", "")
    if resource_type != "model":
        return None

    config = node.get("config", {})
    if not isinstance(config, dict):
        config = {}

    materialized = config.get("materialized", "table")
    if materialized == "ephemeral":
        logger.debug(
            "Skipping ephemeral model '%s'.",
            node.get("unique_id", "<unknown>"),
        )
        return None

    # Map dbt materialisation to IronLayer enums.
    try:
        kind, mat = _map_dbt_materialization(config)
    except DbtManifestError as exc:
        logger.warning(
            "Skipping model '%s': %s",
            node.get("unique_id", "<unknown>"),
            exc,
        )
        return None

    canonical_name = _build_canonical_name(node)
    if not canonical_name:
        logger.warning(
            "Skipping node with empty canonical name: %s",
            node.get("unique_id", "<unknown>"),
        )
        return None

    # Extract SQL -- prefer compiled_sql (fully resolved), fall back to raw_sql.
    # dbt v1.5+ uses "compiled_code" / "raw_code" instead of "compiled_sql" / "raw_sql".
    compiled_sql = node.get("compiled_code") or node.get("compiled_sql") or ""
    raw_sql = node.get("raw_code") or node.get("raw_sql") or ""

    # Use compiled SQL as the "clean" version since refs are already resolved.
    clean_sql = compiled_sql if compiled_sql else raw_sql
    content_hash = _compute_content_hash(clean_sql) if clean_sql else ""

    # Extract metadata.
    time_column = _extract_time_column(config)
    unique_key_raw = config.get("unique_key")
    unique_key: str | None = None
    if isinstance(unique_key_raw, str) and unique_key_raw.strip():
        unique_key = unique_key_raw.strip()
    elif isinstance(unique_key_raw, list) and unique_key_raw:
        # Some dbt configs use a list of unique key columns.
        unique_key = ", ".join(str(k).strip() for k in unique_key_raw if str(k).strip())
        if not unique_key:
            unique_key = None

    partition_by_str: str | None = None
    partition_raw = config.get("partition_by")
    if isinstance(partition_raw, str) and partition_raw.strip():
        partition_by_str = partition_raw.strip()
    elif isinstance(partition_raw, dict):
        field = partition_raw.get("field")
        if isinstance(field, str) and field.strip():
            partition_by_str = field.strip()
    elif isinstance(partition_raw, list) and partition_raw:
        parts = []
        for p in partition_raw:
            if isinstance(p, str) and p.strip():
                parts.append(p.strip())
            elif isinstance(p, dict):
                f = p.get("field")
                if isinstance(f, str) and f.strip():
                    parts.append(f.strip())
        if parts:
            partition_by_str = ", ".join(parts)

    incremental_strategy = config.get("incremental_strategy")
    if isinstance(incremental_strategy, str) and incremental_strategy.strip():
        incremental_strategy = incremental_strategy.strip()
    else:
        incremental_strategy = None

    owner = _extract_owner(node)
    tags = _extract_tags(config, node)
    output_columns = _extract_columns(node)

    # Resolve dependencies.
    depends_on = node.get("depends_on", {})
    if not isinstance(depends_on, dict):
        depends_on = {}
    dependencies = _resolve_dbt_dependencies(depends_on, manifest)

    # The file_path from dbt is relative to the project root.
    file_path = node.get("path") or node.get("original_file_path") or ""

    # For raw_sql, if dbt's raw_sql is empty use the compiled version.
    effective_raw_sql = raw_sql if raw_sql else clean_sql
    if not effective_raw_sql:
        logger.warning(
            "Model '%s' has no SQL content; skipping.",
            canonical_name,
        )
        return None

    # The referenced_tables are the resolved canonical names of dependencies.
    # This matches what the native IronLayer loader populates.
    referenced_tables = list(dependencies)

    return ModelDefinition(
        name=canonical_name,
        kind=kind,
        materialization=mat,
        time_column=time_column,
        unique_key=unique_key,
        partition_by=partition_by_str,
        incremental_strategy=incremental_strategy,
        owner=owner,
        tags=tags,
        dependencies=dependencies,
        file_path=file_path,
        raw_sql=effective_raw_sql,
        clean_sql=clean_sql,
        content_hash=content_hash,
        referenced_tables=referenced_tables,
        output_columns=output_columns,
    )


def load_models_from_dbt_manifest(
    manifest_path: Path,
    *,
    project_filter: str | None = None,
    tag_filter: list[str] | None = None,
) -> list[ModelDefinition]:
    """Load model definitions from a dbt manifest.json file.

    Parameters
    ----------
    manifest_path:
        Path to the dbt manifest.json file.
    project_filter:
        If provided, only load models from this dbt project.
    tag_filter:
        If provided, only load models that have at least one of these tags.

    Returns
    -------
    list[ModelDefinition]
        Fully-parsed model definitions sorted by name.

    Raises
    ------
    DbtManifestError
        If the manifest file is invalid or cannot be read.
    """
    if not manifest_path.is_file():
        raise DbtManifestError(f"Manifest file does not exist or is not a file: '{manifest_path}'")

    try:
        raw_bytes = manifest_path.read_bytes()
    except OSError as exc:
        raise DbtManifestError(f"Failed to read manifest file '{manifest_path}': {exc}") from exc

    try:
        manifest = json.loads(raw_bytes)
    except (json.JSONDecodeError, UnicodeDecodeError) as exc:
        raise DbtManifestError(f"Manifest file '{manifest_path}' is not valid JSON: {exc}") from exc

    if not isinstance(manifest, dict):
        raise DbtManifestError(f"Manifest file '{manifest_path}' root element is not a JSON object.")

    nodes = manifest.get("nodes")
    if nodes is None:
        raise DbtManifestError(
            f"Manifest file '{manifest_path}' does not contain a 'nodes' key. "
            f"Ensure this is a dbt manifest.json artifact (v1-v12 supported)."
        )

    if not isinstance(nodes, dict):
        raise DbtManifestError(f"Manifest 'nodes' must be a JSON object, got {type(nodes).__name__}.")

    # Optional: log the manifest metadata version for debugging.
    metadata = manifest.get("metadata", {})
    if isinstance(metadata, dict):
        dbt_version = metadata.get("dbt_version", "unknown")
        schema_version = metadata.get("dbt_schema_version", "unknown")
        logger.info(
            "Parsing dbt manifest (dbt_version=%s, schema_version=%s) " "with %d node(s).",
            dbt_version,
            schema_version,
            len(nodes),
        )

    tag_filter_set: frozenset[str] | None = None
    if tag_filter:
        tag_filter_set = frozenset(t.strip() for t in tag_filter if t.strip())
        if not tag_filter_set:
            tag_filter_set = None

    models: list[ModelDefinition] = []
    skipped_project = 0
    skipped_tag = 0
    skipped_parse = 0

    for node_id, node in nodes.items():
        if not isinstance(node, dict):
            logger.debug("Skipping non-dict node entry: '%s'.", node_id)
            skipped_parse += 1
            continue

        # Project filter: dbt unique_id format is ``model.project_name.model_name``.
        if project_filter:
            uid: str = node.get("unique_id", node_id) or node_id
            parts = uid.split(".")
            # The project name is the second segment in the unique_id.
            node_project = parts[1] if len(parts) >= 3 else ""
            if node_project != project_filter:
                skipped_project += 1
                continue

        # Tag filter: check both config.tags and top-level tags before full parse.
        if tag_filter_set:
            config = node.get("config", {})
            config_tags = config.get("tags", []) if isinstance(config, dict) else []
            node_tags = node.get("tags", [])
            if not isinstance(config_tags, list):
                config_tags = []
            if not isinstance(node_tags, list):
                node_tags = []

            all_node_tags = {t.strip() for t in config_tags + node_tags if isinstance(t, str) and t.strip()}
            if not all_node_tags.intersection(tag_filter_set):
                skipped_tag += 1
                continue

        model = parse_dbt_node(node, manifest)
        if model is not None:
            models.append(model)
        else:
            skipped_parse += 1

    # Sort by name for deterministic ordering.
    models.sort(key=lambda m: m.name)

    logger.info(
        "Loaded %d model(s) from dbt manifest '%s' "
        "(skipped: %d project-filtered, %d tag-filtered, %d non-model/unparseable).",
        len(models),
        manifest_path,
        skipped_project,
        skipped_tag,
        skipped_parse,
    )

    return models


def discover_dbt_manifest(project_dir: Path) -> Path | None:
    """Locate the manifest.json file in a dbt project directory.

    Searches in common locations:

    1. ``project_dir/target/manifest.json``
    2. ``project_dir/manifest.json``
    3. ``project_dir/dbt_packages/*/target/manifest.json``

    Parameters
    ----------
    project_dir:
        Root directory of the dbt project.

    Returns
    -------
    Path or None
        The path to the first manifest.json found, or ``None`` if none exists.
    """
    if not project_dir.is_dir():
        logger.debug("dbt project directory does not exist: '%s'.", project_dir)
        return None

    # 1. Standard dbt target directory.
    standard = project_dir / "target" / "manifest.json"
    if standard.is_file():
        logger.debug("Found manifest at standard location: '%s'.", standard)
        return standard

    # 2. Root-level manifest (sometimes placed here by CI/CD or manual copy).
    root_level = project_dir / "manifest.json"
    if root_level.is_file():
        logger.debug("Found manifest at root level: '%s'.", root_level)
        return root_level

    # 3. Packages -- useful for monorepos with multiple dbt packages.
    packages_dir = project_dir / "dbt_packages"
    if packages_dir.is_dir():
        # Sort for deterministic selection when multiple packages exist.
        for pkg_dir in sorted(packages_dir.iterdir()):
            candidate = pkg_dir / "target" / "manifest.json"
            if candidate.is_file():
                logger.debug("Found manifest in dbt package: '%s'.", candidate)
                return candidate

    logger.debug("No dbt manifest.json found under '%s'.", project_dir)
    return None

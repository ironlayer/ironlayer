"""Framework auto-detector — route a project directory to the right loader.

Determines which transformation framework a project uses (IronLayer, dbt,
SQLMesh, or raw SQL) from filesystem heuristics, then delegates model loading
to the appropriate loader without requiring the framework to be installed.

Detection priority (first match wins):

1. **IronLayer** — ``ironlayer.yaml`` present, OR ``models/`` dir containing
   ``.sql`` files whose first non-blank line matches ``-- name:`` header pattern.
2. **dbt** — ``dbt_project.yml`` present in the directory or any ancestor up
   to ``depth`` levels.
3. **SQLMesh** — ``.sqlmesh/`` directory present, OR ``config.yaml`` /
   ``config.yml`` containing a ``model_defaults`` key.
4. **Raw SQL** — fallback when no framework markers are found.

Typical usage::

    from core_engine.loader.framework_detector import detect_framework, load_models_auto

    result = detect_framework(Path("my-project/"))
    print(result.framework)  # e.g. FrameworkKind.DBT

    models = load_models_auto(Path("my-project/"))
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any

from core_engine.models.model_definition import ModelDefinition

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Framework kind enum
# ---------------------------------------------------------------------------


class FrameworkKind(str, Enum):
    """Supported transformation frameworks."""

    IRONLAYER = "ironlayer"
    DBT = "dbt"
    SQLMESH = "sqlmesh"
    RAW_SQL = "raw_sql"

    def __str__(self) -> str:  # noqa: D105
        return self.value


# ---------------------------------------------------------------------------
# Detection result
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class DetectionResult:
    """Outcome of a framework detection pass.

    Attributes
    ----------
    framework:
        The detected framework kind.
    project_root:
        Canonical project root (resolved ``Path``).
    confidence:
        Float in [0.0, 1.0] — how confident the detector is.  1.0 = definitive
        marker found; 0.5 = heuristic match; 0.0 = fallback (raw_sql).
    markers:
        Filesystem paths that triggered the detection (for diagnostics).
    """

    framework: FrameworkKind
    project_root: Path
    confidence: float = 1.0
    markers: list[Path] = field(default_factory=list)

    def __str__(self) -> str:  # noqa: D105
        marker_str = ", ".join(str(m) for m in self.markers[:3])
        return f"DetectionResult(framework={self.framework}, confidence={self.confidence:.2f}, markers=[{marker_str}])"


# ---------------------------------------------------------------------------
# Detection helpers
# ---------------------------------------------------------------------------

# Matches an IronLayer YAML-style comment header line: ``-- name: something``
_IL_NAME_HEADER_RE = re.compile(r"^--\s+name\s*:", re.IGNORECASE)

# Matches a SQLMesh MODEL() DDL block
_SM_MODEL_BLOCK_RE = re.compile(r"\bMODEL\s*\(", re.IGNORECASE)


def _is_ironlayer_project(root: Path) -> tuple[bool, list[Path]]:
    """Return True + markers if the directory looks like an IronLayer project."""
    markers: list[Path] = []

    # Definitive marker: ironlayer.yaml
    config = root / "ironlayer.yaml"
    if config.exists():
        markers.append(config)
        return True, markers

    # Heuristic: models/ dir has at least one .sql file with ``-- name:`` header
    models_dir = root / "models"
    if models_dir.is_dir():
        for sql_file in list(models_dir.rglob("*.sql"))[:20]:
            try:
                first_lines = sql_file.read_text(encoding="utf-8", errors="ignore").splitlines()[:5]
            except OSError:
                continue
            for line in first_lines:
                if _IL_NAME_HEADER_RE.match(line.strip()):
                    markers.append(sql_file)
                    break
            if markers:
                return True, markers

    return False, markers


def _is_dbt_project(root: Path, max_depth: int = 3) -> tuple[bool, list[Path]]:
    """Return True + markers if the directory or an ancestor looks like a dbt project."""
    markers: list[Path] = []
    current = root.resolve()

    for _ in range(max_depth + 1):
        candidate = current / "dbt_project.yml"
        if candidate.exists():
            markers.append(candidate)
            return True, markers
        parent = current.parent
        if parent == current:
            break
        current = parent

    return False, markers


def _is_sqlmesh_project(root: Path) -> tuple[bool, list[Path]]:
    """Return True + markers if the directory looks like a SQLMesh project."""
    markers: list[Path] = []

    # Definitive marker: .sqlmesh/ directory
    sqlmesh_dir = root / ".sqlmesh"
    if sqlmesh_dir.is_dir():
        markers.append(sqlmesh_dir)
        return True, markers

    # Secondary: config.yaml / config.yml with model_defaults key
    for cfg_name in ("config.yaml", "config.yml"):
        cfg = root / cfg_name
        if not cfg.exists():
            continue
        try:
            text = cfg.read_text(encoding="utf-8", errors="ignore")
            if "model_defaults" in text:
                markers.append(cfg)
                return True, markers
        except OSError:
            continue

    # Tertiary: models/ dir has .sql files with MODEL() blocks
    models_dir = root / "models"
    if models_dir.is_dir():
        for sql_file in list(models_dir.rglob("*.sql"))[:10]:
            try:
                text = sql_file.read_text(encoding="utf-8", errors="ignore")
            except OSError:
                continue
            if _SM_MODEL_BLOCK_RE.search(text):
                markers.append(sql_file)
                return True, markers

    return False, markers


# ---------------------------------------------------------------------------
# Public API: detection
# ---------------------------------------------------------------------------


def detect_framework(
    project_root: Path,
    *,
    hint: FrameworkKind | None = None,
) -> DetectionResult:
    """Detect the transformation framework used in *project_root*.

    Parameters
    ----------
    project_root:
        Root directory of the project to analyse.
    hint:
        Optional caller-supplied override.  When provided, the detection logic
        is skipped and a ``DetectionResult`` with ``confidence=1.0`` is returned
        immediately.

    Returns
    -------
    DetectionResult
        The detected framework, project root, confidence, and marker files.
    """
    root = project_root.resolve()

    if hint is not None:
        logger.debug("Framework detection bypassed by caller hint: %s", hint)
        return DetectionResult(framework=hint, project_root=root, confidence=1.0)

    # --- Priority 1: IronLayer ---
    is_il, il_markers = _is_ironlayer_project(root)
    if is_il:
        confidence = 1.0 if any(m.name == "ironlayer.yaml" for m in il_markers) else 0.8
        result = DetectionResult(
            framework=FrameworkKind.IRONLAYER,
            project_root=root,
            confidence=confidence,
            markers=il_markers,
        )
        logger.info("Detected framework: %s", result)
        return result

    # --- Priority 2: dbt ---
    is_dbt, dbt_markers = _is_dbt_project(root)
    if is_dbt:
        result = DetectionResult(
            framework=FrameworkKind.DBT,
            project_root=root,
            confidence=1.0,
            markers=dbt_markers,
        )
        logger.info("Detected framework: %s", result)
        return result

    # --- Priority 3: SQLMesh ---
    is_sm, sm_markers = _is_sqlmesh_project(root)
    if is_sm:
        confidence = 1.0 if any(m.name == ".sqlmesh" for m in sm_markers) else 0.85
        result = DetectionResult(
            framework=FrameworkKind.SQLMESH,
            project_root=root,
            confidence=confidence,
            markers=sm_markers,
        )
        logger.info("Detected framework: %s", result)
        return result

    # --- Fallback: raw SQL ---
    result = DetectionResult(
        framework=FrameworkKind.RAW_SQL,
        project_root=root,
        confidence=0.0,
    )
    logger.info("Framework not detected — treating as raw SQL: %s", result)
    return result


# ---------------------------------------------------------------------------
# Public API: unified model loading
# ---------------------------------------------------------------------------


def load_models_auto(
    project_root: Path,
    *,
    framework: FrameworkKind | None = None,
    dbt_manifest_path: Path | None = None,
    sqlmesh_tag_filter: str | None = None,
    models_dir: str = "models",
) -> tuple[DetectionResult, list[ModelDefinition]]:
    """Detect the framework and load all models from *project_root*.

    Parameters
    ----------
    project_root:
        Root directory of the project.
    framework:
        Optional caller-supplied framework override (skips detection).
    dbt_manifest_path:
        Explicit path to a dbt ``manifest.json``.  When not provided, the
        dbt loader will attempt auto-discovery inside *project_root*.
    sqlmesh_tag_filter:
        Optional tag to filter SQLMesh models (e.g. ``"prod"``).
    models_dir:
        Subdirectory name to search for IronLayer or raw SQL model files.
        Defaults to ``"models"``.

    Returns
    -------
    tuple[DetectionResult, list[ModelDefinition]]
        Detection metadata and sorted list of loaded model definitions.

    Raises
    ------
    FrameworkDetectionError
        If an explicit ``framework`` is supplied but the project directory
        does not meet the expected structure, or if loading fails.
    """
    detection = detect_framework(project_root, hint=framework)
    root = detection.project_root
    models: list[ModelDefinition] = []

    if detection.framework == FrameworkKind.DBT:
        from core_engine.loader.dbt_loader import (
            DbtManifestError,
            discover_dbt_manifest,
            load_models_from_dbt_manifest,
        )

        manifest = dbt_manifest_path or discover_dbt_manifest(root)
        if manifest is None:
            raise FrameworkDetectionError(
                f"dbt project detected at '{root}' but no manifest.json found. "
                "Run `dbt compile` or `dbt run` to generate it, then retry."
            )
        try:
            models = load_models_from_dbt_manifest(manifest)
        except DbtManifestError as exc:
            raise FrameworkDetectionError(f"Failed to load dbt models: {exc}") from exc

    elif detection.framework == FrameworkKind.SQLMESH:
        from core_engine.loader.sqlmesh_loader import (
            SQLMeshLoadError,
            load_models_from_sqlmesh_project,
        )

        try:
            models = load_models_from_sqlmesh_project(root, tag_filter=sqlmesh_tag_filter)
        except SQLMeshLoadError as exc:
            raise FrameworkDetectionError(f"Failed to load SQLMesh models: {exc}") from exc

    elif detection.framework in (FrameworkKind.IRONLAYER, FrameworkKind.RAW_SQL):
        from core_engine.loader.model_loader import (
            ModelLoadError,
            load_models_from_directory,
        )

        search_dir = root / models_dir
        if not search_dir.is_dir():
            # Try the root itself as the model directory
            search_dir = root
        try:
            models = load_models_from_directory(search_dir)
        except ModelLoadError as exc:
            raise FrameworkDetectionError(f"Failed to load models from '{search_dir}': {exc}") from exc

    logger.info(
        "Loaded %d model(s) from %s project at '%s'.",
        len(models),
        detection.framework,
        root,
    )
    return detection, models


# ---------------------------------------------------------------------------
# Exception
# ---------------------------------------------------------------------------


class FrameworkDetectionError(Exception):
    """Raised when framework detection or model loading fails."""


# ---------------------------------------------------------------------------
# Convenience helper: framework metadata
# ---------------------------------------------------------------------------


def framework_info(kind: FrameworkKind) -> dict[str, Any]:
    """Return a human-readable metadata dict for a given framework kind.

    Useful for CLI output and API responses.

    Parameters
    ----------
    kind:
        The framework to describe.

    Returns
    -------
    dict[str, Any]
        Keys: ``name``, ``description``, ``config_file``, ``model_extension``.
    """
    _INFO: dict[FrameworkKind, dict[str, Any]] = {
        FrameworkKind.IRONLAYER: {
            "name": "IronLayer",
            "description": "IronLayer native format with YAML comment headers",
            "config_file": "ironlayer.yaml",
            "model_extension": ".sql",
        },
        FrameworkKind.DBT: {
            "name": "dbt",
            "description": "dbt Core / dbt Cloud project (manifest.json required)",
            "config_file": "dbt_project.yml",
            "model_extension": ".sql",
        },
        FrameworkKind.SQLMESH: {
            "name": "SQLMesh",
            "description": "SQLMesh project with MODEL() DDL blocks",
            "config_file": "config.yaml or .sqlmesh/",
            "model_extension": ".sql",
        },
        FrameworkKind.RAW_SQL: {
            "name": "Raw SQL",
            "description": "Plain SQL files without a transformation framework",
            "config_file": None,
            "model_extension": ".sql",
        },
    }
    return _INFO[kind]

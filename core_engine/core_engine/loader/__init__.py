"""SQL model file loading, ref resolution, dbt manifest and SQLMesh project ingestion."""

from core_engine.loader.dbt_loader import (
    DbtManifestError,
    discover_dbt_manifest,
    load_models_from_dbt_manifest,
    parse_dbt_node,
)
from core_engine.loader.framework_detector import (
    DetectionResult,
    FrameworkDetectionError,
    FrameworkKind,
    detect_framework,
    framework_info,
    load_models_auto,
)
from core_engine.loader.model_loader import (
    HeaderParseError,
    ModelLoadError,
    load_models_from_directory,
    parse_model_file,
    parse_yaml_header,
)
from core_engine.loader.ref_resolver import (
    UnresolvedRefError,
    build_model_registry,
    resolve_refs,
)
from core_engine.loader.sqlmesh_loader import (
    SQLMeshLoadError,
    discover_sqlmesh_project,
    load_models_from_sqlmesh_project,
)

__all__ = [
    "DbtManifestError",
    "DetectionResult",
    "FrameworkDetectionError",
    "FrameworkKind",
    "HeaderParseError",
    "ModelLoadError",
    "SQLMeshLoadError",
    "UnresolvedRefError",
    "build_model_registry",
    "detect_framework",
    "discover_dbt_manifest",
    "discover_sqlmesh_project",
    "framework_info",
    "load_models_auto",
    "load_models_from_dbt_manifest",
    "load_models_from_directory",
    "load_models_from_sqlmesh_project",
    "parse_dbt_node",
    "parse_model_file",
    "parse_yaml_header",
    "resolve_refs",
]

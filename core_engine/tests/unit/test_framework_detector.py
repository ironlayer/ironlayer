"""Tests for the framework auto-detector module.

Coverage targets:
- detect_framework() for all four framework kinds
- Hint / override bypass
- load_models_auto() routing to correct loaders
- framework_info() metadata
- DetectionResult and FrameworkKind
- Edge cases: empty dirs, nested projects, ambiguous configs
"""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from core_engine.loader.framework_detector import (
    DetectionResult,
    FrameworkDetectionError,
    FrameworkKind,
    detect_framework,
    framework_info,
    load_models_auto,
)


# ---------------------------------------------------------------------------
# Fixtures — minimal project scaffolding
# ---------------------------------------------------------------------------


def _make_ironlayer_project(root: Path) -> Path:
    """Create a minimal IronLayer project structure."""
    (root / "ironlayer.yaml").write_text("version: 1\n")
    models = root / "models"
    models.mkdir()
    (models / "orders.sql").write_text(
        "-- name: orders\n-- kind: FULL_REFRESH\nSELECT 1 AS id\n"
    )
    return root


def _make_ironlayer_project_no_config(root: Path) -> Path:
    """IronLayer project identified only via -- name: header (no ironlayer.yaml)."""
    models = root / "models"
    models.mkdir()
    (models / "customers.sql").write_text(
        "-- name: customers\n-- kind: INCREMENTAL_BY_TIME_RANGE\nSELECT 2 AS id\n"
    )
    return root


def _make_dbt_project(root: Path) -> Path:
    """Create a minimal dbt project structure."""
    (root / "dbt_project.yml").write_text("name: my_project\nversion: '1.0.0'\n")
    (root / "models").mkdir()
    return root


def _make_sqlmesh_project_with_dir(root: Path) -> Path:
    """SQLMesh project with .sqlmesh/ directory marker."""
    (root / ".sqlmesh").mkdir()
    models = root / "models"
    models.mkdir()
    (models / "orders.sql").write_text(
        "MODEL (\n  name db.orders,\n  kind FULL\n);\nSELECT 1 AS id\n"
    )
    return root


def _make_sqlmesh_project_with_config(root: Path) -> Path:
    """SQLMesh project identified via config.yaml with model_defaults."""
    (root / "config.yaml").write_text(
        "model_defaults:\n  dialect: spark\n  start: 2020-01-01\n"
    )
    models = root / "models"
    models.mkdir()
    (models / "orders.sql").write_text(
        "MODEL (\n  name db.orders,\n  kind FULL\n);\nSELECT 1\n"
    )
    return root


def _make_sqlmesh_project_with_model_block(root: Path) -> Path:
    """SQLMesh project identified via MODEL() block in .sql files (no config)."""
    models = root / "models"
    models.mkdir()
    (models / "orders.sql").write_text(
        "MODEL (\n  name db.orders,\n  kind FULL\n);\nSELECT 1\n"
    )
    return root


def _make_raw_sql_project(root: Path) -> Path:
    """Raw SQL directory with no framework markers."""
    sql = root / "sql"
    sql.mkdir()
    (sql / "report.sql").write_text("SELECT * FROM something\n")
    return root


# ---------------------------------------------------------------------------
# FrameworkKind tests
# ---------------------------------------------------------------------------


class TestFrameworkKind:
    def test_str_values(self):
        assert str(FrameworkKind.IRONLAYER) == "ironlayer"
        assert str(FrameworkKind.DBT) == "dbt"
        assert str(FrameworkKind.SQLMESH) == "sqlmesh"
        assert str(FrameworkKind.RAW_SQL) == "raw_sql"

    def test_all_four_members(self):
        kinds = {k.value for k in FrameworkKind}
        assert kinds == {"ironlayer", "dbt", "sqlmesh", "raw_sql"}

    def test_enum_equality(self):
        assert FrameworkKind("dbt") == FrameworkKind.DBT

    def test_enum_is_str(self):
        assert isinstance(FrameworkKind.DBT, str)


# ---------------------------------------------------------------------------
# DetectionResult tests
# ---------------------------------------------------------------------------


class TestDetectionResult:
    def test_frozen(self, tmp_path):
        result = DetectionResult(
            framework=FrameworkKind.DBT,
            project_root=tmp_path,
            confidence=1.0,
        )
        with pytest.raises((AttributeError, TypeError)):
            result.framework = FrameworkKind.SQLMESH  # type: ignore[misc]

    def test_str_representation(self, tmp_path):
        result = DetectionResult(
            framework=FrameworkKind.DBT,
            project_root=tmp_path,
            confidence=0.9,
            markers=[tmp_path / "dbt_project.yml"],
        )
        s = str(result)
        assert "dbt" in s
        assert "0.90" in s

    def test_default_markers_empty(self, tmp_path):
        result = DetectionResult(framework=FrameworkKind.RAW_SQL, project_root=tmp_path)
        assert result.markers == []

    def test_confidence_default(self, tmp_path):
        result = DetectionResult(framework=FrameworkKind.DBT, project_root=tmp_path)
        assert result.confidence == 1.0


# ---------------------------------------------------------------------------
# detect_framework — IronLayer
# ---------------------------------------------------------------------------


class TestDetectFrameworkIronLayer:
    def test_detects_via_config_file(self, tmp_path):
        _make_ironlayer_project(tmp_path)
        result = detect_framework(tmp_path)
        assert result.framework == FrameworkKind.IRONLAYER
        assert result.confidence == 1.0
        assert any(m.name == "ironlayer.yaml" for m in result.markers)

    def test_detects_via_name_header(self, tmp_path):
        _make_ironlayer_project_no_config(tmp_path)
        result = detect_framework(tmp_path)
        assert result.framework == FrameworkKind.IRONLAYER
        assert result.confidence == 0.8

    def test_ironlayer_takes_priority_over_dbt(self, tmp_path):
        """If both ironlayer.yaml and dbt_project.yml exist, IronLayer wins."""
        _make_ironlayer_project(tmp_path)
        (tmp_path / "dbt_project.yml").write_text("name: x\n")
        result = detect_framework(tmp_path)
        assert result.framework == FrameworkKind.IRONLAYER

    def test_project_root_is_resolved(self, tmp_path):
        _make_ironlayer_project(tmp_path)
        result = detect_framework(tmp_path)
        assert result.project_root == tmp_path.resolve()


# ---------------------------------------------------------------------------
# detect_framework — dbt
# ---------------------------------------------------------------------------


class TestDetectFrameworkDbt:
    def test_detects_dbt_project(self, tmp_path):
        _make_dbt_project(tmp_path)
        result = detect_framework(tmp_path)
        assert result.framework == FrameworkKind.DBT
        assert result.confidence == 1.0
        assert any(m.name == "dbt_project.yml" for m in result.markers)

    def test_ancestor_dbt_project(self, tmp_path):
        """dbt_project.yml in a parent dir is discovered by the detector."""
        (tmp_path / "dbt_project.yml").write_text("name: x\n")
        subdir = tmp_path / "sub" / "models"
        subdir.mkdir(parents=True)
        result = detect_framework(subdir)
        assert result.framework == FrameworkKind.DBT

    def test_dbt_takes_priority_over_sqlmesh(self, tmp_path):
        """dbt_project.yml + .sqlmesh/ → dbt wins (IronLayer not present)."""
        _make_dbt_project(tmp_path)
        (tmp_path / ".sqlmesh").mkdir()
        result = detect_framework(tmp_path)
        assert result.framework == FrameworkKind.DBT


# ---------------------------------------------------------------------------
# detect_framework — SQLMesh
# ---------------------------------------------------------------------------


class TestDetectFrameworkSQLMesh:
    def test_detects_via_sqlmesh_dir(self, tmp_path):
        _make_sqlmesh_project_with_dir(tmp_path)
        result = detect_framework(tmp_path)
        assert result.framework == FrameworkKind.SQLMESH
        assert result.confidence == 1.0
        assert any(m.name == ".sqlmesh" for m in result.markers)

    def test_detects_via_config_yaml_model_defaults(self, tmp_path):
        _make_sqlmesh_project_with_config(tmp_path)
        result = detect_framework(tmp_path)
        assert result.framework == FrameworkKind.SQLMESH
        assert result.confidence == 0.85
        assert any(m.name == "config.yaml" for m in result.markers)

    def test_detects_via_model_block(self, tmp_path):
        _make_sqlmesh_project_with_model_block(tmp_path)
        result = detect_framework(tmp_path)
        assert result.framework == FrameworkKind.SQLMESH

    def test_config_yml_also_detected(self, tmp_path):
        (tmp_path / "config.yml").write_text("model_defaults:\n  dialect: spark\n")
        result = detect_framework(tmp_path)
        assert result.framework == FrameworkKind.SQLMESH

    def test_config_yaml_without_model_defaults_is_not_sqlmesh(self, tmp_path):
        """config.yaml without model_defaults key should NOT trigger SQLMesh detection."""
        (tmp_path / "config.yaml").write_text("version: 1\ndialect: spark\n")
        result = detect_framework(tmp_path)
        assert result.framework == FrameworkKind.RAW_SQL


# ---------------------------------------------------------------------------
# detect_framework — Raw SQL fallback
# ---------------------------------------------------------------------------


class TestDetectFrameworkRawSQL:
    def test_empty_directory_is_raw_sql(self, tmp_path):
        result = detect_framework(tmp_path)
        assert result.framework == FrameworkKind.RAW_SQL
        assert result.confidence == 0.0

    def test_raw_sql_project(self, tmp_path):
        _make_raw_sql_project(tmp_path)
        result = detect_framework(tmp_path)
        assert result.framework == FrameworkKind.RAW_SQL
        assert result.markers == []


# ---------------------------------------------------------------------------
# detect_framework — hint / override
# ---------------------------------------------------------------------------


class TestDetectFrameworkHint:
    def test_hint_bypasses_detection(self, tmp_path):
        """Even an empty directory is detected as dbt when hint=DBT."""
        result = detect_framework(tmp_path, hint=FrameworkKind.DBT)
        assert result.framework == FrameworkKind.DBT
        assert result.confidence == 1.0

    def test_hint_all_kinds(self, tmp_path):
        for kind in FrameworkKind:
            result = detect_framework(tmp_path, hint=kind)
            assert result.framework == kind

    def test_hint_does_not_set_markers(self, tmp_path):
        """Hint bypass skips filesystem scanning so no markers are collected."""
        result = detect_framework(tmp_path, hint=FrameworkKind.SQLMESH)
        assert result.markers == []


# ---------------------------------------------------------------------------
# load_models_auto — routing tests (mocked loaders)
# ---------------------------------------------------------------------------


class TestLoadModelsAutoRouting:
    """Verify load_models_auto delegates to the correct loader for each framework.

    Note: load_models_auto uses lazy imports (inside function bodies) so we must
    patch the functions at their *source* module locations, not at the
    framework_detector namespace.
    """

    def test_routes_to_dbt_loader(self, tmp_path):
        _make_dbt_project(tmp_path)
        fake_manifest = tmp_path / "target" / "manifest.json"
        fake_manifest.parent.mkdir()
        fake_manifest.write_text(
            json.dumps({"metadata": {"dbt_version": "1.7.0"}, "nodes": {}, "sources": {}})
        )
        mock_models = [MagicMock()]

        with patch(
            "core_engine.loader.dbt_loader.load_models_from_dbt_manifest",
            return_value=mock_models,
        ) as mock_load, patch(
            "core_engine.loader.dbt_loader.discover_dbt_manifest",
            return_value=fake_manifest,
        ):
            detection, models = load_models_auto(tmp_path)

        assert detection.framework == FrameworkKind.DBT
        mock_load.assert_called_once_with(fake_manifest)
        assert models is mock_models

    def test_routes_to_sqlmesh_loader(self, tmp_path):
        _make_sqlmesh_project_with_dir(tmp_path)
        mock_models = [MagicMock(), MagicMock()]

        with patch(
            "core_engine.loader.sqlmesh_loader.load_models_from_sqlmesh_project",
            return_value=mock_models,
        ) as mock_load:
            detection, models = load_models_auto(tmp_path)

        assert detection.framework == FrameworkKind.SQLMESH
        mock_load.assert_called_once_with(tmp_path.resolve(), tag_filter=None)
        assert models is mock_models

    def test_routes_to_model_loader_ironlayer(self, tmp_path):
        _make_ironlayer_project(tmp_path)
        mock_models = [MagicMock()]

        with patch(
            "core_engine.loader.model_loader.load_models_from_directory",
            return_value=mock_models,
        ) as mock_load:
            detection, models = load_models_auto(tmp_path)

        assert detection.framework == FrameworkKind.IRONLAYER
        mock_load.assert_called_once()
        assert models is mock_models

    def test_routes_to_model_loader_raw_sql(self, tmp_path):
        mock_models: list = []

        with patch(
            "core_engine.loader.model_loader.load_models_from_directory",
            return_value=mock_models,
        ) as mock_load:
            detection, models = load_models_auto(tmp_path)

        assert detection.framework == FrameworkKind.RAW_SQL
        mock_load.assert_called_once()
        assert models == []

    def test_explicit_framework_override(self, tmp_path):
        """framework= argument bypasses detection and forces the given loader."""
        _make_dbt_project(tmp_path)  # would normally detect dbt
        mock_models = [MagicMock()]

        with patch(
            "core_engine.loader.sqlmesh_loader.load_models_from_sqlmesh_project",
            return_value=mock_models,
        ):
            detection, models = load_models_auto(
                tmp_path, framework=FrameworkKind.SQLMESH
            )

        assert detection.framework == FrameworkKind.SQLMESH

    def test_sqlmesh_tag_filter_passed_through(self, tmp_path):
        _make_sqlmesh_project_with_dir(tmp_path)
        mock_models: list = []

        with patch(
            "core_engine.loader.sqlmesh_loader.load_models_from_sqlmesh_project",
            return_value=mock_models,
        ) as mock_load:
            load_models_auto(tmp_path, sqlmesh_tag_filter="prod")

        _, kwargs = mock_load.call_args
        assert kwargs.get("tag_filter") == "prod"


# ---------------------------------------------------------------------------
# load_models_auto — error propagation
# ---------------------------------------------------------------------------


class TestLoadModelsAutoErrors:
    def test_dbt_no_manifest_raises(self, tmp_path):
        _make_dbt_project(tmp_path)
        with patch(
            "core_engine.loader.dbt_loader.discover_dbt_manifest",
            return_value=None,
        ):
            with pytest.raises(FrameworkDetectionError, match="manifest.json"):
                load_models_auto(tmp_path)

    def test_dbt_manifest_load_error_wraps(self, tmp_path):
        from core_engine.loader.dbt_loader import DbtManifestError

        _make_dbt_project(tmp_path)
        with patch(
            "core_engine.loader.dbt_loader.discover_dbt_manifest",
            return_value=tmp_path / "target/manifest.json",
        ), patch(
            "core_engine.loader.dbt_loader.load_models_from_dbt_manifest",
            side_effect=DbtManifestError("bad manifest"),
        ):
            with pytest.raises(FrameworkDetectionError, match="dbt models"):
                load_models_auto(tmp_path)

    def test_sqlmesh_load_error_wraps(self, tmp_path):
        from core_engine.loader.sqlmesh_loader import SQLMeshLoadError

        _make_sqlmesh_project_with_dir(tmp_path)
        with patch(
            "core_engine.loader.sqlmesh_loader.load_models_from_sqlmesh_project",
            side_effect=SQLMeshLoadError("bad sqlmesh project"),
        ):
            with pytest.raises(FrameworkDetectionError, match="SQLMesh models"):
                load_models_auto(tmp_path)

    def test_model_load_error_wraps(self, tmp_path):
        from core_engine.loader.model_loader import ModelLoadError

        with patch(
            "core_engine.loader.model_loader.load_models_from_directory",
            side_effect=ModelLoadError("bad model dir"),
        ):
            with pytest.raises(FrameworkDetectionError):
                load_models_auto(tmp_path)

    def test_explicit_manifest_path_used(self, tmp_path):
        """Caller-supplied dbt_manifest_path skips discover_dbt_manifest."""
        _make_dbt_project(tmp_path)
        custom_manifest = tmp_path / "custom_manifest.json"
        custom_manifest.write_text("{}")

        with patch(
            "core_engine.loader.dbt_loader.load_models_from_dbt_manifest",
            return_value=[],
        ) as mock_load, patch(
            "core_engine.loader.dbt_loader.discover_dbt_manifest"
        ) as mock_discover:
            load_models_auto(tmp_path, dbt_manifest_path=custom_manifest)

        mock_load.assert_called_once_with(custom_manifest)
        mock_discover.assert_not_called()


# ---------------------------------------------------------------------------
# framework_info tests
# ---------------------------------------------------------------------------


class TestFrameworkInfo:
    def test_ironlayer_info(self):
        info = framework_info(FrameworkKind.IRONLAYER)
        assert info["name"] == "IronLayer"
        assert info["config_file"] == "ironlayer.yaml"
        assert info["model_extension"] == ".sql"

    def test_dbt_info(self):
        info = framework_info(FrameworkKind.DBT)
        assert info["name"] == "dbt"
        assert info["config_file"] == "dbt_project.yml"

    def test_sqlmesh_info(self):
        info = framework_info(FrameworkKind.SQLMESH)
        assert info["name"] == "SQLMesh"
        assert "config.yaml" in info["config_file"]

    def test_raw_sql_info(self):
        info = framework_info(FrameworkKind.RAW_SQL)
        assert info["name"] == "Raw SQL"
        assert info["config_file"] is None

    def test_all_kinds_have_required_keys(self):
        required = {"name", "description", "config_file", "model_extension"}
        for kind in FrameworkKind:
            info = framework_info(kind)
            assert required.issubset(info.keys()), f"Missing keys for {kind}"

    def test_all_kinds_have_nonempty_name(self):
        for kind in FrameworkKind:
            info = framework_info(kind)
            assert info["name"], f"Empty name for {kind}"


# ---------------------------------------------------------------------------
# __init__ re-export tests
# ---------------------------------------------------------------------------


class TestLoaderInitReExports:
    def test_detect_framework_importable_from_loader(self):
        from core_engine.loader import detect_framework as df  # noqa: F401

        assert callable(df)

    def test_load_models_auto_importable_from_loader(self):
        from core_engine.loader import load_models_auto as lma  # noqa: F401

        assert callable(lma)

    def test_framework_kind_importable_from_loader(self):
        from core_engine.loader import FrameworkKind as FK  # noqa: F401

        assert FK.DBT == FrameworkKind.DBT

    def test_detection_result_importable_from_loader(self):
        from core_engine.loader import DetectionResult as DR  # noqa: F401

        assert DR is DetectionResult

    def test_framework_info_importable_from_loader(self):
        from core_engine.loader import framework_info as fi  # noqa: F401

        assert callable(fi)

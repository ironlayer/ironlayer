"""Shared fixtures and import-time patching for CLI tests.

The core_engine.executor package fails to import in some environments
because of a Databricks SDK version mismatch.  We pre-inject a mock
module into sys.modules so that ``from core_engine.executor import
LocalExecutor`` resolves to a mock class that tests can configure.
"""

from __future__ import annotations

import sys
from types import ModuleType
from unittest.mock import MagicMock

# Pre-inject a mock for core_engine.executor if it cannot be imported
# normally (e.g. due to databricks-sdk version skew).
try:
    from core_engine.executor import LocalExecutor  # noqa: F401
except (ImportError, Exception):
    _mock_executor_module = ModuleType("core_engine.executor")
    _mock_executor_module.LocalExecutor = MagicMock  # type: ignore[attr-defined]
    _mock_executor_module.ExecutorInterface = MagicMock  # type: ignore[attr-defined]
    _mock_executor_module.DatabricksExecutor = MagicMock  # type: ignore[attr-defined]
    _mock_executor_module.RetryConfig = MagicMock  # type: ignore[attr-defined]
    _mock_executor_module.retry_with_backoff = MagicMock  # type: ignore[attr-defined]
    _mock_executor_module.ClusterTemplates = MagicMock  # type: ignore[attr-defined]
    _mock_executor_module.get_cluster_spec = MagicMock  # type: ignore[attr-defined]
    _mock_executor_module.get_cost_rate = MagicMock  # type: ignore[attr-defined]
    sys.modules["core_engine.executor"] = _mock_executor_module

    # Also inject sub-modules that may be imported directly.
    _mock_local_executor = ModuleType("core_engine.executor.local_executor")
    _mock_local_executor.LocalExecutor = MagicMock  # type: ignore[attr-defined]
    sys.modules["core_engine.executor.local_executor"] = _mock_local_executor

    _mock_base = ModuleType("core_engine.executor.base")
    _mock_base.ExecutorInterface = MagicMock  # type: ignore[attr-defined]
    sys.modules["core_engine.executor.base"] = _mock_base

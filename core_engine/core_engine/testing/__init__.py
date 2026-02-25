"""Model testing framework for IronLayer.

Provides declarative test assertions per model, DuckDB local execution,
and a pre-apply quality gate.
"""

from core_engine.testing.test_runner import ModelTestRunner, TestResult

__all__ = ["ModelTestRunner", "TestResult"]

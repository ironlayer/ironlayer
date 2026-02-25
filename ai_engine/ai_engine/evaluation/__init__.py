"""AI evaluation harness for regression testing of advisory engines.

Provides a curated gold dataset, metric computation utilities, and an
evaluation harness that runs all AI engines against the dataset to detect
quality degradation.  Designed for deterministic CI-gate execution: all
engines run in rule-based mode (no LLM) to ensure reproducibility.
"""

from __future__ import annotations

from ai_engine.evaluation.gold_dataset import GoldDataset, GoldDatasetEntry
from ai_engine.evaluation.harness import EvaluationHarness, EvaluationReport
from ai_engine.evaluation.metrics import (
    accuracy,
    confidence_calibration,
    confusion_matrix,
    mean_absolute_error,
    precision_recall_f1,
)

__all__ = [
    "GoldDataset",
    "GoldDatasetEntry",
    "EvaluationHarness",
    "EvaluationReport",
    "accuracy",
    "confidence_calibration",
    "confusion_matrix",
    "mean_absolute_error",
    "precision_recall_f1",
]

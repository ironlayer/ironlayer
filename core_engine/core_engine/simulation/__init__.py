"""What-if impact simulation for IronLayer models.

Provides column-change, model-removal, and type-change simulation
against the model dependency DAG.  All analysis is read-only -- no
mutations to plans, models, or the database.
"""

from __future__ import annotations

from core_engine.simulation.impact_analyzer import (
    AffectedModel,
    ChangeAction,
    ColumnChange,
    ContractViolation,
    ImpactAnalyzer,
    ImpactReport,
    ModelRemovalReport,
    ReferenceSeverity,
)

__all__ = [
    "AffectedModel",
    "ChangeAction",
    "ColumnChange",
    "ContractViolation",
    "ImpactAnalyzer",
    "ImpactReport",
    "ModelRemovalReport",
    "ReferenceSeverity",
]

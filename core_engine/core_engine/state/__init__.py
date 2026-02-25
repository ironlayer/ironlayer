"""State persistence layer using PostgreSQL."""

from core_engine.state.database import get_engine, get_session
from core_engine.state.repository import (
    AuditRepository,
    CredentialRepository,
    EnvironmentRepository,
    LockRepository,
    ModelRepository,
    PlanRepository,
    ReconciliationRepository,
    RunRepository,
    SnapshotRepository,
    TelemetryRepository,
    WatermarkRepository,
)

__all__ = [
    "AuditRepository",
    "CredentialRepository",
    "EnvironmentRepository",
    "LockRepository",
    "ModelRepository",
    "PlanRepository",
    "ReconciliationRepository",
    "RunRepository",
    "SnapshotRepository",
    "TelemetryRepository",
    "WatermarkRepository",
    "get_engine",
    "get_session",
]

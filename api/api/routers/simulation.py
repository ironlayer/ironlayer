"""Simulation router — what-if impact analysis endpoints.

Provides endpoints for exploring hypothetical changes to models
(column changes, model removal, type changes) without executing
anything.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

from api.dependencies import SessionDep, TenantDep
from api.middleware.rbac import Permission, require_permission
from api.services.simulation_service import SimulationService

router = APIRouter(
    prefix="/simulation",
    tags=["simulation"],
    dependencies=[Depends(require_permission(Permission.READ_MODELS))],
)


# ---------------------------------------------------------------------------
# Request / response schemas
# ---------------------------------------------------------------------------


class ColumnChangeRequest(BaseModel):
    """A single column change to simulate."""

    action: str = Field(..., description="Change action: ADD, REMOVE, RENAME, TYPE_CHANGE.")
    column_name: str = Field(..., description="Column being changed.")
    new_name: str | None = Field(default=None, description="New name for RENAME.")
    old_type: str | None = Field(default=None, description="Previous data type.")
    new_type: str | None = Field(default=None, description="New data type.")


class ColumnChangeSimulationRequest(BaseModel):
    """Request body for column change simulation."""

    source_model: str = Field(..., description="Model where the change originates.")
    changes: list[ColumnChangeRequest] = Field(..., min_length=1, description="Column changes to simulate.")


class ModelRemovalRequest(BaseModel):
    """Request body for model removal simulation."""

    model_name: str = Field(..., description="Model to simulate removing.")


class TypeChangeRequest(BaseModel):
    """Request body for type change simulation."""

    source_model: str = Field(..., description="Model where the type changes.")
    column_name: str = Field(..., description="Column whose type changes.")
    old_type: str = Field(..., description="Current data type.")
    new_type: str = Field(..., description="Proposed new data type.")


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@router.post("/column-change")
async def simulate_column_change(
    body: ColumnChangeSimulationRequest,
    session: SessionDep,
    tenant_id: TenantDep,
) -> dict[str, Any]:
    """Simulate column changes on a model and return impact analysis.

    Walks the dependency DAG downstream from the source model, checking
    each model's SQL and contracts for references to the changed columns.
    """
    service = SimulationService(session, tenant_id)
    report = await service.simulate_column_changes(
        source_model=body.source_model,
        changes=[c.model_dump() for c in body.changes],
    )
    return report.model_dump()


@router.post("/model-removal")
async def simulate_model_removal(
    body: ModelRemovalRequest,
    session: SessionDep,
    tenant_id: TenantDep,
) -> dict[str, Any]:
    """Simulate removing a model and identify downstream impact.

    Returns affected models, orphaned models (whose sole upstream
    dependency was the removed model), and a human-readable summary.
    """
    service = SimulationService(session, tenant_id)
    report = await service.simulate_model_removal(model_name=body.model_name)
    return report.model_dump()


@router.post("/type-change")
async def simulate_type_change(
    body: TypeChangeRequest,
    session: SessionDep,
    tenant_id: TenantDep,
) -> dict[str, Any]:
    """Simulate changing a column's data type and assess compatibility.

    Uses a type compatibility matrix to classify the change as safe
    (e.g. INT -> BIGINT) or breaking (e.g. STRING -> INT).
    """
    service = SimulationService(session, tenant_id)
    report = await service.simulate_type_change(
        source_model=body.source_model,
        column_name=body.column_name,
        old_type=body.old_type,
        new_type=body.new_type,
    )
    return report.model_dump()

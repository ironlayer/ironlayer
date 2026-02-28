"""Check Engine endpoints: run checks, view results, list check types.

Provides a unified API for executing quality checks across all check
types (model tests, schema contracts, etc.) through the check engine.
"""

from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, Field

from api.dependencies import SessionDep, TenantDep
from api.middleware.rbac import Permission, Role, require_permission
from api.services.check_service import CheckService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/checks", tags=["checks"])


# ---------------------------------------------------------------------------
# Request / response models
# ---------------------------------------------------------------------------


class RunChecksRequest(BaseModel):
    """Request body for running checks."""

    model_names: list[str] | None = Field(
        default=None,
        description="Run checks for specific models. None means all models.",
    )
    check_types: list[str] | None = Field(
        default=None,
        description="Run only specific check types (e.g. MODEL_TEST, SCHEMA_CONTRACT). None means all.",
    )


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@router.post("/run")
async def run_checks(
    body: RunChecksRequest,
    session: SessionDep,
    tenant_id: TenantDep,
    _role: Role = Depends(require_permission(Permission.RUN_CHECKS)),
) -> dict[str, Any]:
    """Run quality checks for specified models and check types.

    Returns a summary of check results including pass/fail/warn counts
    and whether any blocking failures were detected.
    """
    service = CheckService(session, tenant_id=tenant_id)
    return await service.run_checks(
        model_names=body.model_names,
        check_types=body.check_types,
    )


@router.get("/types")
async def list_check_types(
    session: SessionDep,
    tenant_id: TenantDep,
    _role: Role = Depends(require_permission(Permission.READ_CHECK_RESULTS)),
) -> list[dict[str, str]]:
    """List all available check types.

    Returns a list of check type descriptors with name and description.
    """
    service = CheckService(session, tenant_id=tenant_id)
    return service.get_available_types()


@router.get("/summary")
async def get_check_summary(
    session: SessionDep,
    tenant_id: TenantDep,
    _role: Role = Depends(require_permission(Permission.READ_CHECK_RESULTS)),
    model_name: str | None = Query(default=None, description="Filter by model name."),
) -> dict[str, Any]:
    """Get aggregate check statistics.

    Returns summary counts of recent check results.
    """
    service = CheckService(session, tenant_id=tenant_id)
    return await service.run_checks(
        model_names=[model_name] if model_name else None,
    )

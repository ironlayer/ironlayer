"""Service layer for the unified check engine.

Orchestrates check execution via the core engine's CheckEngine,
persists results, and provides query access for the API layer.
"""

from __future__ import annotations

import logging
from typing import Any

from core_engine.checks import (
    CheckContext,
    CheckSummary,
    CheckType,
    create_default_engine,
)
from core_engine.models.model_definition import ModelDefinition
from core_engine.state.repository import ModelRepository
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)


class CheckService:
    """High-level service for running and querying checks.

    Parameters
    ----------
    session:
        Active database session for persistence.
    tenant_id:
        Tenant scope for all operations.
    """

    def __init__(
        self,
        session: AsyncSession,
        *,
        tenant_id: str = "default",
    ) -> None:
        self._session = session
        self._tenant_id = tenant_id
        self._model_repo = ModelRepository(session, tenant_id=tenant_id)

    async def run_checks(
        self,
        model_names: list[str] | None = None,
        check_types: list[str] | None = None,
        models: list[ModelDefinition] | None = None,
    ) -> dict[str, Any]:
        """Run checks and return a serialisable summary.

        Parameters
        ----------
        model_names:
            Optional list of model names to check. None means all.
        check_types:
            Optional list of check type strings to run. None means all.
        models:
            Optional pre-loaded model definitions. When None, models
            are inferred from the model repository.

        Returns
        -------
        dict
            Serialised CheckSummary with results.
        """
        # Parse check type filters.
        parsed_types: list[CheckType] | None = None
        if check_types is not None:
            parsed_types = []
            for ct_str in check_types:
                try:
                    parsed_types.append(CheckType(ct_str))
                except ValueError:
                    logger.warning("Unknown check type requested: %s", ct_str)

        # Build context.
        context = CheckContext(
            models=models or [],
            check_types=parsed_types,
            model_names=model_names,
        )

        # Create engine and run.
        engine = create_default_engine()
        summary = await engine.run(context)

        return self._serialize_summary(summary)

    def get_available_types(self) -> list[dict[str, str]]:
        """Return all available check types.

        Returns
        -------
        list[dict]
            List of check type descriptors with name and description.
        """
        engine = create_default_engine()
        return [
            {
                "name": ct.value,
                "description": _CHECK_TYPE_DESCRIPTIONS.get(ct.value, ""),
            }
            for ct in engine.get_available_types()
        ]

    @staticmethod
    def _serialize_summary(summary: CheckSummary) -> dict[str, Any]:
        """Convert a CheckSummary to a JSON-serialisable dict."""
        return {
            "total": summary.total,
            "passed": summary.passed,
            "failed": summary.failed,
            "warned": summary.warned,
            "errored": summary.errored,
            "skipped": summary.skipped,
            "blocking_failures": summary.blocking_failures,
            "has_blocking_failures": summary.has_blocking_failures,
            "duration_ms": summary.duration_ms,
            "results": [
                {
                    "check_type": r.check_type.value,
                    "model_name": r.model_name,
                    "status": r.status.value,
                    "severity": r.severity.value,
                    "message": r.message,
                    "detail": r.detail,
                    "duration_ms": r.duration_ms,
                }
                for r in summary.results
            ],
        }


# Human-readable descriptions for each check type.
_CHECK_TYPE_DESCRIPTIONS: dict[str, str] = {
    "MODEL_TEST": "Declarative model tests (NOT_NULL, UNIQUE, ROW_COUNT, ACCEPTED_VALUES, CUSTOM_SQL).",
    "SCHEMA_CONTRACT": "Schema contract validation (column presence, type, nullability).",
    "SCHEMA_DRIFT": "Schema drift detection between expected and actual warehouse schemas.",
    "RECONCILIATION": "Control-plane vs warehouse status reconciliation.",
    "DATA_FRESHNESS": "Data freshness checks against staleness thresholds.",
    "CROSS_MODEL": "Cross-model referential integrity validation.",
    "VOLUME_ANOMALY": "Statistical row count anomaly detection.",
    "CUSTOM": "User-defined SQL validation rules.",
}

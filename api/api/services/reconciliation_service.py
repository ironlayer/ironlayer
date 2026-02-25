"""Service for reconciling control-plane run state against the execution backend.

Compares the status recorded in the ``runs`` table with the actual outcome
reported by the execution backend (Databricks).  Discrepancies are recorded
in the ``reconciliation_checks`` table for operator review and resolution.

Phase 3 extends this service with schema-level drift detection: comparing
expected model schemas (from contracts or model definitions) against actual
warehouse table schemas.
"""

from __future__ import annotations

import logging
import os
from typing import Any

from core_engine.executor.schema_introspector import (
    ColumnInfo,
    SchemaDrift,
    TableSchema,
    compare_schemas,
)
from core_engine.models.run import RunStatus
from core_engine.state.repository import (
    ModelRepository,
    ReconciliationRepository,
    RunRepository,
    SchemaDriftRepository,
)
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)


class ReconciliationService:
    """Compare control-plane run records against the execution backend.

    Parameters
    ----------
    session:
        Active database session.
    tenant_id:
        Tenant scope for all queries and checks.
    """

    def __init__(
        self,
        session: AsyncSession,
        *,
        tenant_id: str = "default",
    ) -> None:
        self._session = session
        self._tenant_id = tenant_id
        self._run_repo = RunRepository(session, tenant_id=tenant_id)
        self._recon_repo = ReconciliationRepository(session, tenant_id=tenant_id)
        self._drift_repo = SchemaDriftRepository(session, tenant_id=tenant_id)
        self._model_repo = ModelRepository(session, tenant_id=tenant_id)

    async def trigger_reconciliation(
        self,
        plan_id: str | None = None,
        hours_back: int = 24,
    ) -> dict[str, Any]:
        """Run reconciliation checks against recent runs.

        Checks all runs from the last *hours_back* hours (or all runs for
        a specific plan if *plan_id* is given).  For each run that has an
        ``external_run_id``, queries the execution backend for its actual
        status and compares.

        Returns a summary of the reconciliation results.
        """
        if plan_id:
            runs = await self._run_repo.get_by_plan(plan_id)
        else:
            runs = await self._get_recent_runs(hours_back)

        checked = 0
        discrepancies = 0
        matched = 0
        skipped = 0

        for run in runs:
            external_id = getattr(run, "external_run_id", None)
            if not external_id:
                skipped += 1
                continue

            try:
                warehouse_status = await self._verify_against_backend(external_id)
            except Exception as exc:
                logger.warning(
                    "Could not verify run %s (external=%s): %s",
                    run.run_id,
                    external_id,
                    exc,
                )
                skipped += 1
                continue

            checked += 1
            expected = run.status
            actual = warehouse_status.value

            if expected == actual:
                matched += 1
                await self._recon_repo.record_check(
                    run_id=run.run_id,
                    model_name=run.model_name,
                    expected_status=expected,
                    warehouse_status=actual,
                    discrepancy_type=None,
                )
            else:
                discrepancies += 1
                discrepancy_type = self._classify_discrepancy(expected, actual)
                await self._recon_repo.record_check(
                    run_id=run.run_id,
                    model_name=run.model_name,
                    expected_status=expected,
                    warehouse_status=actual,
                    discrepancy_type=discrepancy_type,
                )
                logger.warning(
                    "Reconciliation discrepancy for run %s model %s: " "control-plane=%s warehouse=%s type=%s",
                    run.run_id,
                    run.model_name,
                    expected,
                    actual,
                    discrepancy_type,
                )

        return {
            "total_runs": len(runs),
            "checked": checked,
            "matched": matched,
            "discrepancies": discrepancies,
            "skipped": skipped,
        }

    async def get_discrepancies(
        self,
        limit: int = 100,
    ) -> list[dict[str, Any]]:
        """Return unresolved discrepancies as serialisable dicts."""
        rows = await self._recon_repo.get_unresolved(limit=limit)
        return [
            {
                "id": row.id,
                "run_id": row.run_id,
                "model_name": row.model_name,
                "expected_status": row.expected_status,
                "warehouse_status": row.warehouse_status,
                "discrepancy_type": row.discrepancy_type,
                "checked_at": row.checked_at.isoformat() if row.checked_at else None,
            }
            for row in rows
        ]

    async def resolve_discrepancy(
        self,
        check_id: int,
        resolved_by: str,
        resolution_note: str,
    ) -> dict[str, Any] | None:
        """Mark a discrepancy as resolved. Returns the updated record or None."""
        row = await self._recon_repo.resolve(
            check_id=check_id,
            resolved_by=resolved_by,
            resolution_note=resolution_note,
        )
        if row is None:
            return None
        return {
            "id": row.id,
            "run_id": row.run_id,
            "model_name": row.model_name,
            "resolved": row.resolved,
            "resolved_by": row.resolved_by,
            "resolved_at": row.resolved_at.isoformat() if row.resolved_at else None,
            "resolution_note": row.resolution_note,
        }

    async def get_stats(self) -> dict[str, Any]:
        """Return reconciliation statistics."""
        return await self._recon_repo.get_stats()

    # -- Internal helpers -----------------------------------------------

    async def _get_recent_runs(self, hours_back: int) -> list:
        """Fetch runs from the last N hours.

        Uses a broad query approach: fetches recent plans and then their runs.
        """
        from core_engine.state.repository import PlanRepository

        plan_repo = PlanRepository(self._session, tenant_id=self._tenant_id)
        recent_plans = await plan_repo.list_recent(limit=50)

        all_runs = []
        for plan in recent_plans:
            runs = await self._run_repo.get_by_plan(plan.plan_id)
            all_runs.extend(runs)
        return all_runs

    async def _verify_against_backend(self, external_run_id: str) -> RunStatus:
        """Query the execution backend for the actual run status."""
        host = os.environ.get("PLATFORM_DATABRICKS_HOST")
        token = os.environ.get("PLATFORM_DATABRICKS_TOKEN")

        if not host or not token:
            raise RuntimeError("Databricks credentials not configured for reconciliation")

        from core_engine.executor.databricks_executor import DatabricksExecutor

        executor = DatabricksExecutor(host=host, token=token)
        return executor.verify_run(external_run_id)

    @staticmethod
    def _classify_discrepancy(expected: str, actual: str) -> str:
        """Classify the type of discrepancy between expected and actual status."""
        if expected == RunStatus.SUCCESS.value and actual == RunStatus.FAIL.value:
            return "phantom_success"
        if expected == RunStatus.FAIL.value and actual == RunStatus.SUCCESS.value:
            return "missed_success"
        if expected == RunStatus.RUNNING.value and actual == RunStatus.SUCCESS.value:
            return "stale_running"
        if expected == RunStatus.RUNNING.value and actual == RunStatus.FAIL.value:
            return "stale_running_failed"
        if expected == RunStatus.PENDING.value and actual in (
            RunStatus.SUCCESS.value,
            RunStatus.FAIL.value,
        ):
            return "stale_pending"
        return "status_mismatch"

    # -- Schema drift detection -------------------------------------------------

    async def check_schema_drift(
        self,
        model_name: str,
        actual_schema: TableSchema | None = None,
        expected_schema: TableSchema | None = None,
    ) -> dict[str, Any]:
        """Check schema drift for a single model.

        If *actual_schema* is not provided, the method returns a summary
        indicating that no actual schema was available for comparison (the
        caller is responsible for fetching the warehouse schema externally).

        If *expected_schema* is not provided, the method attempts to derive
        one from the most recent schema drift check that recorded expected
        columns.

        Returns a dict with drift details and persistence status.
        """
        model_row = await self._model_repo.get(model_name)
        if model_row is None:
            return {
                "model_name": model_name,
                "status": "model_not_found",
                "drifts": [],
            }

        if actual_schema is None:
            return {
                "model_name": model_name,
                "status": "no_actual_schema",
                "drifts": [],
            }

        # Build expected schema from explicit parameter or previous drift check.
        if expected_schema is None:
            expected_schema = await self._derive_expected_schema(model_name)

        # Perform actual comparison using compare_schemas when both schemas
        # are available.
        drifts: list[SchemaDrift] = []
        if expected_schema is not None and expected_schema.columns:
            drifts = compare_schemas(expected_schema, actual_schema)

        # Serialise drifts for persistence and response.
        drifts_serialised: list[dict[str, Any]] = [
            {
                "drift_type": d.drift_type,
                "column_name": d.column_name,
                "expected": d.expected,
                "actual": d.actual,
                "message": d.message,
            }
            for d in drifts
        ]

        # Classify overall drift type from individual drifts.
        if not drifts:
            drift_type = "NONE"
        elif any(d.drift_type == "COLUMN_REMOVED" for d in drifts):
            drift_type = "COLUMN_REMOVED"
        elif any(d.drift_type == "TYPE_CHANGED" for d in drifts):
            drift_type = "TYPE_CHANGED"
        elif any(d.drift_type == "COLUMN_ADDED" for d in drifts):
            drift_type = "COLUMN_ADDED"
        else:
            drift_type = drifts[0].drift_type

        # Build JSON representations for persistence.
        expected_json = (
            [
                {"name": c.name, "data_type": c.data_type, "nullable": c.nullable}
                for c in sorted(expected_schema.columns, key=lambda c: c.name.lower())
            ]
            if expected_schema is not None and expected_schema.columns
            else None
        )
        actual_json = (
            [
                {"name": c.name, "data_type": c.data_type, "nullable": c.nullable}
                for c in sorted(actual_schema.columns, key=lambda c: c.name.lower())
            ]
            if actual_schema.columns
            else None
        )

        # Record the check in the database for audit.
        row = await self._drift_repo.record_drift(
            model_name=model_name,
            expected_columns=expected_json,
            actual_columns=actual_json,
            drift_type=drift_type,
            drift_details={"drifts": drifts_serialised} if drifts_serialised else None,
        )

        return {
            "model_name": model_name,
            "status": "checked",
            "drift_type": drift_type,
            "drifts": drifts_serialised,
            "check_id": row.id,
        }

    async def _derive_expected_schema(self, model_name: str) -> TableSchema | None:
        """Attempt to derive an expected schema from previous drift checks.

        Looks for the most recent drift check that has ``expected_columns``
        recorded.  If found, reconstructs a :class:`TableSchema` from the
        persisted column definitions.

        Returns ``None`` if no previous expected schema is available.
        """
        try:
            recent_drifts = await self._drift_repo.get_unresolved(limit=100)
            for drift_row in recent_drifts:
                if drift_row.model_name != model_name:
                    continue
                expected_cols = getattr(drift_row, "expected_columns_json", None)
                if expected_cols and isinstance(expected_cols, list):
                    columns = [
                        ColumnInfo(
                            name=col["name"],
                            data_type=col.get("data_type", "UNKNOWN"),
                            nullable=col.get("nullable", True),
                        )
                        for col in expected_cols
                    ]
                    return TableSchema(table_name=model_name, columns=columns)
        except Exception:
            logger.debug(
                "Could not derive expected schema for %s from previous drift checks",
                model_name,
                exc_info=True,
            )
        return None

    async def check_all_schemas(
        self,
        model_names: list[str] | None = None,
    ) -> dict[str, Any]:
        """Check schema drift for all (or specified) models.

        This method iterates through models and records drift checks.
        Since actual warehouse schemas must be fetched externally, this
        creates placeholder records for each model indicating that a
        drift check was initiated.

        Returns a summary with counts of models checked and drifts found.
        """
        if model_names is None:
            all_models = await self._model_repo.list_all()
            model_names = [m.model_name for m in all_models]

        checked = 0
        drifts_found = 0
        results: list[dict[str, Any]] = []

        for name in sorted(model_names):
            result = await self.check_schema_drift(name)
            results.append(result)
            if result["status"] == "checked":
                checked += 1
                if result.get("drift_type", "NONE") != "NONE":
                    drifts_found += 1

        return {
            "models_requested": len(model_names),
            "models_checked": checked,
            "drifts_found": drifts_found,
            "results": results,
        }

    async def get_schema_drifts(self, limit: int = 100) -> list[dict[str, Any]]:
        """Return unresolved schema drifts as serialisable dicts."""
        rows = await self._drift_repo.get_unresolved(limit=limit)
        return [
            {
                "id": row.id,
                "model_name": row.model_name,
                "drift_type": row.drift_type,
                "drift_details": row.drift_details_json,
                "expected_columns": row.expected_columns_json,
                "actual_columns": row.actual_columns_json,
                "resolved": row.resolved,
                "checked_at": row.checked_at.isoformat() if row.checked_at else None,
            }
            for row in rows
        ]

    async def resolve_schema_drift(
        self,
        check_id: int,
        resolved_by: str,
        resolution_note: str,
    ) -> dict[str, Any] | None:
        """Resolve a schema drift check. Returns the updated record or None."""
        row = await self._drift_repo.resolve(
            check_id=check_id,
            resolved_by=resolved_by,
            resolution_note=resolution_note,
        )
        if row is None:
            return None
        return {
            "id": row.id,
            "model_name": row.model_name,
            "drift_type": row.drift_type,
            "resolved": row.resolved,
            "resolved_by": row.resolved_by,
            "resolved_at": row.resolved_at.isoformat() if row.resolved_at else None,
            "resolution_note": row.resolution_note,
        }

"""Abstract interface for SQL execution backends.

Every executor -- whether it targets a remote Databricks workspace or a local
DuckDB instance -- must satisfy the :class:`ExecutorInterface` protocol so that
the planner and orchestrator can remain backend-agnostic.
"""

from __future__ import annotations

from typing import Protocol

from core_engine.models.plan import PlanStep
from core_engine.models.run import RunRecord, RunStatus


class ExecutorInterface(Protocol):
    """Structural interface for SQL execution backends.

    Implementations are **not** required to subclass this protocol; they only
    need to expose methods with matching signatures (duck typing).
    """

    def execute_step(
        self,
        step: PlanStep,
        sql: str,
        parameters: dict[str, str],
        plan_id: str = "",
    ) -> RunRecord:
        """Execute a single plan step and return the completed run record.

        Parameters
        ----------
        step:
            The plan step describing the work to perform.
        sql:
            Rendered SQL statement to execute.
        parameters:
            Key-value pairs to substitute into the SQL template.
        plan_id:
            Identifier of the parent plan, propagated to the RunRecord.

        Returns
        -------
        RunRecord
            A record capturing the outcome, timing, and metadata of the run.
        """
        ...

    def poll_status(self, run_id: str) -> RunStatus:
        """Check the current lifecycle status of a running job.

        Parameters
        ----------
        run_id:
            The identifier returned when the job was submitted.
        """
        ...

    def cancel(self, run_id: str) -> None:
        """Request cancellation of a running job.

        Parameters
        ----------
        run_id:
            The identifier of the job to cancel.
        """
        ...

    def get_logs(self, run_id: str) -> str:
        """Retrieve execution logs for a completed or failed run.

        Parameters
        ----------
        run_id:
            The identifier of the run whose logs are requested.

        Returns
        -------
        str
            Raw log text.  May be empty if the backend does not persist logs.
        """
        ...

    def verify_run(self, run_id: str) -> RunStatus:
        """Verify the final status of a run against the execution backend.

        Used for reconciliation -- checks whether the backend agrees with
        the control plane's recorded outcome.

        Parameters
        ----------
        run_id:
            The external run identifier (e.g. Databricks run ID).

        Returns
        -------
        RunStatus
            The status as reported by the execution backend.
        """
        ...

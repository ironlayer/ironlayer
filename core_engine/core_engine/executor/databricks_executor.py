"""Databricks Jobs API 2.x executor for remote SQL model runs.

Submits SQL tasks to a Databricks workspace via the official SDK, polls for
completion, and maps Databricks lifecycle states back to the engine's
:class:`RunStatus` enum.  Token values are **never** written to log output.
"""

from __future__ import annotations

import logging
import time
from datetime import UTC, datetime
from uuid import uuid4

from databricks.sdk import WorkspaceClient
from databricks.sdk.service.jobs import (
    RunLifeCycleState,
    RunResultState,
    SqlTask,
    SqlTaskQuery,
    SubmitTask,
    TaskDependency,
)

from core_engine.executor.cluster_templates import get_cluster_spec
from core_engine.executor.retry import RetryConfig, retry_with_backoff
from core_engine.models.plan import Plan, PlanStep
from core_engine.models.run import RunRecord, RunStatus
from core_engine.parser.sql_guard import SQLGuardConfig, assert_sql_safe

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Mapping helpers
# ---------------------------------------------------------------------------

_TERMINAL_STATES: frozenset[RunLifeCycleState] = frozenset(
    {
        RunLifeCycleState.TERMINATED,
        RunLifeCycleState.SKIPPED,
        RunLifeCycleState.INTERNAL_ERROR,
    }
)

_RESULT_STATE_MAP: dict[RunResultState | None, RunStatus] = {
    RunResultState.SUCCESS: RunStatus.SUCCESS,
    RunResultState.FAILED: RunStatus.FAIL,
    RunResultState.TIMEDOUT: RunStatus.FAIL,
    RunResultState.CANCELED: RunStatus.CANCELLED,
    None: RunStatus.FAIL,
}

_LIFECYCLE_STATE_MAP: dict[RunLifeCycleState, RunStatus] = {
    RunLifeCycleState.PENDING: RunStatus.PENDING,
    RunLifeCycleState.RUNNING: RunStatus.RUNNING,
    RunLifeCycleState.TERMINATING: RunStatus.RUNNING,
    RunLifeCycleState.SKIPPED: RunStatus.CANCELLED,
    RunLifeCycleState.INTERNAL_ERROR: RunStatus.FAIL,
}


def _map_status(
    lifecycle_state: RunLifeCycleState | None,
    result_state: RunResultState | None,
) -> RunStatus:
    """Translate Databricks state pair to :class:`RunStatus`."""
    if lifecycle_state in _TERMINAL_STATES:
        return _RESULT_STATE_MAP.get(result_state, RunStatus.FAIL)
    if lifecycle_state is not None:
        return _LIFECYCLE_STATE_MAP.get(lifecycle_state, RunStatus.RUNNING)
    return RunStatus.PENDING


# ---------------------------------------------------------------------------
# Token-safe logging filter
# ---------------------------------------------------------------------------


class _TokenRedactionFilter(logging.Filter):
    """Logging filter that replaces sensitive tokens with a redacted marker."""

    def __init__(self, token: str) -> None:
        super().__init__()
        self._token = token

    def filter(self, record: logging.LogRecord) -> bool:
        if self._token and isinstance(record.msg, str):
            record.msg = record.msg.replace(self._token, "***REDACTED***")
        if record.args:
            sanitised = []
            for arg in record.args:  # type: ignore[union-attr]
                if isinstance(arg, str) and self._token:
                    sanitised.append(arg.replace(self._token, "***REDACTED***"))
                else:
                    sanitised.append(arg)  # type: ignore[arg-type]
            record.args = tuple(sanitised)
        return True


# ---------------------------------------------------------------------------
# DatabricksExecutor
# ---------------------------------------------------------------------------


class DatabricksExecutor:
    """Execute SQL model steps on a Databricks workspace.

    This class implements the :class:`ExecutorInterface` protocol by submitting
    Spark SQL tasks through the Jobs API, polling for their completion, and
    translating the outcome into engine-native :class:`RunRecord` instances.

    Parameters
    ----------
    host:
        Databricks workspace URL, e.g. ``https://adb-123.azuredatabricks.net``.
    token:
        Personal access token or service-principal token.  The token is stored
        in memory but is **never** emitted in log output.
    warehouse_id:
        Optional SQL warehouse identifier.  When provided, ``SqlTask``
        instances target this warehouse instead of a general-purpose cluster.
    default_cluster_size:
        T-shirt size used when a step does not specify its own cluster.
    max_retries:
        Maximum number of retries for transient API failures.
    poll_interval:
        Seconds between polling requests when waiting for a run to finish.
    job_timeout:
        Maximum seconds to wait for a single run before raising a timeout.
    """

    def __init__(
        self,
        host: str,
        token: str,
        warehouse_id: str | None = None,
        default_cluster_size: str = "small",
        max_retries: int = 5,
        poll_interval: float = 10.0,
        job_timeout: int = 3600,
        sql_guard_config: SQLGuardConfig | None = None,
    ) -> None:
        self._client = WorkspaceClient(host=host, token=token)
        self._warehouse_id = warehouse_id
        self._default_cluster_size = default_cluster_size
        self._poll_interval = poll_interval
        self._job_timeout = job_timeout
        self._retry_config = RetryConfig(
            max_retries=max_retries,
            base_delay=2.0,
            max_delay=60.0,
            jitter=True,
        )
        self._sql_guard_config = sql_guard_config

        # Attach redaction filter to prevent token leakage.
        self._redaction_filter = _TokenRedactionFilter(token)
        logger.addFilter(self._redaction_filter)

    # -- ExecutorInterface implementation ------------------------------------

    def execute_step(
        self,
        step: PlanStep,
        sql: str,
        parameters: dict[str, str],
    ) -> RunRecord:
        """Submit a single SQL step and block until it finishes."""
        run_id_str = str(uuid4())
        started_at = datetime.now(UTC)

        logger.info(
            "Submitting step %s for model %s (run %s)",
            step.step_id[:12],
            step.model,
            run_id_str[:12],
        )

        cluster_spec = get_cluster_spec(self._default_cluster_size)
        task = self._build_sql_task(
            step=step,
            sql=sql,
            params=parameters,
            cluster_spec=cluster_spec,
        )

        # SQL safety check AFTER parameter substitution so the guard
        # inspects the final SQL that will actually be executed.
        assert_sql_safe(sql, self._sql_guard_config)

        waiter = self._client.jobs.submit(
            run_name=f"ironlayer-{step.model}-{run_id_str[:8]}",
            tasks=[task],
        )
        dbx_run_id = str(waiter.bind()["run_id"]) if hasattr(waiter, "bind") else str(waiter.run_id)

        final_status = self._poll_until_complete(dbx_run_id)
        finished_at = datetime.now(UTC)

        logs_uri = ""
        error_message: str | None = None
        if final_status == RunStatus.FAIL:
            try:
                logs_uri = self.get_logs(dbx_run_id)
                error_message = logs_uri[:2000] if logs_uri else "Run failed with no output."
            except Exception:
                error_message = "Run failed and logs could not be retrieved."

        return RunRecord(
            run_id=run_id_str,
            plan_id=step.step_id,
            step_id=step.step_id,
            model_name=step.model,
            status=final_status,
            started_at=started_at,
            finished_at=finished_at,
            error_message=error_message,
            logs_uri=logs_uri or None,
            executor_version="databricks-sdk",
        )

    def submit_plan_as_job(
        self,
        plan: Plan,
        cluster_size: str | None = None,
    ) -> str:
        """Submit an entire plan as a single multi-task Databricks job.

        Task dependencies within the job mirror the ``depends_on`` edges
        declared in the plan steps, so Databricks schedules them in the
        correct topological order.

        Parameters
        ----------
        plan:
            The execution plan to submit.
        cluster_size:
            Cluster size override; defaults to the executor's configured size.

        Returns
        -------
        str
            The Databricks run ID as a string.
        """
        size = cluster_size or self._default_cluster_size
        cluster_spec = get_cluster_spec(size)

        # Build a lookup from step_id -> task_key for dependency wiring.
        task_key_map: dict[str, str] = {}
        tasks: list[SubmitTask] = []

        for idx, step in enumerate(plan.steps):
            task_key = f"step_{idx}_{step.model.replace('.', '_')}"
            task_key_map[step.step_id] = task_key

        for _idx, step in enumerate(plan.steps):
            task_key = task_key_map[step.step_id]

            dependencies: list[TaskDependency] = []
            for dep_id in step.depends_on:
                dep_key = task_key_map.get(dep_id)
                if dep_key:
                    dependencies.append(TaskDependency(task_key=dep_key))

            sql_task = SqlTask(
                query=SqlTaskQuery(query=step.model),  # type: ignore[call-arg]
                warehouse_id=self._warehouse_id or "",
            )

            task = SubmitTask(
                task_key=task_key,
                sql_task=sql_task,
                new_cluster=cluster_spec,
                depends_on=dependencies if dependencies else None,
            )
            tasks.append(task)

        logger.info(
            "Submitting plan %s as multi-task job with %d tasks",
            plan.plan_id[:12],
            len(tasks),
        )

        waiter = self._client.jobs.submit(
            run_name=f"ironlayer-{plan.plan_id[:12]}",
            tasks=tasks,
        )
        dbx_run_id = str(waiter.run_id)

        logger.info("Plan %s submitted as Databricks run %s", plan.plan_id[:12], dbx_run_id)
        return dbx_run_id

    def poll_status(self, run_id: str) -> RunStatus:
        """Poll Databricks for the current status of *run_id*.

        Handles HTTP 429 (rate limit) transparently via retry logic.
        """

        def _do_poll() -> RunStatus:
            run = self._client.jobs.get_run(run_id=int(run_id))
            state = run.state
            if state is None:
                return RunStatus.PENDING
            return _map_status(state.life_cycle_state, state.result_state)

        return retry_with_backoff(
            fn=_do_poll,
            config=self._retry_config,
            retryable_exceptions=(Exception,),
        )

    def cancel(self, run_id: str) -> None:
        """Cancel a running Databricks job."""
        logger.info("Cancelling Databricks run %s", run_id)
        self._client.jobs.cancel_run(run_id=int(run_id))

    def get_logs(self, run_id: str) -> str:
        """Retrieve logs or error output for a completed run."""
        try:
            output = self._client.jobs.get_run_output(run_id=int(run_id))
        except Exception:
            logger.warning("Could not retrieve output for run %s", run_id)
            return ""

        if output.notebook_output and output.notebook_output.result:
            return output.notebook_output.result

        if output.error:
            return output.error

        if output.error_trace:
            return output.error_trace

        return ""

    def verify_run(self, run_id: str) -> RunStatus:
        """Verify the final status of a Databricks run for reconciliation.

        Queries the Jobs API for the run's current state and maps it back
        to an engine-native RunStatus.  Uses retry logic for transient
        API errors.
        """

        def _do_verify() -> RunStatus:
            run = self._client.jobs.get_run(run_id=int(run_id))
            state = run.state
            if state is None:
                return RunStatus.PENDING
            return _map_status(state.life_cycle_state, state.result_state)

        return retry_with_backoff(
            fn=_do_verify,
            config=self._retry_config,
            retryable_exceptions=(Exception,),
        )

    # -- Internal helpers ----------------------------------------------------

    def _poll_until_complete(
        self,
        run_id: str,
        timeout: int | None = None,
    ) -> RunStatus:
        """Block until the Databricks run reaches a terminal state.

        Uses the configured poll interval with exponential backoff on
        transient failures, and raises :class:`TimeoutError` if the job
        exceeds the timeout window.
        """
        effective_timeout = timeout or self._job_timeout
        deadline = time.monotonic() + effective_timeout
        consecutive_errors = 0
        max_consecutive_errors = 10

        while True:
            if time.monotonic() > deadline:
                logger.error("Run %s exceeded timeout of %ds", run_id, effective_timeout)
                try:
                    self.cancel(run_id)
                except Exception:
                    logger.warning("Failed to cancel timed-out run %s", run_id)
                raise TimeoutError(f"Databricks run {run_id} did not complete within {effective_timeout}s")

            try:
                status = self.poll_status(run_id)
                consecutive_errors = 0
            except Exception:
                consecutive_errors += 1
                if consecutive_errors >= max_consecutive_errors:
                    raise
                backoff = min(self._poll_interval * (2**consecutive_errors), 120.0)
                logger.warning(
                    "Poll error for run %s (attempt %d/%d), retrying in %.1fs",
                    run_id,
                    consecutive_errors,
                    max_consecutive_errors,
                    backoff,
                )
                time.sleep(backoff)
                continue

            if status in {RunStatus.SUCCESS, RunStatus.FAIL, RunStatus.CANCELLED}:
                logger.info("Run %s finished with status %s", run_id, status.value)
                return status

            time.sleep(self._poll_interval)

    def _build_sql_task(
        self,
        step: PlanStep,
        sql: str,
        params: dict[str, str],
        cluster_spec: dict,
    ) -> SubmitTask:
        """Construct a :class:`SubmitTask` for a single plan step.

        Parameters are formatted as Databricks SQL widget parameters by
        wrapping them in ``{{ key }}`` markers within the query text.  The
        Databricks runtime performs the actual substitution at execution time.
        """
        # Substitute parameters directly into the SQL for SqlTask.
        rendered_sql = sql
        for key, value in params.items():
            rendered_sql = rendered_sql.replace("{{ " + key + " }}", value)
            rendered_sql = rendered_sql.replace("{{" + key + "}}", value)

        task_key = f"step_{step.model.replace('.', '_')}_{step.step_id[:8]}"

        sql_task = SqlTask(
            query=SqlTaskQuery(query=rendered_sql),  # type: ignore[call-arg]
            warehouse_id=self._warehouse_id or "",
        )

        return SubmitTask(
            task_key=task_key,
            sql_task=sql_task,
            new_cluster=cluster_spec,
        )

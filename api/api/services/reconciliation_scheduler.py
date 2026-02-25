"""Background scheduler for periodic reconciliation and schema drift checks.

Runs as an ``asyncio`` background task, polling enabled schedules every 60
seconds and executing any that are due.  Supports a simple subset of cron
expressions (hourly, daily, weekly) that covers the typical reconciliation
cadence without requiring a full cron parser dependency.
"""

from __future__ import annotations

import asyncio
import logging
import re
from datetime import UTC, datetime, timedelta
from typing import Any

from core_engine.state.database import set_tenant_context
from core_engine.state.repository import ReconciliationScheduleRepository
from sqlalchemy.exc import InterfaceError, OperationalError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from api.services.reconciliation_service import ReconciliationService

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Cron expression helpers
# ---------------------------------------------------------------------------

# Pre-compiled patterns for the supported cron subset.
_HOURLY_RE = re.compile(r"^(\d{1,2})\s+\*\s+\*\s+\*\s+\*$")
_DAILY_RE = re.compile(r"^(\d{1,2})\s+(\d{1,2})\s+\*\s+\*\s+\*$")
_WEEKLY_RE = re.compile(r"^(\d{1,2})\s+(\d{1,2})\s+\*\s+\*\s+(\d)$")


def compute_next_run(cron_expression: str, from_time: datetime) -> datetime:
    """Compute the next run time from a cron expression.

    Supports a practical subset of cron syntax:

    * ``M * * * *`` -- run every hour at minute *M*.
    * ``M H * * *`` -- run daily at hour *H*, minute *M*.
    * ``M H * * D`` -- run weekly on day-of-week *D* (0=Sunday) at *H*:*M*.

    Parameters
    ----------
    cron_expression:
        Five-field cron string (minute, hour, day-of-month, month, day-of-week).
    from_time:
        The reference time to compute the *next* run after.

    Returns
    -------
    datetime
        The next execution time (UTC).

    Raises
    ------
    ValueError
        If the cron expression does not match any supported pattern.
    """
    expr = cron_expression.strip()

    # Hourly: "M * * * *"
    match = _HOURLY_RE.match(expr)
    if match:
        minute = int(match.group(1))
        candidate = from_time.replace(minute=minute, second=0, microsecond=0)
        if candidate <= from_time:
            candidate += timedelta(hours=1)
        return candidate

    # Daily: "M H * * *"
    match = _DAILY_RE.match(expr)
    if match:
        minute = int(match.group(1))
        hour = int(match.group(2))
        candidate = from_time.replace(hour=hour, minute=minute, second=0, microsecond=0)
        if candidate <= from_time:
            candidate += timedelta(days=1)
        return candidate

    # Weekly: "M H * * D"
    match = _WEEKLY_RE.match(expr)
    if match:
        minute = int(match.group(1))
        hour = int(match.group(2))
        target_dow = int(match.group(3))  # 0=Sunday

        # Python weekday(): Monday=0 ... Sunday=6
        # Cron day-of-week: Sunday=0 ... Saturday=6
        # Convert cron dow to Python dow.
        python_dow = (target_dow - 1) % 7  # Sunday(0)->6, Mon(1)->0, ...

        candidate = from_time.replace(hour=hour, minute=minute, second=0, microsecond=0)
        current_dow = candidate.weekday()
        days_ahead = (python_dow - current_dow) % 7
        if days_ahead == 0 and candidate <= from_time:
            days_ahead = 7
        candidate += timedelta(days=days_ahead)
        return candidate

    raise ValueError(
        f"Unsupported cron expression: '{cron_expression}'. "
        f"Supported patterns: 'M * * * *' (hourly), "
        f"'M H * * *' (daily), 'M H * * D' (weekly)."
    )


# ---------------------------------------------------------------------------
# Scheduler
# ---------------------------------------------------------------------------


class ReconciliationScheduler:
    """AsyncIO background task for scheduled reconciliation.

    Periodically checks for enabled schedules whose ``next_run_at`` is in the
    past and executes the appropriate reconciliation action.

    Parameters
    ----------
    session_factory:
        An ``async_sessionmaker`` used to create database sessions for each
        schedule check iteration.
    tenant_id:
        Tenant scope for all schedule queries.
    """

    def __init__(
        self,
        session_factory: async_sessionmaker[AsyncSession],
        tenant_id: str = "default",
    ) -> None:
        self._session_factory = session_factory
        self._tenant_id = tenant_id
        self._running = False
        self._task: asyncio.Task[None] | None = None

    @property
    def running(self) -> bool:
        """Whether the scheduler loop is active."""
        return self._running

    async def start(self) -> None:
        """Start the scheduler background task."""
        if self._running:
            logger.warning("ReconciliationScheduler already running; ignoring start()")
            return
        self._running = True
        self._task = asyncio.create_task(self._run_loop())
        logger.info("ReconciliationScheduler started for tenant=%s", self._tenant_id)

    async def stop(self) -> None:
        """Stop the scheduler gracefully."""
        self._running = False
        if self._task is not None:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
            self._task = None
        logger.info("ReconciliationScheduler stopped for tenant=%s", self._tenant_id)

    async def _run_loop(self) -> None:
        """Main scheduler loop -- checks every 60 seconds for due schedules."""
        while self._running:
            try:
                await self._check_and_run_due_schedules()
            except asyncio.CancelledError:
                raise
            except (OperationalError, InterfaceError) as exc:
                logger.error(
                    "ReconciliationScheduler database error (tenant=%s): %s",
                    self._tenant_id,
                    exc,
                    exc_info=True,
                )
            except Exception as exc:
                logger.critical(
                    "ReconciliationScheduler unexpected error (tenant=%s): %s",
                    self._tenant_id,
                    exc,
                    exc_info=True,
                )
                raise
            await asyncio.sleep(60)

    async def _check_and_run_due_schedules(self) -> None:
        """Check for schedules due to run and execute them.

        Each iteration creates a session with the RLS tenant context set
        so that PostgreSQL Row-Level Security policies are active alongside
        the application-level ``tenant_id`` filters in repository queries.
        """
        async with self._session_factory() as session:
            await set_tenant_context(session, self._tenant_id)
            schedule_repo = ReconciliationScheduleRepository(session, tenant_id=self._tenant_id)
            schedules = await schedule_repo.get_all_enabled()
            now = datetime.now(UTC)

            for schedule in schedules:
                if schedule.next_run_at is not None and schedule.next_run_at <= now:
                    await self._execute_schedule(session, schedule)
            await session.commit()

    async def _execute_schedule(
        self,
        session: AsyncSession,
        schedule: Any,
    ) -> None:
        """Execute a single scheduled reconciliation.

        Runs the appropriate reconciliation type, updates ``last_run_at``,
        and computes the ``next_run_at`` from the cron expression.
        """
        now = datetime.now(UTC)
        schedule_type = schedule.schedule_type
        cron_expr = schedule.cron_expression

        logger.info(
            "Executing scheduled reconciliation: type=%s tenant=%s",
            schedule_type,
            self._tenant_id,
        )

        try:
            service = ReconciliationService(session, tenant_id=self._tenant_id)

            if schedule_type == "run_reconciliation":
                result = await service.trigger_reconciliation(hours_back=24)
                logger.info("Scheduled run_reconciliation complete: %s", result)
            elif schedule_type == "schema_drift":
                result = await service.check_all_schemas()
                logger.info("Scheduled schema_drift check complete: %s", result)
            else:
                logger.warning("Unknown schedule_type '%s'; skipping.", schedule_type)
                return
        except Exception as exc:
            logger.error(
                "Scheduled reconciliation failed (type=%s, tenant=%s): %s",
                schedule_type,
                self._tenant_id,
                exc,
                exc_info=True,
            )

        # Update timing regardless of success/failure so the schedule advances.
        try:
            next_run = compute_next_run(cron_expr, now)
        except ValueError as exc:
            logger.error(
                "Invalid cron expression for schedule type=%s: %s",
                schedule_type,
                exc,
            )
            return

        schedule_repo = ReconciliationScheduleRepository(session, tenant_id=self._tenant_id)
        await schedule_repo.update_last_run(
            schedule_type=schedule_type,
            last_run_at=now,
            next_run_at=next_run,
        )

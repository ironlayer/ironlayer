"""Telemetry retention management and aggregation policy.

Defines default retention windows and provides aggregation jobs:

- **Raw telemetry**: 30 days retention (configurable).
- **Hourly aggregates**: 365 days retention.
- **Daily aggregates**: Indefinite retention.

Aggregation jobs roll up raw records into compact summaries suitable
for long-term storage and cost/performance trend analysis.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta

from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from core_engine.state.tables import TelemetryTable

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class RetentionPolicy:
    """Configurable retention windows for telemetry data.

    Parameters
    ----------
    raw_retention_days:
        How long to keep raw per-run telemetry records.
    hourly_retention_days:
        How long to keep hourly aggregate records.
    daily_retention_days:
        How long to keep daily aggregates (0 = indefinite).
    """

    raw_retention_days: int = 30
    hourly_retention_days: int = 365
    daily_retention_days: int = 0  # 0 = indefinite


@dataclass(frozen=True)
class AggregateRecord:
    """A single aggregated telemetry summary."""

    model_name: str
    period_start: datetime
    period_end: datetime
    run_count: int
    avg_runtime_seconds: float
    total_shuffle_bytes: int
    total_input_rows: int
    total_output_rows: int
    avg_partition_count: float
    p50_runtime_seconds: float
    p95_runtime_seconds: float


DEFAULT_POLICY = RetentionPolicy()


class RetentionManager:
    """Manages telemetry lifecycle: aggregation, compaction, and cleanup.

    Parameters
    ----------
    session:
        Active database session.
    tenant_id:
        Tenant to scope operations to.
    policy:
        Retention policy to apply.
    """

    def __init__(
        self,
        session: AsyncSession,
        tenant_id: str = "default",
        policy: RetentionPolicy | None = None,
    ) -> None:
        self._session = session
        self._tenant_id = tenant_id
        self._policy = policy or DEFAULT_POLICY

    async def cleanup_expired_raw(self) -> int:
        """Delete raw telemetry records older than the retention window.

        Returns the number of records deleted.
        """
        cutoff = datetime.now(UTC) - timedelta(days=self._policy.raw_retention_days)
        stmt = delete(TelemetryTable).where(
            TelemetryTable.tenant_id == self._tenant_id,
            TelemetryTable.captured_at < cutoff,
        )
        result = await self._session.execute(stmt)
        await self._session.flush()
        count = result.rowcount or 0  # type: ignore[attr-defined]
        logger.info(
            "Cleaned up %d expired raw telemetry records (cutoff: %s)",
            count,
            cutoff.isoformat(),
        )
        return count

    async def compute_hourly_aggregates(
        self,
        target_date: date | None = None,
    ) -> list[AggregateRecord]:
        """Compute hourly aggregates for a given date.

        Parameters
        ----------
        target_date:
            The date to aggregate.  Defaults to yesterday.

        Returns
        -------
        list[AggregateRecord]
            Hourly aggregate records for all models with data on that date.
        """
        if target_date is None:
            target_date = date.today() - timedelta(days=1)

        day_start = datetime(
            target_date.year,
            target_date.month,
            target_date.day,
            tzinfo=UTC,
        )
        day_start + timedelta(days=1)

        aggregates: list[AggregateRecord] = []

        for hour_offset in range(24):
            period_start = day_start + timedelta(hours=hour_offset)
            period_end = period_start + timedelta(hours=1)

            stmt = (
                select(
                    TelemetryTable.model_name,
                    func.count().label("run_count"),
                    func.avg(TelemetryTable.runtime_seconds).label("avg_runtime"),
                    func.sum(TelemetryTable.shuffle_bytes).label("total_shuffle"),
                    func.sum(TelemetryTable.input_rows).label("total_input"),
                    func.sum(TelemetryTable.output_rows).label("total_output"),
                    func.avg(TelemetryTable.partition_count).label("avg_partitions"),
                )
                .where(
                    TelemetryTable.tenant_id == self._tenant_id,
                    TelemetryTable.captured_at >= period_start,
                    TelemetryTable.captured_at < period_end,
                )
                .group_by(TelemetryTable.model_name)
            )

            result = await self._session.execute(stmt)
            rows = result.all()

            for row in rows:
                # For percentiles, we need the raw values
                p_stmt = (
                    select(TelemetryTable.runtime_seconds)
                    .where(
                        TelemetryTable.tenant_id == self._tenant_id,
                        TelemetryTable.model_name == row.model_name,
                        TelemetryTable.captured_at >= period_start,
                        TelemetryTable.captured_at < period_end,
                    )
                    .order_by(TelemetryTable.runtime_seconds)
                )
                p_result = await self._session.execute(p_stmt)
                runtimes = [r[0] for r in p_result.all()]

                p50 = _percentile(runtimes, 0.50)
                p95 = _percentile(runtimes, 0.95)

                aggregates.append(
                    AggregateRecord(
                        model_name=row.model_name,
                        period_start=period_start,
                        period_end=period_end,
                        run_count=row.run_count,
                        avg_runtime_seconds=float(row.avg_runtime or 0),
                        total_shuffle_bytes=int(row.total_shuffle or 0),
                        total_input_rows=int(row.total_input or 0),
                        total_output_rows=int(row.total_output or 0),
                        avg_partition_count=float(row.avg_partitions or 0),
                        p50_runtime_seconds=p50,
                        p95_runtime_seconds=p95,
                    )
                )

        return aggregates

    async def compute_daily_aggregates(
        self,
        target_date: date | None = None,
    ) -> list[AggregateRecord]:
        """Compute daily aggregates for a given date.

        Parameters
        ----------
        target_date:
            The date to aggregate.  Defaults to yesterday.
        """
        if target_date is None:
            target_date = date.today() - timedelta(days=1)

        day_start = datetime(
            target_date.year,
            target_date.month,
            target_date.day,
            tzinfo=UTC,
        )
        day_end = day_start + timedelta(days=1)

        stmt = (
            select(
                TelemetryTable.model_name,
                func.count().label("run_count"),
                func.avg(TelemetryTable.runtime_seconds).label("avg_runtime"),
                func.sum(TelemetryTable.shuffle_bytes).label("total_shuffle"),
                func.sum(TelemetryTable.input_rows).label("total_input"),
                func.sum(TelemetryTable.output_rows).label("total_output"),
                func.avg(TelemetryTable.partition_count).label("avg_partitions"),
            )
            .where(
                TelemetryTable.tenant_id == self._tenant_id,
                TelemetryTable.captured_at >= day_start,
                TelemetryTable.captured_at < day_end,
            )
            .group_by(TelemetryTable.model_name)
        )

        result = await self._session.execute(stmt)
        rows = result.all()

        aggregates: list[AggregateRecord] = []
        for row in rows:
            p_stmt = (
                select(TelemetryTable.runtime_seconds)
                .where(
                    TelemetryTable.tenant_id == self._tenant_id,
                    TelemetryTable.model_name == row.model_name,
                    TelemetryTable.captured_at >= day_start,
                    TelemetryTable.captured_at < day_end,
                )
                .order_by(TelemetryTable.runtime_seconds)
            )
            p_result = await self._session.execute(p_stmt)
            runtimes = [r[0] for r in p_result.all()]

            aggregates.append(
                AggregateRecord(
                    model_name=row.model_name,
                    period_start=day_start,
                    period_end=day_end,
                    run_count=row.run_count,
                    avg_runtime_seconds=float(row.avg_runtime or 0),
                    total_shuffle_bytes=int(row.total_shuffle or 0),
                    total_input_rows=int(row.total_input or 0),
                    total_output_rows=int(row.total_output or 0),
                    avg_partition_count=float(row.avg_partitions or 0),
                    p50_runtime_seconds=_percentile(runtimes, 0.50),
                    p95_runtime_seconds=_percentile(runtimes, 0.95),
                )
            )

        return aggregates


def _percentile(sorted_values: list[float], pct: float) -> float:
    """Compute a percentile from a sorted list of values."""
    if not sorted_values:
        return 0.0
    idx = int(len(sorted_values) * pct)
    idx = min(idx, len(sorted_values) - 1)
    return sorted_values[idx]

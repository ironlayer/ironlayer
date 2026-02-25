"""Tenant-scoped reporting service for cost, usage, and LLM analytics.

Supports date-range queries, multiple grouping modes, CSV/JSON export,
and period-over-period comparison reports.
"""

from __future__ import annotations

import csv
import io
import json
import logging
from datetime import UTC, datetime
from typing import Any

from core_engine.state.repository import ReportingRepository
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# CSV injection prevention
# ---------------------------------------------------------------------------

_CSV_DANGEROUS_CHARS = frozenset({"=", "+", "-", "@", "\t", "\r"})


def _sanitize_csv_value(value: Any) -> Any:
    """Prevent CSV formula injection by prefixing dangerous values.

    Cells starting with ``=``, ``+``, ``-``, ``@``, ``\\t``, or ``\\r``
    are interpreted as formulas by spreadsheet applications.  Prefixing
    with a single-quote neutralises this while keeping the value readable.
    """
    if isinstance(value, str) and value and value[0] in _CSV_DANGEROUS_CHARS:
        return "'" + value
    return value


# ---------------------------------------------------------------------------
# Format / report-type validation
# ---------------------------------------------------------------------------

_VALID_FORMATS = frozenset({"csv", "json"})
_VALID_REPORT_TYPES = frozenset({"cost", "llm", "usage"})


class ReportingService:
    """Per-tenant reporting with export and comparison capabilities."""

    def __init__(self, session: AsyncSession, tenant_id: str) -> None:
        self._repo = ReportingRepository(session, tenant_id)
        self._tenant_id = tenant_id

    async def cost_report(
        self,
        since: datetime,
        until: datetime,
        group_by: str = "model",
    ) -> dict[str, Any]:
        """Generate a cost report grouped by model or time bucket.

        Returns
        -------
        dict
            ``{"items": [...], "total_cost_usd": float, "period": {...}}``
        """
        if group_by == "model":
            items = await self._repo.get_cost_by_model(since, until)
        else:
            items = await self._repo.get_cost_by_time(since, until, group_by)

        total_cost = sum(item.get("cost_usd", 0) for item in items)
        return {
            "items": items,
            "total_cost_usd": round(total_cost, 4),
            "period": {"since": since.isoformat(), "until": until.isoformat()},
            "group_by": group_by,
        }

    async def usage_report(
        self,
        since: datetime,
        until: datetime,
        group_by: str = "actor",
    ) -> dict[str, Any]:
        """Generate a usage report grouped by actor or time bucket.

        Returns
        -------
        dict
            ``{"items": [...], "period": {...}}``
        """
        if group_by == "actor":
            items = await self._repo.get_usage_by_actor(since, until)
        else:
            items = await self._repo.get_usage_by_type_over_time(since, until, group_by)

        return {
            "items": items,
            "period": {"since": since.isoformat(), "until": until.isoformat()},
            "group_by": group_by,
        }

    async def llm_report(
        self,
        since: datetime,
        until: datetime,
    ) -> dict[str, Any]:
        """Generate an LLM cost and token usage report.

        Returns
        -------
        dict
            ``{"by_call_type": [...], "by_time": [...], "total_cost_usd": float, "period": {...}}``
        """
        by_type = await self._repo.get_llm_cost_by_call_type(since, until)
        by_time = await self._repo.get_llm_cost_by_time(since, until, "day")
        total_cost = sum(item.get("cost_usd", 0) for item in by_type)

        return {
            "by_call_type": by_type,
            "by_time": by_time,
            "total_cost_usd": round(total_cost, 6),
            "period": {"since": since.isoformat(), "until": until.isoformat()},
        }

    async def export_data(
        self,
        report_type: str,
        since: datetime,
        until: datetime,
        fmt: str = "csv",
    ) -> tuple[bytes, str, str]:
        """Export report data as CSV or JSON bytes.

        Parameters
        ----------
        report_type:
            One of ``"cost"``, ``"usage"``, ``"llm"``.
        fmt:
            ``"csv"`` or ``"json"``.

        Returns
        -------
        tuple
            ``(data_bytes, content_type, filename)``

        Raises
        ------
        ValueError
            If *fmt* is not a supported export format.
        """
        if fmt not in _VALID_FORMATS:
            raise ValueError(f"Unsupported export format '{fmt}'. Valid: {sorted(_VALID_FORMATS)}")

        # Generate the report data.
        if report_type == "cost":
            report = await self.cost_report(since, until, "model")
            items = report["items"]
        elif report_type == "usage":
            report = await self.usage_report(since, until, "actor")
            items = report["items"]
        elif report_type == "llm":
            report = await self.llm_report(since, until)
            items = report["by_call_type"]
        else:
            raise ValueError(f"Unknown report type: {report_type}")

        date_str = datetime.now(UTC).strftime("%Y%m%d")
        base_name = f"ironlayer_{report_type}_report_{date_str}"

        if fmt == "json":
            data = json.dumps({"items": items, "exported_at": datetime.now(UTC).isoformat()}, indent=2).encode("utf-8")
            return data, "application/json", f"{base_name}.json"

        # CSV export.
        if not items:
            return b"", "text/csv", f"{base_name}.csv"

        output = io.StringIO()
        fieldnames = list(items[0].keys())
        writer = csv.writer(output)
        writer.writerow(fieldnames)
        for row in items:
            writer.writerow([_sanitize_csv_value(row.get(k, "")) for k in fieldnames])
        data = output.getvalue().encode("utf-8")
        return data, "text/csv", f"{base_name}.csv"

    async def comparison_report(
        self,
        current_start: datetime,
        current_end: datetime,
        previous_start: datetime,
        previous_end: datetime,
        report_type: str = "cost",
    ) -> dict[str, Any]:
        """Run the same report for two periods and compute deltas.

        Returns
        -------
        dict
            ``{"current": {...}, "previous": {...}, "delta": {...}}``

        Raises
        ------
        ValueError
            If *report_type* is not a supported report type.
        """
        if report_type not in _VALID_REPORT_TYPES:
            raise ValueError(f"Unsupported report type '{report_type}'. Valid: {sorted(_VALID_REPORT_TYPES)}")

        if report_type == "cost":
            current = await self.cost_report(current_start, current_end, "model")
            previous = await self.cost_report(previous_start, previous_end, "model")
            current_total = current["total_cost_usd"]
            previous_total = previous["total_cost_usd"]
        elif report_type == "llm":
            current = await self.llm_report(current_start, current_end)
            previous = await self.llm_report(previous_start, previous_end)
            current_total = current["total_cost_usd"]
            previous_total = previous["total_cost_usd"]
        else:
            current = await self.usage_report(current_start, current_end, "actor")
            previous = await self.usage_report(previous_start, previous_end, "actor")
            current_total = len(current["items"])
            previous_total = len(previous["items"])

        absolute_delta = round(current_total - previous_total, 4)
        pct_delta = round((absolute_delta / previous_total) * 100, 2) if previous_total else None

        return {
            "current": current,
            "previous": previous,
            "delta": {
                "absolute": absolute_delta,
                "percentage": pct_delta,
                "direction": "up" if absolute_delta > 0 else ("down" if absolute_delta < 0 else "flat"),
            },
        }

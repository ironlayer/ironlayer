"""Invoice generation, PDF rendering, and storage service.

Generates invoices from usage data, renders PDFs using reportlab, and
manages invoice lifecycle (creation, retrieval, PDF download).  Invoices
can be generated on-demand or triggered by Stripe webhook events.
"""

from __future__ import annotations

import io
import logging
import re
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from core_engine.state.repository import InvoiceRepository
from core_engine.state.tables import (
    LLMUsageLogTable,
    RunTable,
    UsageEventTable,
)
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Path traversal prevention
# ---------------------------------------------------------------------------

_SAFE_ID_RE = re.compile(r"^[a-zA-Z0-9_-]+$")


def _validate_path_component(value: str, name: str) -> None:
    """Reject identifiers that contain path-separator or other unsafe chars.

    Only allows alphanumeric characters, hyphens, and underscores.

    Raises
    ------
    ValueError
        If *value* contains characters outside the safe set.
    """
    if not _SAFE_ID_RE.match(value):
        raise ValueError(f"Invalid {name}: contains unsafe characters")


def _resolve_safe_path(storage_base: Path, tenant_id: str, invoice_id: str) -> Path:
    """Build and validate that the resolved path stays within *storage_base*.

    Raises
    ------
    ValueError
        If the resolved path escapes the storage root (path traversal).
    """
    _validate_path_component(tenant_id, "tenant_id")
    _validate_path_component(invoice_id, "invoice_id")

    base_resolved = storage_base.resolve()
    full_path = (base_resolved / tenant_id / f"{invoice_id}.pdf").resolve()
    if not str(full_path).startswith(str(base_resolved)):
        raise ValueError("Path traversal detected")
    return full_path


class InvoiceService:
    """Per-tenant invoice generation and management."""

    def __init__(
        self,
        session: AsyncSession,
        tenant_id: str,
        storage_path: str = "/var/lib/ironlayer/invoices",
    ) -> None:
        self._session = session
        self._tenant_id = tenant_id
        self._repo = InvoiceRepository(session, tenant_id)
        self._storage_path = storage_path

    async def generate_invoice(
        self,
        period_start: datetime,
        period_end: datetime,
    ) -> dict[str, Any]:
        """Generate an invoice for the given billing period.

        Queries usage events, run costs, and LLM costs for the period,
        builds line items, creates the DB record, renders a PDF, and
        stores the file.

        Returns the invoice data dict.
        """
        invoice_id = uuid.uuid4().hex
        invoice_number = await self._repo.get_next_invoice_number()

        # ----- Build line items from usage data -----
        line_items: list[dict[str, Any]] = []

        # Plan runs.
        plan_runs_r = await self._session.execute(
            select(func.coalesce(func.sum(UsageEventTable.quantity), 0)).where(
                UsageEventTable.tenant_id == self._tenant_id,
                UsageEventTable.event_type == "plan_run",
                UsageEventTable.created_at >= period_start,
                UsageEventTable.created_at < period_end,
            )
        )
        plan_runs = int(plan_runs_r.scalar_one())
        if plan_runs > 0:
            line_items.append(
                {
                    "description": "Plan Runs",
                    "quantity": plan_runs,
                    "unit_price": 0.0,  # Included in subscription
                    "amount": 0.0,
                }
            )

        # AI calls.
        ai_calls_r = await self._session.execute(
            select(func.coalesce(func.sum(UsageEventTable.quantity), 0)).where(
                UsageEventTable.tenant_id == self._tenant_id,
                UsageEventTable.event_type == "ai_call",
                UsageEventTable.created_at >= period_start,
                UsageEventTable.created_at < period_end,
            )
        )
        ai_calls = int(ai_calls_r.scalar_one())
        if ai_calls > 0:
            line_items.append(
                {
                    "description": "AI Advisory Calls",
                    "quantity": ai_calls,
                    "unit_price": 0.0,  # Included in subscription
                    "amount": 0.0,
                }
            )

        # Compute run cost.
        run_cost_r = await self._session.execute(
            select(func.coalesce(func.sum(RunTable.cost_usd), 0.0)).where(
                RunTable.tenant_id == self._tenant_id,
                RunTable.started_at >= period_start,
                RunTable.started_at < period_end,
                RunTable.cost_usd.is_not(None),
            )
        )
        run_cost_val = run_cost_r.scalar_one()
        run_cost = round(float(run_cost_val) if run_cost_val is not None else 0.0, 2)
        if run_cost > 0:
            line_items.append(
                {
                    "description": "Compute Cost (Databricks)",
                    "quantity": 1,
                    "unit_price": run_cost,
                    "amount": run_cost,
                }
            )

        # LLM cost.
        llm_cost_r = await self._session.execute(
            select(func.coalesce(func.sum(LLMUsageLogTable.estimated_cost_usd), 0.0)).where(
                LLMUsageLogTable.tenant_id == self._tenant_id,
                LLMUsageLogTable.created_at >= period_start,
                LLMUsageLogTable.created_at < period_end,
            )
        )
        llm_cost = round(float(llm_cost_r.scalar_one()), 2)
        if llm_cost > 0:
            line_items.append(
                {
                    "description": "LLM Usage (AI Advisory)",
                    "quantity": 1,
                    "unit_price": llm_cost,
                    "amount": llm_cost,
                }
            )

        # API requests.
        api_requests_r = await self._session.execute(
            select(func.coalesce(func.sum(UsageEventTable.quantity), 0)).where(
                UsageEventTable.tenant_id == self._tenant_id,
                UsageEventTable.event_type == "api_request",
                UsageEventTable.created_at >= period_start,
                UsageEventTable.created_at < period_end,
            )
        )
        api_requests = int(api_requests_r.scalar_one())
        if api_requests > 0:
            line_items.append(
                {
                    "description": "API Requests",
                    "quantity": api_requests,
                    "unit_price": 0.0,
                    "amount": 0.0,
                }
            )

        subtotal = round(sum(item["amount"] for item in line_items), 2)
        tax = 0.0  # Tax calculation would integrate with a tax service.
        total = round(subtotal + tax, 2)

        # Render PDF.
        invoice_data = {
            "invoice_id": invoice_id,
            "invoice_number": invoice_number,
            "tenant_id": self._tenant_id,
            "period_start": period_start.isoformat(),
            "period_end": period_end.isoformat(),
            "line_items": line_items,
            "subtotal_usd": subtotal,
            "tax_usd": tax,
            "total_usd": total,
            "created_at": datetime.now(UTC).isoformat(),
        }

        pdf_bytes = self._render_pdf(invoice_data)
        pdf_key = self._store_pdf(invoice_id, pdf_bytes)

        # Persist to DB.
        await self._repo.create(
            invoice_id=invoice_id,
            invoice_number=invoice_number,
            period_start=period_start,
            period_end=period_end,
            subtotal_usd=subtotal,
            tax_usd=tax,
            total_usd=total,
            line_items=line_items,
            pdf_storage_key=pdf_key,
        )

        logger.info(
            "Generated invoice %s for tenant=%s period=%s..%s total=$%.2f",
            invoice_number,
            self._tenant_id,
            period_start.strftime("%Y-%m-%d"),
            period_end.strftime("%Y-%m-%d"),
            total,
        )

        return invoice_data

    async def generate_invoice_from_stripe(self, stripe_event: dict[str, Any]) -> dict[str, Any] | None:
        """Generate an internal invoice from a Stripe ``invoice.payment_succeeded`` event.

        Maps the Stripe invoice data to our internal format and persists it.
        Returns ``None`` if the invoice already exists.
        """
        stripe_invoice = stripe_event.get("data", {}).get("object", {})
        stripe_invoice_id = stripe_invoice.get("id")

        if not stripe_invoice_id:
            logger.warning("Stripe event missing invoice ID")
            return None

        # Check for duplicate.
        existing = await self._repo.get_by_stripe_invoice(stripe_invoice_id)
        if existing is not None:
            logger.info("Invoice for stripe_invoice=%s already exists", stripe_invoice_id)
            return None

        period_start = datetime.fromtimestamp(stripe_invoice.get("period_start", 0), tz=UTC)
        period_end = datetime.fromtimestamp(stripe_invoice.get("period_end", 0), tz=UTC)

        # Build line items from Stripe invoice lines.
        stripe_lines = stripe_invoice.get("lines", {}).get("data", [])
        line_items = []
        for line in stripe_lines:
            line_items.append(
                {
                    "description": line.get("description", "Subscription"),
                    "quantity": line.get("quantity", 1),
                    "unit_price": round(line.get("unit_amount", 0) / 100, 2),
                    "amount": round(line.get("amount", 0) / 100, 2),
                }
            )

        subtotal = round(stripe_invoice.get("subtotal", 0) / 100, 2)
        tax = round(stripe_invoice.get("tax", 0) / 100, 2)
        total = round(stripe_invoice.get("total", 0) / 100, 2)

        invoice_id = uuid.uuid4().hex
        invoice_number = await self._repo.get_next_invoice_number()

        invoice_data = {
            "invoice_id": invoice_id,
            "invoice_number": invoice_number,
            "stripe_invoice_id": stripe_invoice_id,
            "tenant_id": self._tenant_id,
            "period_start": period_start.isoformat(),
            "period_end": period_end.isoformat(),
            "line_items": line_items,
            "subtotal_usd": subtotal,
            "tax_usd": tax,
            "total_usd": total,
            "created_at": datetime.now(UTC).isoformat(),
        }

        pdf_bytes = self._render_pdf(invoice_data)
        pdf_key = self._store_pdf(invoice_id, pdf_bytes)

        await self._repo.create(
            invoice_id=invoice_id,
            invoice_number=invoice_number,
            period_start=period_start,
            period_end=period_end,
            subtotal_usd=subtotal,
            tax_usd=tax,
            total_usd=total,
            line_items=line_items,
            stripe_invoice_id=stripe_invoice_id,
            pdf_storage_key=pdf_key,
        )
        await self._repo.update_status(invoice_id, "paid")

        logger.info("Generated invoice from Stripe: %s -> %s", stripe_invoice_id, invoice_number)
        return invoice_data

    async def get_invoice(self, invoice_id: str) -> dict[str, Any] | None:
        """Return invoice detail with line items."""
        row = await self._repo.get(invoice_id)
        if row is None:
            return None
        return {
            "invoice_id": row.invoice_id,
            "invoice_number": row.invoice_number,
            "stripe_invoice_id": row.stripe_invoice_id,
            "period_start": row.period_start.isoformat() if row.period_start else None,
            "period_end": row.period_end.isoformat() if row.period_end else None,
            "subtotal_usd": row.subtotal_usd,
            "tax_usd": row.tax_usd,
            "total_usd": row.total_usd,
            "line_items": row.line_items_json,
            "status": row.status,
            "created_at": row.created_at.isoformat() if row.created_at else None,
        }

    async def list_invoices(
        self,
        limit: int = 20,
        offset: int = 0,
    ) -> dict[str, Any]:
        """List invoices for this tenant with pagination."""
        rows, total = await self._repo.list_for_tenant(limit, offset)
        invoices = []
        for row in rows:
            invoices.append(
                {
                    "invoice_id": row.invoice_id,
                    "invoice_number": row.invoice_number,
                    "period_start": row.period_start.isoformat() if row.period_start else None,
                    "period_end": row.period_end.isoformat() if row.period_end else None,
                    "total_usd": row.total_usd,
                    "status": row.status,
                    "created_at": row.created_at.isoformat() if row.created_at else None,
                }
            )
        return {"invoices": invoices, "total": total}

    async def get_pdf(self, invoice_id: str) -> bytes | None:
        """Read the PDF file for an invoice from storage.

        Returns ``None`` if the invoice doesn't exist or has no PDF.

        Validates that the stored path resolves within the configured
        storage directory to prevent path traversal attacks.
        """
        # Validate the invoice_id itself before any I/O.
        _validate_path_component(invoice_id, "invoice_id")

        row = await self._repo.get(invoice_id)
        if row is None or not row.pdf_storage_key:
            return None

        # Verify the stored path resolves within the storage root.
        storage_base = Path(self._storage_path).resolve()
        pdf_path = Path(row.pdf_storage_key).resolve()
        if not str(pdf_path).startswith(str(storage_base)):
            logger.error(
                "Path traversal attempt detected for invoice %s: %s",
                invoice_id,
                row.pdf_storage_key,
            )
            raise ValueError("Path traversal detected")

        try:
            return pdf_path.read_bytes()
        except FileNotFoundError:
            logger.warning("PDF not found at %s for invoice %s", pdf_path, invoice_id)
            return None

    def _render_pdf(self, invoice_data: dict[str, Any]) -> bytes:
        """Render an invoice as a PDF document using reportlab.

        Falls back to a simple text-based PDF if reportlab is not available.
        """
        try:
            return self._render_pdf_reportlab(invoice_data)
        except ImportError:
            logger.warning("reportlab not installed; generating text-based PDF")
            return self._render_pdf_fallback(invoice_data)

    def _render_pdf_reportlab(self, data: dict[str, Any]) -> bytes:
        """Render PDF using reportlab with IronLayer branding."""
        from reportlab.lib import colors
        from reportlab.lib.pagesizes import letter
        from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
        from reportlab.lib.units import inch
        from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

        buf = io.BytesIO()
        doc = SimpleDocTemplate(buf, pagesize=letter, topMargin=0.75 * inch, bottomMargin=0.75 * inch)
        styles = getSampleStyleSheet()

        elements = []

        # Header.
        header_style = ParagraphStyle(
            "Header", parent=styles["Heading1"], fontSize=20, textColor=colors.HexColor("#1a1a2e")
        )
        elements.append(Paragraph("IronLayer", header_style))
        elements.append(Spacer(1, 12))

        # Invoice metadata.
        meta_style = ParagraphStyle("Meta", parent=styles["Normal"], fontSize=10, textColor=colors.grey)
        elements.append(Paragraph(f"Invoice: {data['invoice_number']}", styles["Heading3"]))
        elements.append(Paragraph(f"Tenant: {data['tenant_id']}", meta_style))
        elements.append(Paragraph(f"Period: {data['period_start'][:10]} to {data['period_end'][:10]}", meta_style))
        elements.append(Paragraph(f"Date: {data['created_at'][:10]}", meta_style))
        elements.append(Spacer(1, 24))

        # Line items table.
        table_data = [["Description", "Quantity", "Unit Price", "Amount"]]
        for item in data.get("line_items", []):
            table_data.append(
                [
                    item["description"],
                    str(item["quantity"]),
                    f"${item['unit_price']:.2f}",
                    f"${item['amount']:.2f}",
                ]
            )

        # Totals.
        table_data.append(["", "", "Subtotal:", f"${data['subtotal_usd']:.2f}"])
        table_data.append(["", "", "Tax:", f"${data['tax_usd']:.2f}"])
        table_data.append(["", "", "Total:", f"${data['total_usd']:.2f}"])

        table = Table(table_data, colWidths=[3.5 * inch, 1 * inch, 1.25 * inch, 1.25 * inch])
        table.setStyle(
            TableStyle(
                [
                    ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#1a1a2e")),
                    ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                    ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                    ("FONTSIZE", (0, 0), (-1, 0), 10),
                    ("BOTTOMPADDING", (0, 0), (-1, 0), 12),
                    ("GRID", (0, 0), (-1, -4), 0.5, colors.grey),
                    ("ALIGN", (1, 0), (-1, -1), "RIGHT"),
                    ("FONTNAME", (2, -3), (-1, -1), "Helvetica-Bold"),
                    ("LINEABOVE", (2, -3), (-1, -3), 1, colors.black),
                    ("LINEABOVE", (2, -1), (-1, -1), 2, colors.black),
                ]
            )
        )
        elements.append(table)
        elements.append(Spacer(1, 36))

        # Footer.
        footer_style = ParagraphStyle("Footer", parent=styles["Normal"], fontSize=8, textColor=colors.grey)
        elements.append(Paragraph("Generated by IronLayer Platform", footer_style))

        doc.build(elements)
        return buf.getvalue()

    def _render_pdf_fallback(self, data: dict[str, Any]) -> bytes:
        """Simple text-based PDF fallback without reportlab."""
        lines = [
            "IRONLAYER INVOICE",
            "=" * 50,
            f"Invoice: {data['invoice_number']}",
            f"Tenant:  {data['tenant_id']}",
            f"Period:  {data['period_start'][:10]} to {data['period_end'][:10]}",
            f"Date:    {data['created_at'][:10]}",
            "",
            f"{'Description':<30} {'Qty':>6} {'Unit':>10} {'Amount':>10}",
            "-" * 60,
        ]
        for item in data.get("line_items", []):
            lines.append(
                f"{item['description']:<30} {item['quantity']:>6} ${item['unit_price']:>9.2f} ${item['amount']:>9.2f}"
            )
        lines.extend(
            [
                "-" * 60,
                f"{'Subtotal:':>48} ${data['subtotal_usd']:>9.2f}",
                f"{'Tax:':>48} ${data['tax_usd']:>9.2f}",
                f"{'Total:':>48} ${data['total_usd']:>9.2f}",
                "",
                "Generated by IronLayer Platform",
            ]
        )
        return "\n".join(lines).encode("utf-8")

    def _store_pdf(self, invoice_id: str, pdf_bytes: bytes) -> str:
        """Write PDF bytes to the filesystem and return the storage key.

        Validates that *tenant_id* and *invoice_id* contain only safe
        characters and that the resolved path stays within the configured
        storage directory to prevent path traversal attacks.
        """
        storage_base = Path(self._storage_path)
        pdf_path = _resolve_safe_path(storage_base, self._tenant_id, invoice_id)
        pdf_path.parent.mkdir(parents=True, exist_ok=True)
        pdf_path.write_bytes(pdf_bytes)
        logger.info("Stored invoice PDF: %s (%d bytes)", pdf_path, len(pdf_bytes))
        return str(pdf_path)

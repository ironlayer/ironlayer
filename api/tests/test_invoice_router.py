"""Tests for invoice and quota endpoints in api/api/routers/billing.py

Covers:
- GET /billing/quotas: quota data with usage and LLM budget info
- GET /billing/invoices: paginated invoice listing
- GET /billing/invoices/{invoice_id}: invoice detail, 404 for missing
- GET /billing/invoices/{invoice_id}/download: PDF streaming, 404 for missing
- RBAC: invoice endpoints require VIEW_INVOICES (admin-only); quotas use READ_PLANS
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import time
from typing import Any
from unittest.mock import AsyncMock, patch

import pytest
from httpx import AsyncClient

_DEV_SECRET = "test-secret-key-for-ironlayer-tests"


def _make_dev_token(
    tenant_id: str = "default",
    sub: str = "test-user",
    role: str = "admin",
    scopes: list[str] | None = None,
) -> str:
    now = time.time()
    payload: dict[str, Any] = {
        "sub": sub,
        "tenant_id": tenant_id,
        "iss": "ironlayer",
        "iat": now,
        "exp": now + 3600,
        "scopes": scopes or ["read", "write"],
        "jti": "test-jti-conftest",
        "identity_kind": "user",
        "role": role,
    }
    payload_json = json.dumps(payload)
    signature = hmac.new(
        _DEV_SECRET.encode("utf-8"),
        payload_json.encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()
    token_bytes = base64.urlsafe_b64encode(payload_json.encode("utf-8")).decode("ascii")
    return f"bmdev.{token_bytes}.{signature}"


# Viewer token for RBAC tests (has READ_PLANS but not VIEW_INVOICES).
_VIEWER_TOKEN = _make_dev_token(role="viewer")
_VIEWER_HEADERS = {"Authorization": f"Bearer {_VIEWER_TOKEN}"}


# ---------------------------------------------------------------------------
# GET /billing/quotas
# ---------------------------------------------------------------------------


class TestQuotasEndpoint:
    """Verify GET /api/v1/billing/quotas responses."""

    @pytest.mark.asyncio
    async def test_returns_quota_data(self, client: AsyncClient) -> None:
        """Authenticated user receives 200 with quotas list and llm_budget."""
        mock_usage: dict[str, Any] = {
            "quotas": [
                {
                    "name": "Plan Runs",
                    "event_type": "plan_run",
                    "used": 23,
                    "limit": 100,
                    "percentage": 23.0,
                },
                {
                    "name": "AI Calls",
                    "event_type": "ai_call",
                    "used": 150,
                    "limit": 500,
                    "percentage": 30.0,
                },
                {
                    "name": "API Requests",
                    "event_type": "api_request",
                    "used": 4500,
                    "limit": 10000,
                    "percentage": 45.0,
                },
            ],
            "llm_budget": {
                "daily_used_usd": 1.2345,
                "daily_limit_usd": 10.0,
                "monthly_used_usd": 28.50,
                "monthly_limit_usd": 200.0,
            },
        }

        with patch("api.routers.billing.QuotaService") as MockQuota:
            instance = MockQuota.return_value
            instance.get_usage_vs_limits = AsyncMock(return_value=mock_usage)

            resp = await client.get("/api/v1/billing/quotas")

        assert resp.status_code == 200
        body = resp.json()
        assert len(body["quotas"]) == 3
        assert body["quotas"][0]["name"] == "Plan Runs"
        assert body["quotas"][0]["used"] == 23
        assert body["quotas"][0]["limit"] == 100
        assert body["llm_budget"]["daily_used_usd"] == 1.2345
        assert body["llm_budget"]["monthly_limit_usd"] == 200.0

        instance.get_usage_vs_limits.assert_awaited_once()


# ---------------------------------------------------------------------------
# GET /billing/invoices
# ---------------------------------------------------------------------------


class TestInvoiceListEndpoint:
    """Verify GET /api/v1/billing/invoices responses."""

    @pytest.mark.asyncio
    async def test_returns_invoice_list(self, client: AsyncClient) -> None:
        """Admin receives 200 with invoices array and total count."""
        mock_result: dict[str, Any] = {
            "invoices": [
                {
                    "invoice_id": "inv-001",
                    "invoice_number": "INV-2026-001",
                    "amount_usd": 49.99,
                    "subtotal_usd": 49.99,
                    "tax_usd": 0.0,
                    "total_usd": 49.99,
                    "status": "paid",
                    "issued_at": "2026-01-01T00:00:00+00:00",
                    "period_start": "2025-12-01T00:00:00+00:00",
                    "period_end": "2025-12-31T23:59:59+00:00",
                },
                {
                    "invoice_id": "inv-002",
                    "invoice_number": "INV-2026-002",
                    "amount_usd": 99.99,
                    "subtotal_usd": 99.99,
                    "tax_usd": 0.0,
                    "total_usd": 99.99,
                    "status": "paid",
                    "issued_at": "2026-02-01T00:00:00+00:00",
                    "period_start": "2026-01-01T00:00:00+00:00",
                    "period_end": "2026-01-31T23:59:59+00:00",
                },
            ],
            "total": 2,
        }

        with patch("api.routers.billing.InvoiceService") as MockInvoice:
            instance = MockInvoice.return_value
            instance.list_invoices = AsyncMock(return_value=mock_result)

            resp = await client.get("/api/v1/billing/invoices")

        assert resp.status_code == 200
        body = resp.json()
        assert body["total"] == 2
        assert len(body["invoices"]) == 2
        assert body["invoices"][0]["invoice_id"] == "inv-001"
        assert body["invoices"][1]["total_usd"] == 99.99

        instance.list_invoices.assert_awaited_once_with(20, 0)

    @pytest.mark.asyncio
    async def test_pagination_params(self, client: AsyncClient) -> None:
        """Custom limit and offset are forwarded to the service."""
        mock_result: dict[str, Any] = {"invoices": [], "total": 0}

        with patch("api.routers.billing.InvoiceService") as MockInvoice:
            instance = MockInvoice.return_value
            instance.list_invoices = AsyncMock(return_value=mock_result)

            resp = await client.get("/api/v1/billing/invoices?limit=5&offset=10")

        assert resp.status_code == 200
        instance.list_invoices.assert_awaited_once_with(5, 10)

    @pytest.mark.asyncio
    async def test_non_admin_forbidden(self, client: AsyncClient) -> None:
        """Viewer role lacks VIEW_INVOICES permission and gets 403."""
        resp = await client.get(
            "/api/v1/billing/invoices",
            headers=_VIEWER_HEADERS,
        )

        assert resp.status_code == 403
        assert "permission denied" in resp.json()["detail"].lower()


# ---------------------------------------------------------------------------
# GET /billing/invoices/{invoice_id}
# ---------------------------------------------------------------------------


class TestInvoiceDetailEndpoint:
    """Verify GET /api/v1/billing/invoices/{invoice_id} responses."""

    @pytest.mark.asyncio
    async def test_returns_invoice(self, client: AsyncClient) -> None:
        """Admin receives 200 with full invoice data including line items."""
        mock_invoice: dict[str, Any] = {
            "invoice_id": "inv-001",
            "invoice_number": "INV-2026-001",
            "tenant_id": "default",
            "amount_usd": 49.99,
            "subtotal_usd": 49.99,
            "tax_usd": 0.0,
            "total_usd": 49.99,
            "status": "paid",
            "issued_at": "2026-01-01T00:00:00+00:00",
            "period_start": "2025-12-01T00:00:00+00:00",
            "period_end": "2025-12-31T23:59:59+00:00",
            "line_items": [
                {
                    "description": "Team plan subscription",
                    "quantity": 1,
                    "unit_price": 39.99,
                    "amount": 39.99,
                },
                {
                    "description": "Metered AI calls overage",
                    "quantity": 50,
                    "unit_price": 0.20,
                    "amount": 10.00,
                },
            ],
        }

        with patch("api.routers.billing.InvoiceService") as MockInvoice:
            instance = MockInvoice.return_value
            instance.get_invoice = AsyncMock(return_value=mock_invoice)

            resp = await client.get("/api/v1/billing/invoices/inv-001")

        assert resp.status_code == 200
        body = resp.json()
        assert body["invoice_id"] == "inv-001"
        assert body["total_usd"] == 49.99
        assert len(body["line_items"]) == 2
        assert body["line_items"][0]["description"] == "Team plan subscription"
        assert body["line_items"][1]["amount"] == 10.00

        instance.get_invoice.assert_awaited_once_with("inv-001")

    @pytest.mark.asyncio
    async def test_not_found(self, client: AsyncClient) -> None:
        """Service returning None maps to 404."""
        with patch("api.routers.billing.InvoiceService") as MockInvoice:
            instance = MockInvoice.return_value
            instance.get_invoice = AsyncMock(return_value=None)

            resp = await client.get("/api/v1/billing/invoices/nonexistent")

        assert resp.status_code == 404
        assert "not found" in resp.json()["detail"].lower()


# ---------------------------------------------------------------------------
# GET /billing/invoices/{invoice_id}/download
# ---------------------------------------------------------------------------


class TestInvoiceDownloadEndpoint:
    """Verify GET /api/v1/billing/invoices/{invoice_id}/download responses."""

    @pytest.mark.asyncio
    async def test_returns_pdf(self, client: AsyncClient) -> None:
        """Admin receives 200 with application/pdf content type and correct headers."""
        fake_pdf = b"fake-pdf-bytes"

        with patch("api.routers.billing.InvoiceService") as MockInvoice:
            instance = MockInvoice.return_value
            instance.get_pdf = AsyncMock(return_value=fake_pdf)

            resp = await client.get("/api/v1/billing/invoices/inv-001/download")

        assert resp.status_code == 200
        assert resp.headers["content-type"] == "application/pdf"
        assert "Content-Disposition" in resp.headers or "content-disposition" in resp.headers
        disposition = resp.headers.get("content-disposition", resp.headers.get("Content-Disposition", ""))
        assert "invoice-inv-001.pdf" in disposition
        assert resp.content == fake_pdf

        instance.get_pdf.assert_awaited_once_with("inv-001")

    @pytest.mark.asyncio
    async def test_not_found(self, client: AsyncClient) -> None:
        """Service returning None for PDF maps to 404."""
        with patch("api.routers.billing.InvoiceService") as MockInvoice:
            instance = MockInvoice.return_value
            instance.get_pdf = AsyncMock(return_value=None)

            resp = await client.get("/api/v1/billing/invoices/inv-002/download")

        assert resp.status_code == 404
        assert "not found" in resp.json()["detail"].lower()

    @pytest.mark.asyncio
    async def test_non_admin_forbidden(self, client: AsyncClient) -> None:
        """Viewer role lacks VIEW_INVOICES permission and gets 403."""
        resp = await client.get(
            "/api/v1/billing/invoices/inv-001/download",
            headers=_VIEWER_HEADERS,
        )

        assert resp.status_code == 403
        assert "permission denied" in resp.json()["detail"].lower()

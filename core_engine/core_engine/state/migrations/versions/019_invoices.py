"""Add invoices table.

Creates the ``invoices`` table for storing generated invoice records,
line items, and PDF storage references.

Revision ID: 019
Revises: 018
Create Date: 2026-02-23 00:00:00.000000+00:00

"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

# revision identifiers, used by Alembic.
revision: str = "019"
down_revision: str | None = "018"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "invoices",
        sa.Column("invoice_id", sa.String(64), primary_key=True),
        sa.Column("tenant_id", sa.String(64), nullable=False),
        sa.Column("stripe_invoice_id", sa.String(256), nullable=True),
        sa.Column("invoice_number", sa.String(64), nullable=False),
        sa.Column("period_start", sa.DateTime(timezone=True), nullable=False),
        sa.Column("period_end", sa.DateTime(timezone=True), nullable=False),
        sa.Column("subtotal_usd", sa.Float(), nullable=False),
        sa.Column(
            "tax_usd",
            sa.Float(),
            nullable=False,
            server_default="0.0",
        ),
        sa.Column("total_usd", sa.Float(), nullable=False),
        sa.Column("line_items_json", JSONB(), nullable=False),
        sa.Column("pdf_storage_key", sa.String(1024), nullable=True),
        sa.Column(
            "status",
            sa.String(32),
            nullable=False,
            server_default="'generated'",
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )

    op.create_index(
        "ix_invoices_tenant_created",
        "invoices",
        ["tenant_id", "created_at"],
    )
    op.create_index(
        "ix_invoices_stripe_invoice",
        "invoices",
        ["stripe_invoice_id"],
    )
    op.create_index(
        "ix_invoices_tenant_period",
        "invoices",
        ["tenant_id", "period_start", "period_end"],
    )

    # Enable RLS on the new table.
    op.execute("ALTER TABLE invoices ENABLE ROW LEVEL SECURITY")
    op.execute(
        "CREATE POLICY tenant_isolation_invoices ON invoices USING (tenant_id = current_setting('app.tenant_id', true))"
    )


def downgrade() -> None:
    op.execute("DROP POLICY IF EXISTS tenant_isolation_invoices ON invoices")
    op.drop_index("ix_invoices_tenant_period")
    op.drop_index("ix_invoices_stripe_invoice")
    op.drop_index("ix_invoices_tenant_created")
    op.drop_table("invoices")

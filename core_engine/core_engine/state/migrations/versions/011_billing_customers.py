"""Add billing_customers table for Stripe integration.

Creates the ``billing_customers`` table mapping IronLayer tenants to
their Stripe customer and subscription identifiers.

Revision ID: 011
Revises: 010
Create Date: 2026-02-21 00:00:00.000000+00:00

"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "011"
down_revision: str | None = "010"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "billing_customers",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("tenant_id", sa.String(64), nullable=False, unique=True),
        sa.Column("stripe_customer_id", sa.String(256), nullable=False),
        sa.Column("stripe_subscription_id", sa.String(256), nullable=True),
        sa.Column("plan_tier", sa.String(32), nullable=False, server_default="community"),
        sa.Column("period_start", sa.DateTime(timezone=True), nullable=True),
        sa.Column("period_end", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )

    op.create_index(
        "ix_billing_customers_tenant",
        "billing_customers",
        ["tenant_id"],
    )
    op.create_index(
        "ix_billing_customers_stripe_customer",
        "billing_customers",
        ["stripe_customer_id"],
    )

    # Enable RLS on the new table.
    op.execute("ALTER TABLE billing_customers ENABLE ROW LEVEL SECURITY")
    op.execute(
        "CREATE POLICY tenant_isolation_billing_customers ON billing_customers "
        "USING (tenant_id = current_setting('app.tenant_id', true))"
    )


def downgrade() -> None:
    op.execute("DROP POLICY IF EXISTS tenant_isolation_billing_customers ON billing_customers")
    op.drop_index("ix_billing_customers_stripe_customer")
    op.drop_index("ix_billing_customers_tenant")
    op.drop_table("billing_customers")

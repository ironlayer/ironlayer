"""Add event_subscriptions table for webhook delivery.

Revision ID: 014
Revises: 013
Create Date: 2025-01-01 00:00:00.000000

"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

# revision identifiers, used by Alembic.
revision = "014"
down_revision = "013"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "event_subscriptions",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("tenant_id", sa.String(64), nullable=False),
        sa.Column("name", sa.String(256), nullable=False),
        sa.Column("url", sa.String(2048), nullable=False),
        sa.Column("secret_hash", sa.String(256), nullable=True),
        sa.Column("event_types", JSONB(), nullable=True),
        sa.Column("active", sa.Boolean(), server_default=sa.text("true"), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
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
        sa.PrimaryKeyConstraint("id"),
    )

    op.create_index(
        "ix_event_sub_tenant",
        "event_subscriptions",
        ["tenant_id"],
    )
    op.create_index(
        "ix_event_sub_tenant_active",
        "event_subscriptions",
        ["tenant_id", "active"],
    )

    # RLS policy for multi-tenant isolation.
    op.execute("ALTER TABLE event_subscriptions ENABLE ROW LEVEL SECURITY")
    op.execute("""
        CREATE POLICY event_subscriptions_tenant_isolation
        ON event_subscriptions
        USING (tenant_id = current_setting('app.tenant_id', true))
        WITH CHECK (tenant_id = current_setting('app.tenant_id', true))
        """)


def downgrade() -> None:
    op.execute("DROP POLICY IF EXISTS event_subscriptions_tenant_isolation ON event_subscriptions")
    op.drop_index("ix_event_sub_tenant_active", table_name="event_subscriptions")
    op.drop_index("ix_event_sub_tenant", table_name="event_subscriptions")
    op.drop_table("event_subscriptions")

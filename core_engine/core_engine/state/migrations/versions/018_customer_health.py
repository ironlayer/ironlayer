"""Add customer_health table.

Creates the ``customer_health`` table for tracking per-tenant engagement
metrics, health scores, and churn risk signals.

Revision ID: 018
Revises: 017
Create Date: 2026-02-23 00:00:00.000000+00:00

"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

# revision identifiers, used by Alembic.
revision: str = "018"
down_revision: str | None = "017"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "customer_health",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("tenant_id", sa.String(64), nullable=False, unique=True),
        sa.Column(
            "health_score",
            sa.Float(),
            nullable=False,
            server_default="100.0",
        ),
        sa.Column(
            "health_status",
            sa.String(32),
            nullable=False,
            server_default="'active'",
        ),
        sa.Column("last_login_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_plan_run_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_ai_call_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("engagement_metrics_json", JSONB(), nullable=True),
        sa.Column("trend_direction", sa.String(32), nullable=True),
        sa.Column("previous_score", sa.Float(), nullable=True),
        sa.Column(
            "computed_at",
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
        "ix_customer_health_tenant",
        "customer_health",
        ["tenant_id"],
        unique=True,
    )
    op.create_index(
        "ix_customer_health_status",
        "customer_health",
        ["health_status"],
    )
    op.create_index(
        "ix_customer_health_score",
        "customer_health",
        ["health_score"],
    )

    # Enable RLS on the new table.
    op.execute("ALTER TABLE customer_health ENABLE ROW LEVEL SECURITY")
    op.execute(
        "CREATE POLICY tenant_isolation_customer_health ON customer_health "
        "USING (tenant_id = current_setting('app.tenant_id', true))"
    )


def downgrade() -> None:
    op.execute("DROP POLICY IF EXISTS tenant_isolation_customer_health ON customer_health")
    op.drop_index("ix_customer_health_score")
    op.drop_index("ix_customer_health_status")
    op.drop_index("ix_customer_health_tenant")
    op.drop_table("customer_health")

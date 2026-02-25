"""Create reconciliation_checks table.

Records reconciliation checks comparing control-plane run state to the
actual outcome observed in the execution backend (e.g., Databricks).

Revision ID: 007
Revises: 006
Create Date: 2026-02-21 00:00:00.000000+00:00

"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers
revision: str = "007"
down_revision: str | Sequence[str] = "006"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "reconciliation_checks",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("tenant_id", sa.String(64), nullable=False),
        sa.Column("run_id", sa.String(64), nullable=False),
        sa.Column("model_name", sa.String(512), nullable=False),
        sa.Column("expected_status", sa.String(32), nullable=False),
        sa.Column("warehouse_status", sa.String(32), nullable=False),
        sa.Column("discrepancy_type", sa.String(64), nullable=True),
        sa.Column("resolved", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("resolved_by", sa.String(256), nullable=True),
        sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("resolution_note", sa.Text(), nullable=True),
        sa.Column(
            "checked_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
    )

    op.create_index(
        "ix_reconciliation_tenant_run",
        "reconciliation_checks",
        ["tenant_id", "run_id"],
    )
    op.create_index(
        "ix_reconciliation_tenant_unresolved",
        "reconciliation_checks",
        ["tenant_id", "resolved"],
    )
    op.create_index(
        "ix_reconciliation_checked_at",
        "reconciliation_checks",
        ["tenant_id", "checked_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_reconciliation_checked_at", table_name="reconciliation_checks")
    op.drop_index("ix_reconciliation_tenant_unresolved", table_name="reconciliation_checks")
    op.drop_index("ix_reconciliation_tenant_run", table_name="reconciliation_checks")
    op.drop_table("reconciliation_checks")

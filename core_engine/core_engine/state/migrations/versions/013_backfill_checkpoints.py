"""Add backfill_checkpoints and backfill_audit tables.

Supports chunked backfill execution with checkpoint-based resume and
per-chunk audit trail.  A long-running backfill over a wide date range
is split into day-sized chunks; each chunk's outcome is recorded in
``backfill_audit`` and overall progress is tracked in
``backfill_checkpoints`` so that a failed backfill can resume from the
last successfully completed chunk instead of restarting from scratch.

Revision ID: 013
Revises: 012
Create Date: 2026-02-21 00:00:00.000000+00:00

"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "013"
down_revision: str | None = "012"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # ------------------------------------------------------------------
    # backfill_checkpoints
    # ------------------------------------------------------------------
    op.create_table(
        "backfill_checkpoints",
        sa.Column("backfill_id", sa.String(64), primary_key=True),
        sa.Column("tenant_id", sa.String(64), nullable=False),
        sa.Column("model_name", sa.String(512), nullable=False),
        sa.Column("overall_start", sa.Date(), nullable=False),
        sa.Column("overall_end", sa.Date(), nullable=False),
        sa.Column("completed_through", sa.Date(), nullable=True),
        sa.Column("chunk_size_days", sa.Integer(), nullable=False, server_default="7"),
        sa.Column(
            "status",
            sa.String(32),
            nullable=False,
            server_default="RUNNING",
        ),
        sa.Column("total_chunks", sa.Integer(), nullable=False),
        sa.Column("completed_chunks", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("cluster_size", sa.String(32), nullable=True),
        sa.Column("plan_id", sa.String(64), nullable=True),
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
        "ix_backfill_checkpoints_tenant_id",
        "backfill_checkpoints",
        ["tenant_id", "backfill_id"],
    )
    op.create_index(
        "ix_backfill_checkpoints_tenant_model_status",
        "backfill_checkpoints",
        ["tenant_id", "model_name", "status"],
    )

    # ------------------------------------------------------------------
    # backfill_audit
    # ------------------------------------------------------------------
    op.create_table(
        "backfill_audit",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("tenant_id", sa.String(64), nullable=False),
        sa.Column("backfill_id", sa.String(64), nullable=False),
        sa.Column("model_name", sa.String(512), nullable=False),
        sa.Column("chunk_start", sa.Date(), nullable=False),
        sa.Column("chunk_end", sa.Date(), nullable=False),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("run_id", sa.String(64), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("duration_seconds", sa.Float(), nullable=True),
        sa.Column(
            "executed_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )

    op.create_index(
        "ix_backfill_audit_tenant_model_executed",
        "backfill_audit",
        ["tenant_id", "model_name", "executed_at"],
    )
    op.create_index(
        "ix_backfill_audit_backfill_id",
        "backfill_audit",
        ["tenant_id", "backfill_id"],
    )

    # Enable RLS on the new tables.
    op.execute("ALTER TABLE backfill_checkpoints ENABLE ROW LEVEL SECURITY")
    op.execute(
        "CREATE POLICY tenant_isolation_backfill_checkpoints ON backfill_checkpoints "
        "USING (tenant_id = current_setting('app.tenant_id', true))"
    )

    op.execute("ALTER TABLE backfill_audit ENABLE ROW LEVEL SECURITY")
    op.execute(
        "CREATE POLICY tenant_isolation_backfill_audit ON backfill_audit "
        "USING (tenant_id = current_setting('app.tenant_id', true))"
    )


def downgrade() -> None:
    op.execute("DROP POLICY IF EXISTS tenant_isolation_backfill_audit ON backfill_audit")
    op.execute("DROP POLICY IF EXISTS tenant_isolation_backfill_checkpoints ON backfill_checkpoints")
    op.drop_index("ix_backfill_audit_backfill_id")
    op.drop_index("ix_backfill_audit_tenant_model_executed")
    op.drop_table("backfill_audit")
    op.drop_index("ix_backfill_checkpoints_tenant_model_status")
    op.drop_index("ix_backfill_checkpoints_tenant_id")
    op.drop_table("backfill_checkpoints")

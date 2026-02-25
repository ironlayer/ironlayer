"""Add webhook_configs table for GitHub integration.

Creates the ``webhook_configs`` table for managing per-tenant webhook
configurations that trigger automated plan generation on push events.

Revision ID: 012
Revises: 011
Create Date: 2026-02-21 00:00:00.000000+00:00

"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "012"
down_revision: str | None = "011"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "webhook_configs",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("tenant_id", sa.String(64), nullable=False),
        sa.Column("provider", sa.String(32), nullable=False, server_default="github"),
        sa.Column("repo_url", sa.String(1024), nullable=False),
        sa.Column("branch", sa.String(256), nullable=False, server_default="main"),
        sa.Column("secret_hash", sa.String(256), nullable=False),
        sa.Column("auto_plan", sa.Boolean(), nullable=False, server_default="true"),
        sa.Column("auto_apply", sa.Boolean(), nullable=False, server_default="false"),
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
        sa.UniqueConstraint(
            "tenant_id",
            "provider",
            "repo_url",
            "branch",
            name="uq_webhook_configs_tenant_provider_repo_branch",
        ),
    )

    op.create_index(
        "ix_webhook_configs_tenant",
        "webhook_configs",
        ["tenant_id"],
    )

    # Enable RLS on the new table.
    op.execute("ALTER TABLE webhook_configs ENABLE ROW LEVEL SECURITY")
    op.execute(
        "CREATE POLICY tenant_isolation_webhook_configs ON webhook_configs "
        "USING (tenant_id = current_setting('app.tenant_id', true))"
    )


def downgrade() -> None:
    op.execute("DROP POLICY IF EXISTS tenant_isolation_webhook_configs ON webhook_configs")
    op.drop_index("ix_webhook_configs_tenant")
    op.drop_table("webhook_configs")

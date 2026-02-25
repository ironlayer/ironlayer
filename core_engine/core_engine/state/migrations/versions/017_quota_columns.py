"""Add quota columns to tenant_config.

Adds ``plan_quota_monthly``, ``api_quota_monthly``, and ``ai_quota_monthly``
nullable INTEGER columns to the ``tenant_config`` table for per-tenant
usage quota enforcement.

Revision ID: 017
Revises: 016
Create Date: 2026-02-23 00:00:00.000000+00:00

"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "017"
down_revision: str | None = "016"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "tenant_config",
        sa.Column("plan_quota_monthly", sa.Integer(), nullable=True),
    )
    op.add_column(
        "tenant_config",
        sa.Column("api_quota_monthly", sa.Integer(), nullable=True),
    )
    op.add_column(
        "tenant_config",
        sa.Column("ai_quota_monthly", sa.Integer(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("tenant_config", "ai_quota_monthly")
    op.drop_column("tenant_config", "api_quota_monthly")
    op.drop_column("tenant_config", "plan_quota_monthly")

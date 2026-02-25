"""Add created_at and deactivated_at columns to tenant_config.

Supports tenant lifecycle management (provisioning + soft-delete).

Revision ID: 005
Revises: 004
Create Date: 2026-02-21 00:00:00.000000+00:00

"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers
revision: str = "005"
down_revision: str | Sequence[str] = "004"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Add created_at with a server default so that existing rows get
    # a value automatically.
    op.add_column(
        "tenant_config",
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )

    # Add deactivated_at (nullable) for soft-delete support.
    op.add_column(
        "tenant_config",
        sa.Column(
            "deactivated_at",
            sa.DateTime(timezone=True),
            nullable=True,
        ),
    )


def downgrade() -> None:
    op.drop_column("tenant_config", "deactivated_at")
    op.drop_column("tenant_config", "created_at")

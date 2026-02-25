"""Add max_seats column to tenant_config.

Stores the maximum number of user seats allowed for a tenant.
``NULL`` means the limit is determined by the tier default
(community=1, team=10, enterprise=unlimited).  An explicit
non-NULL value overrides the tier default, enabling per-tenant
seat overrides for custom contracts.

Revision ID: 024
Revises: 023
Create Date: 2026-02-24 00:00:00.000000+00:00

"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "024"
down_revision: str | None = "023"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "tenant_config",
        sa.Column("max_seats", sa.Integer(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("tenant_config", "max_seats")

"""Add cost_usd and external_run_id columns to runs table.

Supports per-run cost tracking computed from runtime and cluster rate,
plus an optional external run identifier for cross-referencing with
external orchestration systems (e.g. Databricks job run IDs).

Revision ID: 006
Revises: 005
Create Date: 2026-02-21 00:00:00.000000+00:00

"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers
revision: str = "006"
down_revision: str | Sequence[str] = "005"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Add cost_usd column for storing computed run costs.
    op.add_column(
        "runs",
        sa.Column("cost_usd", sa.Float(), nullable=True),
    )

    # Add external_run_id for cross-referencing with external systems.
    op.add_column(
        "runs",
        sa.Column("external_run_id", sa.String(256), nullable=True),
    )

    # Index on external_run_id for fast lookups by external reference.
    op.create_index(
        "ix_runs_external_run_id",
        "runs",
        ["external_run_id"],
    )


def downgrade() -> None:
    op.drop_index("ix_runs_external_run_id", table_name="runs")
    op.drop_column("runs", "external_run_id")
    op.drop_column("runs", "cost_usd")

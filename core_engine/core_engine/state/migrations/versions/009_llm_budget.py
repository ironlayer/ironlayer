"""Add LLM usage tracking and budget columns.

Creates the ``llm_usage_log`` table for per-call LLM usage tracking and
adds ``llm_monthly_budget_usd`` / ``llm_daily_budget_usd`` columns to
``tenant_config`` for per-tenant budget guardrails.

Revision ID: 009
Revises: 008
Create Date: 2026-02-21 00:00:00.000000+00:00

"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers
revision: str = "009"
down_revision: str | Sequence[str] = "008"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # --- LLM usage log table ---
    op.create_table(
        "llm_usage_log",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("tenant_id", sa.String(64), nullable=False),
        sa.Column("call_type", sa.String(64), nullable=False),
        sa.Column("model_id", sa.String(128), nullable=False),
        sa.Column("input_tokens", sa.Integer(), nullable=False),
        sa.Column("output_tokens", sa.Integer(), nullable=False),
        sa.Column("estimated_cost_usd", sa.Float(), nullable=False),
        sa.Column("latency_ms", sa.Integer(), nullable=False),
        sa.Column("success", sa.Boolean(), nullable=False),
        sa.Column("error_type", sa.String(128), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
    )

    op.create_index(
        "ix_llm_usage_tenant_created",
        "llm_usage_log",
        ["tenant_id", "created_at"],
    )
    op.create_index(
        "ix_llm_usage_tenant_type",
        "llm_usage_log",
        ["tenant_id", "call_type"],
    )

    # --- Budget columns on tenant_config ---
    op.add_column(
        "tenant_config",
        sa.Column("llm_monthly_budget_usd", sa.Float(), nullable=True),
    )
    op.add_column(
        "tenant_config",
        sa.Column("llm_daily_budget_usd", sa.Float(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("tenant_config", "llm_daily_budget_usd")
    op.drop_column("tenant_config", "llm_monthly_budget_usd")
    op.drop_index("ix_llm_usage_tenant_type", table_name="llm_usage_log")
    op.drop_index("ix_llm_usage_tenant_created", table_name="llm_usage_log")
    op.drop_table("llm_usage_log")

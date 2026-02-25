"""Convert financial Float columns to Numeric for precision.

Replaces imprecise ``Float`` types with ``Numeric(14, 4)`` on all
monetary columns and ``Numeric(6, 2)`` on score columns to eliminate
floating-point rounding errors in financial calculations and health
score comparisons.

Revision ID: 021
Revises: 020
Create Date: 2026-02-24 00:00:00.000000+00:00

"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "021"
down_revision: str | None = "020"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # -- Monetary columns -> Numeric(14, 4) --

    # runs.cost_usd
    op.alter_column(
        "runs",
        "cost_usd",
        existing_type=sa.Float(),
        type_=sa.Numeric(14, 4),
        existing_nullable=True,
        postgresql_using="cost_usd::NUMERIC(14,4)",
    )

    # tenant_config.llm_monthly_budget_usd
    op.alter_column(
        "tenant_config",
        "llm_monthly_budget_usd",
        existing_type=sa.Float(),
        type_=sa.Numeric(14, 4),
        existing_nullable=True,
        postgresql_using="llm_monthly_budget_usd::NUMERIC(14,4)",
    )

    # tenant_config.llm_daily_budget_usd
    op.alter_column(
        "tenant_config",
        "llm_daily_budget_usd",
        existing_type=sa.Float(),
        type_=sa.Numeric(14, 4),
        existing_nullable=True,
        postgresql_using="llm_daily_budget_usd::NUMERIC(14,4)",
    )

    # llm_usage_log.estimated_cost_usd
    op.alter_column(
        "llm_usage_log",
        "estimated_cost_usd",
        existing_type=sa.Float(),
        type_=sa.Numeric(14, 4),
        existing_nullable=False,
        postgresql_using="estimated_cost_usd::NUMERIC(14,4)",
    )

    # invoices.subtotal_usd
    op.alter_column(
        "invoices",
        "subtotal_usd",
        existing_type=sa.Float(),
        type_=sa.Numeric(14, 4),
        existing_nullable=False,
        postgresql_using="subtotal_usd::NUMERIC(14,4)",
    )

    # invoices.tax_usd
    op.alter_column(
        "invoices",
        "tax_usd",
        existing_type=sa.Float(),
        type_=sa.Numeric(14, 4),
        existing_nullable=False,
        postgresql_using="tax_usd::NUMERIC(14,4)",
    )

    # invoices.total_usd
    op.alter_column(
        "invoices",
        "total_usd",
        existing_type=sa.Float(),
        type_=sa.Numeric(14, 4),
        existing_nullable=False,
        postgresql_using="total_usd::NUMERIC(14,4)",
    )

    # -- Score columns -> Numeric(6, 2) --

    # customer_health.health_score
    op.alter_column(
        "customer_health",
        "health_score",
        existing_type=sa.Float(),
        type_=sa.Numeric(6, 2),
        existing_nullable=False,
        postgresql_using="health_score::NUMERIC(6,2)",
    )

    # customer_health.previous_score
    op.alter_column(
        "customer_health",
        "previous_score",
        existing_type=sa.Float(),
        type_=sa.Numeric(6, 2),
        existing_nullable=True,
        postgresql_using="previous_score::NUMERIC(6,2)",
    )


def downgrade() -> None:
    # -- Restore score columns to Float --

    op.alter_column(
        "customer_health",
        "previous_score",
        existing_type=sa.Numeric(6, 2),
        type_=sa.Float(),
        existing_nullable=True,
        postgresql_using="previous_score::DOUBLE PRECISION",
    )

    op.alter_column(
        "customer_health",
        "health_score",
        existing_type=sa.Numeric(6, 2),
        type_=sa.Float(),
        existing_nullable=False,
        postgresql_using="health_score::DOUBLE PRECISION",
    )

    # -- Restore monetary columns to Float --

    op.alter_column(
        "invoices",
        "total_usd",
        existing_type=sa.Numeric(14, 4),
        type_=sa.Float(),
        existing_nullable=False,
        postgresql_using="total_usd::DOUBLE PRECISION",
    )

    op.alter_column(
        "invoices",
        "tax_usd",
        existing_type=sa.Numeric(14, 4),
        type_=sa.Float(),
        existing_nullable=False,
        postgresql_using="tax_usd::DOUBLE PRECISION",
    )

    op.alter_column(
        "invoices",
        "subtotal_usd",
        existing_type=sa.Numeric(14, 4),
        type_=sa.Float(),
        existing_nullable=False,
        postgresql_using="subtotal_usd::DOUBLE PRECISION",
    )

    op.alter_column(
        "llm_usage_log",
        "estimated_cost_usd",
        existing_type=sa.Numeric(14, 4),
        type_=sa.Float(),
        existing_nullable=False,
        postgresql_using="estimated_cost_usd::DOUBLE PRECISION",
    )

    op.alter_column(
        "tenant_config",
        "llm_daily_budget_usd",
        existing_type=sa.Numeric(14, 4),
        type_=sa.Float(),
        existing_nullable=True,
        postgresql_using="llm_daily_budget_usd::DOUBLE PRECISION",
    )

    op.alter_column(
        "tenant_config",
        "llm_monthly_budget_usd",
        existing_type=sa.Numeric(14, 4),
        type_=sa.Float(),
        existing_nullable=True,
        postgresql_using="llm_monthly_budget_usd::DOUBLE PRECISION",
    )

    op.alter_column(
        "runs",
        "cost_usd",
        existing_type=sa.Numeric(14, 4),
        type_=sa.Float(),
        existing_nullable=True,
        postgresql_using="cost_usd::DOUBLE PRECISION",
    )

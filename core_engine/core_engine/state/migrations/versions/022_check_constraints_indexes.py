"""Add CHECK constraints and supplementary indexes.

Adds CHECK constraints on status/type enum columns to enforce valid
values at the database level, and creates additional indexes for
common query patterns.

Revision ID: 022
Revises: 021
Create Date: 2026-02-24 00:00:00.000000+00:00

"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "022"
down_revision: str | None = "021"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # ------------------------------------------------------------------
    # CHECK constraints (PostgreSQL only — using raw SQL for reliability)
    # ------------------------------------------------------------------

    op.execute(
        "ALTER TABLE runs ADD CONSTRAINT ck_runs_status "
        "CHECK (status IN ('PENDING','RUNNING','COMPLETED','FAILED','CANCELLED'))"
    )

    op.execute(
        "ALTER TABLE backfill_checkpoints ADD CONSTRAINT ck_backfill_checkpoints_status "
        "CHECK (status IN ('RUNNING','COMPLETED','FAILED'))"
    )

    op.execute(
        "ALTER TABLE backfill_audit ADD CONSTRAINT ck_backfill_audit_status "
        "CHECK (status IN ('RUNNING','SUCCESS','FAILED'))"
    )

    op.execute(
        "ALTER TABLE schema_drift_checks ADD CONSTRAINT ck_schema_drift_checks_drift_type "
        "CHECK (drift_type IN ('COLUMN_ADDED','COLUMN_REMOVED','TYPE_CHANGED','NONE'))"
    )

    op.execute(
        "ALTER TABLE model_tests ADD CONSTRAINT ck_model_tests_severity CHECK (severity IN ('BLOCK','WARN','INFO'))"
    )

    op.execute(
        "ALTER TABLE customer_health ADD CONSTRAINT ck_customer_health_health_status "
        "CHECK (health_status IN ('active','at_risk','churning'))"
    )

    op.execute("ALTER TABLE invoices ADD CONSTRAINT ck_invoices_status CHECK (status IN ('generated','paid','void'))")

    # ------------------------------------------------------------------
    # Supplementary indexes
    # ------------------------------------------------------------------

    op.create_index(
        "ix_model_versions_tenant",
        "model_versions",
        ["tenant_id"],
    )

    op.create_index(
        "ix_invoices_tenant_number",
        "invoices",
        ["tenant_id", "invoice_number"],
        unique=True,
    )

    op.create_index(
        "ix_runs_tenant_model",
        "runs",
        ["tenant_id", "model_name"],
    )

    op.create_index(
        "ix_usage_events_tenant_type_month",
        "usage_events",
        ["tenant_id", "event_type", "created_at"],
    )


def downgrade() -> None:
    # ------------------------------------------------------------------
    # Drop indexes (reverse order)
    # ------------------------------------------------------------------

    op.drop_index("ix_usage_events_tenant_type_month", table_name="usage_events")
    op.drop_index("ix_runs_tenant_model", table_name="runs")
    op.drop_index("ix_invoices_tenant_number", table_name="invoices")
    op.drop_index("ix_model_versions_tenant", table_name="model_versions")

    # ------------------------------------------------------------------
    # Drop CHECK constraints (reverse order)
    # ------------------------------------------------------------------

    op.execute("ALTER TABLE invoices DROP CONSTRAINT IF EXISTS ck_invoices_status")
    op.execute("ALTER TABLE customer_health DROP CONSTRAINT IF EXISTS ck_customer_health_health_status")
    op.execute("ALTER TABLE model_tests DROP CONSTRAINT IF EXISTS ck_model_tests_severity")
    op.execute("ALTER TABLE schema_drift_checks DROP CONSTRAINT IF EXISTS ck_schema_drift_checks_drift_type")
    op.execute("ALTER TABLE backfill_audit DROP CONSTRAINT IF EXISTS ck_backfill_audit_status")
    op.execute("ALTER TABLE backfill_checkpoints DROP CONSTRAINT IF EXISTS ck_backfill_checkpoints_status")
    op.execute("ALTER TABLE runs DROP CONSTRAINT IF EXISTS ck_runs_status")

"""Create environments, environment_promotions, model_tests, test_results,
schema_drift_checks, and reconciliation_schedules tables.

Revision ID: 016
Revises: 015
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

# revision identifiers, used by Alembic.
revision = "016"
down_revision = "015"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # -----------------------------------------------------------------------
    # environments
    # -----------------------------------------------------------------------
    op.create_table(
        "environments",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("tenant_id", sa.String(64), nullable=False),
        sa.Column("name", sa.String(128), nullable=False),
        sa.Column("catalog", sa.String(256), nullable=False),
        sa.Column("schema_prefix", sa.String(256), nullable=False),
        sa.Column("is_default", sa.Boolean, default=False, nullable=False),
        sa.Column("is_production", sa.Boolean, default=False, nullable=False),
        sa.Column("is_ephemeral", sa.Boolean, default=False, nullable=False),
        sa.Column("pr_number", sa.Integer, nullable=True),
        sa.Column("branch_name", sa.String(256), nullable=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_by", sa.String(256), nullable=False),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
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
        "ix_env_tenant_name",
        "environments",
        ["tenant_id", "name"],
        unique=True,
    )
    op.create_index("ix_env_tenant_id", "environments", ["tenant_id"])

    # -----------------------------------------------------------------------
    # environment_promotions
    # -----------------------------------------------------------------------
    op.create_table(
        "environment_promotions",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("tenant_id", sa.String(64), nullable=False),
        sa.Column("source_environment", sa.String(128), nullable=False),
        sa.Column("target_environment", sa.String(128), nullable=False),
        sa.Column("source_snapshot_id", sa.String(128), nullable=False),
        sa.Column("target_snapshot_id", sa.String(128), nullable=False),
        sa.Column("promoted_by", sa.String(256), nullable=False),
        sa.Column(
            "promoted_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column("metadata_json", JSONB, nullable=True),
    )
    op.create_index(
        "ix_promotion_tenant_source",
        "environment_promotions",
        ["tenant_id", "source_environment"],
    )
    op.create_index(
        "ix_promotion_tenant_target",
        "environment_promotions",
        ["tenant_id", "target_environment"],
    )
    op.create_index(
        "ix_promotion_promoted_at",
        "environment_promotions",
        ["tenant_id", "promoted_at"],
    )

    # -----------------------------------------------------------------------
    # model_tests
    # -----------------------------------------------------------------------
    op.create_table(
        "model_tests",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("tenant_id", sa.String(64), nullable=False),
        sa.Column("test_id", sa.String(64), nullable=False),
        sa.Column("model_name", sa.String(512), nullable=False),
        sa.Column("test_type", sa.String(64), nullable=False),
        sa.Column("test_config_json", JSONB, nullable=True),
        sa.Column("severity", sa.String(32), default="BLOCK", nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )
    op.create_index(
        "ix_model_test_tenant_model",
        "model_tests",
        ["tenant_id", "model_name"],
    )
    op.create_index(
        "ix_model_test_tenant_id",
        "model_tests",
        ["tenant_id", "test_id"],
        unique=True,
    )

    # -----------------------------------------------------------------------
    # test_results
    # -----------------------------------------------------------------------
    op.create_table(
        "test_results",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("tenant_id", sa.String(64), nullable=False),
        sa.Column("test_id", sa.String(64), nullable=False),
        sa.Column("plan_id", sa.String(64), nullable=True),
        sa.Column("model_name", sa.String(512), nullable=False),
        sa.Column("test_type", sa.String(64), nullable=False),
        sa.Column("passed", sa.Boolean, nullable=False),
        sa.Column("failure_message", sa.Text, nullable=True),
        sa.Column("execution_mode", sa.String(32), nullable=False),
        sa.Column("duration_ms", sa.Integer, default=0, nullable=False),
        sa.Column(
            "executed_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )
    op.create_index(
        "ix_test_result_tenant_plan",
        "test_results",
        ["tenant_id", "plan_id"],
    )
    op.create_index(
        "ix_test_result_tenant_model",
        "test_results",
        ["tenant_id", "model_name"],
    )
    op.create_index(
        "ix_test_result_executed_at",
        "test_results",
        ["tenant_id", "executed_at"],
    )

    # -----------------------------------------------------------------------
    # schema_drift_checks
    # -----------------------------------------------------------------------
    op.create_table(
        "schema_drift_checks",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("tenant_id", sa.String(64), nullable=False),
        sa.Column("model_name", sa.String(512), nullable=False),
        sa.Column("expected_columns_json", JSONB, nullable=True),
        sa.Column("actual_columns_json", JSONB, nullable=True),
        sa.Column("drift_type", sa.String(64), nullable=False),
        sa.Column("drift_details_json", JSONB, nullable=True),
        sa.Column("resolved", sa.Boolean, default=False, nullable=False),
        sa.Column("resolved_by", sa.String(256), nullable=True),
        sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("resolution_note", sa.Text, nullable=True),
        sa.Column(
            "checked_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )
    op.create_index(
        "ix_schema_drift_tenant_model",
        "schema_drift_checks",
        ["tenant_id", "model_name"],
    )
    op.create_index(
        "ix_schema_drift_tenant_unresolved",
        "schema_drift_checks",
        ["tenant_id", "resolved"],
    )
    op.create_index(
        "ix_schema_drift_checked_at",
        "schema_drift_checks",
        ["tenant_id", "checked_at"],
    )

    # -----------------------------------------------------------------------
    # reconciliation_schedules
    # -----------------------------------------------------------------------
    op.create_table(
        "reconciliation_schedules",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("tenant_id", sa.String(64), nullable=False),
        sa.Column("schedule_type", sa.String(64), nullable=False),
        sa.Column("cron_expression", sa.String(128), nullable=False),
        sa.Column("enabled", sa.Boolean, default=True, nullable=False),
        sa.Column("last_run_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("next_run_at", sa.DateTime(timezone=True), nullable=True),
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
        "ix_recon_schedule_tenant_type",
        "reconciliation_schedules",
        ["tenant_id", "schedule_type"],
        unique=True,
    )

    # -----------------------------------------------------------------------
    # RLS policies for new tables
    # -----------------------------------------------------------------------
    for table_name in (
        "environments",
        "environment_promotions",
        "model_tests",
        "test_results",
        "schema_drift_checks",
        "reconciliation_schedules",
    ):
        op.execute(f"ALTER TABLE {table_name} ENABLE ROW LEVEL SECURITY")
        op.execute(
            f"CREATE POLICY {table_name}_tenant_isolation ON {table_name} "
            f"USING (tenant_id = current_setting('app.tenant_id', true))"
        )


def downgrade() -> None:
    for table_name in (
        "reconciliation_schedules",
        "schema_drift_checks",
        "test_results",
        "model_tests",
        "environment_promotions",
        "environments",
    ):
        op.execute(f"DROP POLICY IF EXISTS {table_name}_tenant_isolation ON {table_name}")
        op.drop_table(table_name)

"""Initial schema for IronLayer state store.

Creates all core tables: models, model_versions, snapshots, watermarks,
runs, plans, locks, and telemetry.  Every table includes a ``tenant_id``
column for multi-tenant isolation, with corresponding composite indexes
and unique constraints.

Revision ID: 001
Revises: None
Create Date: 2025-05-01 00:00:00.000000+00:00

"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "001"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # ------------------------------------------------------------------
    # models
    # ------------------------------------------------------------------
    op.create_table(
        "models",
        sa.Column("model_name", sa.String(512), primary_key=True),
        sa.Column("tenant_id", sa.String(64), nullable=False, server_default="default"),
        sa.Column("repo_path", sa.String(1024), nullable=False),
        sa.Column("current_version", sa.String(64), nullable=False),
        sa.Column("kind", sa.String(64), nullable=False),
        sa.Column("time_column", sa.String(256), nullable=True),
        sa.Column("unique_key", sa.String(256), nullable=True),
        sa.Column("materialization", sa.String(64), nullable=False),
        sa.Column("owner", sa.String(256), nullable=True),
        sa.Column("tags", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column(
            "last_modified_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.UniqueConstraint("tenant_id", "model_name", name="uq_models_tenant_name"),
    )
    op.create_index("ix_models_tenant", "models", ["tenant_id"])

    # ------------------------------------------------------------------
    # model_versions
    # ------------------------------------------------------------------
    op.create_table(
        "model_versions",
        sa.Column("version_id", sa.String(64), primary_key=True),
        sa.Column("tenant_id", sa.String(64), nullable=False, server_default="default"),
        sa.Column(
            "model_name",
            sa.String(512),
            sa.ForeignKey("models.model_name", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("canonical_sql", sa.Text(), nullable=False),
        sa.Column("canonical_sql_hash", sa.String(64), nullable=False),
        sa.Column("metadata_json", sa.Text(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
    )
    op.create_index("ix_model_versions_model_name", "model_versions", ["model_name"])

    # ------------------------------------------------------------------
    # snapshots
    # ------------------------------------------------------------------
    op.create_table(
        "snapshots",
        sa.Column("snapshot_id", sa.String(64), primary_key=True),
        sa.Column("tenant_id", sa.String(64), nullable=False, server_default="default"),
        sa.Column("environment", sa.String(64), nullable=False),
        sa.Column("model_versions_json", sa.Text(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
    )
    op.create_index("ix_snapshots_environment", "snapshots", ["environment"])
    op.create_index("ix_snapshots_tenant_env", "snapshots", ["tenant_id", "environment"])

    # ------------------------------------------------------------------
    # watermarks
    # ------------------------------------------------------------------
    op.create_table(
        "watermarks",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("tenant_id", sa.String(64), nullable=False, server_default="default"),
        sa.Column("model_name", sa.String(512), nullable=False),
        sa.Column("partition_start", sa.Date(), nullable=False),
        sa.Column("partition_end", sa.Date(), nullable=False),
        sa.Column("row_count", sa.Integer(), nullable=True),
        sa.Column(
            "last_updated",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.UniqueConstraint(
            "tenant_id",
            "model_name",
            "partition_start",
            "partition_end",
            name="uq_watermarks_tenant_model_range",
        ),
    )
    op.create_index("ix_watermarks_model_name", "watermarks", ["model_name"])

    # ------------------------------------------------------------------
    # runs
    # ------------------------------------------------------------------
    op.create_table(
        "runs",
        sa.Column("run_id", sa.String(64), primary_key=True),
        sa.Column("tenant_id", sa.String(64), nullable=False, server_default="default"),
        sa.Column("plan_id", sa.String(64), nullable=False),
        sa.Column("step_id", sa.String(64), nullable=False),
        sa.Column("model_name", sa.String(512), nullable=False),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("input_range_start", sa.Date(), nullable=True),
        sa.Column("input_range_end", sa.Date(), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("logs_uri", sa.String(1024), nullable=True),
        sa.Column("cluster_used", sa.String(256), nullable=True),
        sa.Column("executor_version", sa.String(64), nullable=False),
        sa.Column("retry_count", sa.Integer(), nullable=False, server_default="0"),
    )
    op.create_index("ix_runs_plan_id", "runs", ["plan_id"])
    op.create_index("ix_runs_model_name", "runs", ["model_name"])
    op.create_index("ix_runs_tenant_plan", "runs", ["tenant_id", "plan_id"])
    op.create_index("ix_runs_tenant_model_status", "runs", ["tenant_id", "model_name", "status"])

    # ------------------------------------------------------------------
    # plans
    # ------------------------------------------------------------------
    op.create_table(
        "plans",
        sa.Column("plan_id", sa.String(64), primary_key=True),
        sa.Column("tenant_id", sa.String(64), nullable=False, server_default="default"),
        sa.Column("base_sha", sa.String(64), nullable=False),
        sa.Column("target_sha", sa.String(64), nullable=False),
        sa.Column("plan_json", postgresql.JSONB(), nullable=False),
        sa.Column("approvals_json", postgresql.JSONB(), nullable=True),
        sa.Column("advisory_json", postgresql.JSONB(), nullable=True),
        sa.Column("auto_approved", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
    )
    op.create_index("ix_plans_tenant_created", "plans", ["tenant_id", "created_at"])
    op.create_index(
        "ix_plans_plan_json_gin",
        "plans",
        ["plan_json"],
        postgresql_using="gin",
    )
    op.create_index(
        "ix_plans_advisory_json_gin",
        "plans",
        ["advisory_json"],
        postgresql_using="gin",
    )

    # ------------------------------------------------------------------
    # locks
    # ------------------------------------------------------------------
    op.create_table(
        "locks",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("tenant_id", sa.String(64), nullable=False, server_default="default"),
        sa.Column("model_name", sa.String(512), nullable=False),
        sa.Column("range_start", sa.Date(), nullable=False),
        sa.Column("range_end", sa.Date(), nullable=False),
        sa.Column("locked_by", sa.String(256), nullable=False),
        sa.Column(
            "locked_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column("ttl_seconds", sa.Integer(), nullable=False, server_default="3600"),
        sa.Column("force_release_by", sa.String(256), nullable=True),
        sa.Column("preemption_reason", sa.Text(), nullable=True),
        sa.UniqueConstraint(
            "tenant_id",
            "model_name",
            "range_start",
            "range_end",
            name="uq_locks_tenant_model_range",
        ),
    )
    op.create_index("ix_locks_model_name", "locks", ["model_name"])
    op.create_index("ix_locks_tenant_model", "locks", ["tenant_id", "model_name"])

    # ------------------------------------------------------------------
    # telemetry
    # ------------------------------------------------------------------
    op.create_table(
        "telemetry",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("tenant_id", sa.String(64), nullable=False, server_default="default"),
        sa.Column("run_id", sa.String(64), nullable=False),
        sa.Column("model_name", sa.String(512), nullable=False),
        sa.Column("runtime_seconds", sa.Float(), nullable=False),
        sa.Column("shuffle_bytes", sa.Integer(), nullable=False),
        sa.Column("input_rows", sa.Integer(), nullable=False),
        sa.Column("output_rows", sa.Integer(), nullable=False),
        sa.Column("partition_count", sa.Integer(), nullable=False),
        sa.Column("cluster_id", sa.String(256), nullable=True),
        sa.Column(
            "captured_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
    )
    op.create_index("ix_telemetry_run_id", "telemetry", ["run_id"])
    op.create_index("ix_telemetry_model_name", "telemetry", ["model_name"])
    op.create_index(
        "ix_telemetry_tenant_model_captured",
        "telemetry",
        ["tenant_id", "model_name", "captured_at"],
    )

    # ------------------------------------------------------------------
    # credentials
    # ------------------------------------------------------------------
    op.create_table(
        "credentials",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("tenant_id", sa.String(64), nullable=False),
        sa.Column("credential_name", sa.String(256), nullable=False),
        sa.Column("encrypted_value", sa.Text(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column(
            "last_rotated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.UniqueConstraint("tenant_id", "credential_name", name="uq_credentials_tenant_name"),
    )
    op.create_index("ix_credentials_tenant", "credentials", ["tenant_id"])


def downgrade() -> None:
    op.drop_table("credentials")
    op.drop_table("telemetry")
    op.drop_table("locks")
    op.drop_table("plans")
    op.drop_table("runs")
    op.drop_table("watermarks")
    op.drop_table("snapshots")
    op.drop_table("model_versions")
    op.drop_table("models")

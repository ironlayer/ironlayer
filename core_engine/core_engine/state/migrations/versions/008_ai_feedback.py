"""Create ai_feedback table.

Records AI predictions (cost, risk, classification) and their actual
outcomes after execution, enabling accuracy tracking and model retraining.

Revision ID: 008
Revises: 007
Create Date: 2026-02-21 00:00:00.000000+00:00

"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

# revision identifiers
revision: str = "008"
down_revision: str | Sequence[str] = "007"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "ai_feedback",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("tenant_id", sa.String(64), nullable=False),
        sa.Column("plan_id", sa.String(64), nullable=False),
        sa.Column("step_id", sa.String(64), nullable=False),
        sa.Column("model_name", sa.String(512), nullable=False),
        sa.Column("feedback_type", sa.String(64), nullable=False),
        sa.Column("prediction_json", JSONB, nullable=True),
        sa.Column("outcome_json", JSONB, nullable=True),
        sa.Column("accepted", sa.Boolean(), nullable=True),
        sa.Column("accuracy_score", sa.Float(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
    )

    op.create_index(
        "ix_ai_feedback_tenant_plan",
        "ai_feedback",
        ["tenant_id", "plan_id"],
    )
    op.create_index(
        "ix_ai_feedback_tenant_model",
        "ai_feedback",
        ["tenant_id", "model_name"],
    )
    op.create_index(
        "ix_ai_feedback_tenant_type",
        "ai_feedback",
        ["tenant_id", "feedback_type"],
    )
    op.create_index(
        "ix_ai_feedback_created_at",
        "ai_feedback",
        ["tenant_id", "created_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_ai_feedback_created_at", table_name="ai_feedback")
    op.drop_index("ix_ai_feedback_tenant_type", table_name="ai_feedback")
    op.drop_index("ix_ai_feedback_tenant_model", table_name="ai_feedback")
    op.drop_index("ix_ai_feedback_tenant_plan", table_name="ai_feedback")
    op.drop_table("ai_feedback")

"""Add token_revocations and tenant_config tables; merge branches 002+003.

Revision ID: 004
Revises: 002, 003
Create Date: 2025-05-15 00:00:00.000000+00:00

"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers
revision: str = "004"
down_revision: str | Sequence[str] = ("002", "003")
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # -- token_revocations table -------------------------------------------
    op.create_table(
        "token_revocations",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("tenant_id", sa.String(64), nullable=False),
        sa.Column("jti", sa.String(64), nullable=False),
        sa.Column(
            "revoked_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column("reason", sa.Text(), nullable=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("tenant_id", "jti", name="uq_token_revocations_tenant_jti"),
    )
    op.create_index("ix_token_revocations_jti", "token_revocations", ["jti"])
    op.create_index("ix_token_revocations_tenant", "token_revocations", ["tenant_id"])

    # -- tenant_config table -----------------------------------------------
    op.create_table(
        "tenant_config",
        sa.Column("tenant_id", sa.String(64), nullable=False),
        sa.Column("llm_enabled", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column("updated_by", sa.String(256), nullable=True),
        sa.PrimaryKeyConstraint("tenant_id"),
    )

    # -- RLS policies on new tables ----------------------------------------
    op.execute("""ALTER TABLE token_revocations ENABLE ROW LEVEL SECURITY""")
    op.execute("""ALTER TABLE token_revocations FORCE ROW LEVEL SECURITY""")
    op.execute("""
        CREATE POLICY tenant_isolation_token_revocations ON token_revocations
            USING (tenant_id = current_setting('app.tenant_id', true))
            WITH CHECK (tenant_id = current_setting('app.tenant_id', true))
    """)

    op.execute("""ALTER TABLE tenant_config ENABLE ROW LEVEL SECURITY""")
    op.execute("""ALTER TABLE tenant_config FORCE ROW LEVEL SECURITY""")
    op.execute("""
        CREATE POLICY tenant_isolation_tenant_config ON tenant_config
            USING (tenant_id = current_setting('app.tenant_id', true))
            WITH CHECK (tenant_id = current_setting('app.tenant_id', true))
    """)

    # Also enable RLS on audit_log (was missed in 003)
    op.execute("""ALTER TABLE audit_log ENABLE ROW LEVEL SECURITY""")
    op.execute("""ALTER TABLE audit_log FORCE ROW LEVEL SECURITY""")
    op.execute("""
        CREATE POLICY tenant_isolation_audit_log ON audit_log
            USING (tenant_id = current_setting('app.tenant_id', true))
            WITH CHECK (tenant_id = current_setting('app.tenant_id', true))
    """)


def downgrade() -> None:
    op.execute("DROP POLICY IF EXISTS tenant_isolation_audit_log ON audit_log")
    op.execute("ALTER TABLE audit_log DISABLE ROW LEVEL SECURITY")

    op.execute("DROP POLICY IF EXISTS tenant_isolation_tenant_config ON tenant_config")
    op.execute("ALTER TABLE tenant_config DISABLE ROW LEVEL SECURITY")
    op.drop_table("tenant_config")

    op.execute("DROP POLICY IF EXISTS tenant_isolation_token_revocations ON token_revocations")
    op.execute("ALTER TABLE token_revocations DISABLE ROW LEVEL SECURITY")
    op.drop_table("token_revocations")

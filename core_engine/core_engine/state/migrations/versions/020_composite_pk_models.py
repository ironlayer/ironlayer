"""Composite primary key on models table.

Migrates the ``models`` table from a single-column primary key on
``model_name`` to a composite primary key on ``(tenant_id, model_name)``
for proper multi-tenant isolation.  Updates the foreign key from
``model_versions`` to reference the composite key, and drops the now-
redundant ``uq_models_tenant_name`` unique constraint.

Revision ID: 020
Revises: 019
Create Date: 2026-02-24 00:00:00.000000+00:00

"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "020"
down_revision: str | None = "019"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # 1. Drop the FK from model_versions.model_name -> models.model_name.
    #    The FK was created inline (unnamed) in 001_initial, so PostgreSQL
    #    auto-generated the constraint name.  We use the conventional name.
    op.drop_constraint(
        "model_versions_model_name_fkey",
        "model_versions",
        type_="foreignkey",
    )

    # 2. Drop existing single-column PK on models.model_name.
    op.drop_constraint("models_pkey", "models", type_="primarykey")

    # 3. Create composite PK on models(tenant_id, model_name).
    op.create_primary_key(
        "models_pkey",
        "models",
        ["tenant_id", "model_name"],
    )

    # 4. Create composite FK on model_versions(tenant_id, model_name)
    #    -> models(tenant_id, model_name) with ON DELETE CASCADE.
    op.create_foreign_key(
        "fk_model_versions_tenant_model",
        "model_versions",
        "models",
        ["tenant_id", "model_name"],
        ["tenant_id", "model_name"],
        ondelete="CASCADE",
    )

    # 5. Drop the now-redundant unique constraint (the composite PK
    #    already enforces uniqueness on (tenant_id, model_name)).
    op.drop_constraint("uq_models_tenant_name", "models", type_="unique")


def downgrade() -> None:
    # Reverse all steps in reverse order.

    # 5. Re-create the unique constraint.
    op.create_unique_constraint(
        "uq_models_tenant_name",
        "models",
        ["tenant_id", "model_name"],
    )

    # 4. Drop the composite FK.
    op.drop_constraint(
        "fk_model_versions_tenant_model",
        "model_versions",
        type_="foreignkey",
    )

    # 3. Drop the composite PK.
    op.drop_constraint("models_pkey", "models", type_="primarykey")

    # 2. Re-create the single-column PK on model_name.
    op.create_primary_key("models_pkey", "models", ["model_name"])

    # 1. Re-create the original FK from model_versions.model_name
    #    -> models.model_name.
    op.create_foreign_key(
        "model_versions_model_name_fkey",
        "model_versions",
        "models",
        ["model_name"],
        ["model_name"],
        ondelete="CASCADE",
    )

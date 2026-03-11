"""Add GIN trigram index on models.model_name for fast ILIKE search.

The ``ModelRepository.list_filtered()`` method uses ``ilike(f"%{search}%")``
which results in a sequential scan on PostgreSQL.  A GIN trigram index
accelerates this to an indexed lookup, significantly improving search
performance on large model catalogs.

The index uses ``pg_trgm`` (trigram matching), which must be enabled as a
PostgreSQL extension.  This migration is dialect-gated: it runs on
PostgreSQL only and is a no-op on SQLite (used for development/testing).

Revision ID: 030
Revises: 029
Create Date: 2026-03-10 00:00:00.000000+00:00

"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "030"
down_revision: str | None = "029"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Skip on SQLite (no extension support, no GIN indexes).
    bind = op.get_bind()
    if bind.dialect.name != "postgresql":
        return

    # Enable the pg_trgm extension (idempotent).
    op.execute("CREATE EXTENSION IF NOT EXISTS pg_trgm")

    # Create the GIN trigram index on model_name.
    op.create_index(
        "ix_models_name_trgm",
        "models",
        ["model_name"],
        postgresql_using="gin",
        postgresql_ops={"model_name": "gin_trgm_ops"},
    )


def downgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name != "postgresql":
        return

    op.drop_index("ix_models_name_trgm", table_name="models")
    # Do NOT drop the pg_trgm extension — other indexes may depend on it.

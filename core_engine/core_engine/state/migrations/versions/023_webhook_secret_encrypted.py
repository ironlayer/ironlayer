"""Add secret_encrypted column and lookup index to webhook_configs.

Adds the ``secret_encrypted`` column for storing Fernet-encrypted
webhook secrets (needed for HMAC-SHA256 signature verification), and
a composite index on ``(tenant_id, provider, repo_url)`` for efficient
webhook config lookups by provider and repository.

Revision ID: 023
Revises: 022
Create Date: 2026-02-24 00:00:00.000000+00:00

"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "023"
down_revision: str | None = "022"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Add the encrypted secret column for HMAC verification.
    op.add_column(
        "webhook_configs",
        sa.Column("secret_encrypted", sa.Text(), nullable=True),
    )

    # Composite index for provider + repo lookups scoped to tenant.
    op.create_index(
        "ix_webhook_configs_tenant_provider_repo",
        "webhook_configs",
        ["tenant_id", "provider", "repo_url"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_webhook_configs_tenant_provider_repo",
        table_name="webhook_configs",
    )
    op.drop_column("webhook_configs", "secret_encrypted")

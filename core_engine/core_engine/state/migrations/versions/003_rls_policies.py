"""Enable Row-Level Security on all tenant-scoped tables.

Adds RLS policies enforcing tenant isolation at the database level using
the ``app.tenant_id`` PostgreSQL session variable.  Every tenant-scoped
table receives a ``USING`` and ``WITH CHECK`` clause tied to
``current_setting('app.tenant_id', true)`` so that queries are restricted
to the authenticated tenant's rows even if the ORM layer is bypassed.

The ``true`` parameter to ``current_setting`` returns NULL when the
variable is unset, which means unset sessions see zero rows rather than
raising an error.  Superuser and migration contexts are unaffected because
RLS does not apply to table owners or superusers by default; however,
``FORCE ROW LEVEL SECURITY`` is enabled so that even the table owner is
subject to policies when the session variable is set.

Revision ID: 003
Revises: 001
Create Date: 2025-06-15 00:00:00.000000+00:00

"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "003"
down_revision: str | None = "001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# All tenant-scoped tables that require RLS enforcement.
_TENANT_TABLES: list[str] = [
    "models",
    "model_versions",
    "snapshots",
    "watermarks",
    "runs",
    "plans",
    "locks",
    "telemetry",
    "credentials",
]


def upgrade() -> None:
    for table in _TENANT_TABLES:
        # Enable RLS on the table.
        op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")
        # Force RLS even for the table owner so policies always apply
        # when app.tenant_id is set.
        op.execute(f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY")
        # Create the tenant isolation policy.  Uses current_setting with
        # the missing_ok parameter (true) so that sessions without the
        # variable set receive NULL and see zero rows instead of erroring.
        policy_name = f"tenant_isolation_{table}"
        op.execute(
            f"CREATE POLICY {policy_name} ON {table} "
            f"USING (tenant_id = current_setting('app.tenant_id', true)) "
            f"WITH CHECK (tenant_id = current_setting('app.tenant_id', true))"
        )


def downgrade() -> None:
    for table in reversed(_TENANT_TABLES):
        policy_name = f"tenant_isolation_{table}"
        op.execute(f"DROP POLICY IF EXISTS {policy_name} ON {table}")
        op.execute(f"ALTER TABLE {table} DISABLE ROW LEVEL SECURITY")
        op.execute(f"ALTER TABLE {table} NO FORCE ROW LEVEL SECURITY")

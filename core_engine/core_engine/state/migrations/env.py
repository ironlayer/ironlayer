"""Alembic environment configuration for IronLayer state store migrations.

Supports both **online** (connected) and **offline** (SQL-generation) modes.
The database URL is resolved from the ``ALEMBIC_DATABASE_URL`` environment
variable, falling back to the default local development connection string.

The ``target_metadata`` is bound to the shared ``Base.metadata`` from
``core_engine.state.tables`` so that ``--autogenerate`` can detect schema
drift against the ORM model definitions.
"""

from __future__ import annotations

import logging
import os
from logging.config import fileConfig

from alembic import context
from core_engine.state.tables import Base
from sqlalchemy import engine_from_config, pool

# Alembic Config object (provides access to alembic.ini values).
config = context.config

# Set up Python logging from the ini file if present.
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

logger = logging.getLogger("alembic.env")

# Target metadata for autogenerate support.
target_metadata = Base.metadata

# ---------------------------------------------------------------------------
# Database URL resolution
# ---------------------------------------------------------------------------

_DEFAULT_DATABASE_URL = "postgresql+asyncpg://ironlayer:ironlayer_dev@localhost:5432/ironlayer"


def _get_database_url() -> str:
    """Resolve the database URL from the environment or alembic.ini.

    Priority:
    1. ``ALEMBIC_DATABASE_URL`` environment variable.
    2. ``sqlalchemy.url`` key in ``alembic.ini``.
    3. Hard-coded local development default.

    For online migrations the async URL is converted to use the psycopg3
    synchronous driver (``postgresql+psycopg://``) because Alembic's default
    ``MigrationContext`` requires a synchronous engine.  psycopg3 is already
    a core dependency — no extra install needed.
    """
    url = os.environ.get("ALEMBIC_DATABASE_URL") or config.get_main_option("sqlalchemy.url")
    if not url:
        url = _DEFAULT_DATABASE_URL
        logger.info("Using default database URL: %s", url[:40] + "...")

    # Normalise to psycopg3 synchronous driver (already installed).
    if url.startswith("postgresql+asyncpg://"):
        url = "postgresql+psycopg://" + url[len("postgresql+asyncpg://") :]
    elif url.startswith("postgresql://"):
        url = "postgresql+psycopg://" + url[len("postgresql://") :]
    # Convert asyncpg SSL parameter to libpq format.
    url = url.replace("?ssl=require", "?sslmode=require")
    url = url.replace("&ssl=require", "&sslmode=require")
    return url


# ---------------------------------------------------------------------------
# Offline migrations (generate SQL without a live database)
# ---------------------------------------------------------------------------


def run_migrations_offline() -> None:
    """Run migrations in 'offline' mode.

    Configures the context with just a URL and not an Engine.  Calls to
    ``context.execute()`` emit the given string to the script output.
    """
    url = _get_database_url()
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        compare_type=True,
        compare_server_default=True,
    )

    with context.begin_transaction():
        context.run_migrations()


# ---------------------------------------------------------------------------
# Online migrations (connected to a live database)
# ---------------------------------------------------------------------------


def run_migrations_online() -> None:
    """Run migrations in 'online' mode.

    Creates a synchronous engine from the resolved URL and runs each
    migration revision within a transaction.
    """
    configuration = config.get_section(config.config_ini_section, {})
    configuration["sqlalchemy.url"] = _get_database_url()

    connectable = engine_from_config(
        configuration,
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            compare_type=True,
            compare_server_default=True,
        )

        with context.begin_transaction():
            context.run_migrations()

    connectable.dispose()


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()

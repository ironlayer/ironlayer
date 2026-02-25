"""SQLite adapter for local-only IronLayer operation.

Provides an async SQLAlchemy engine backed by ``aiosqlite`` that uses the
same ORM table definitions as the production PostgreSQL backend.  This
allows the CLI ``platform dev`` command to run the full API stack without
Docker or external dependencies.

Key differences from the PostgreSQL backend:

* No connection pooling (SQLite is single-writer).
* ``set_tenant_context()`` is a no-op (single-tenant local mode).
* Tables are created automatically on first connect.
* JSONB columns fall back to SQLite's TEXT (JSON stored as strings).

INVARIANT: The same ORM code paths are exercised in local and production
modes.  Only the engine URL and tenant context differ.
"""

from __future__ import annotations

import logging
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from pathlib import Path

from sqlalchemy import event
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

logger = logging.getLogger(__name__)


def get_local_engine(
    db_path: Path | str = ".ironlayer/state.db",
) -> AsyncEngine:
    """Create an async SQLAlchemy engine backed by SQLite via aiosqlite.

    Parameters
    ----------
    db_path:
        Path to the SQLite database file.  Parent directories are
        created automatically.  Use ``:memory:`` for ephemeral
        in-memory databases (useful for testing).

    Returns
    -------
    AsyncEngine
        A configured async engine ready for session creation.
    """
    db_path = Path(db_path) if db_path != ":memory:" else db_path

    if isinstance(db_path, Path):
        db_path.parent.mkdir(parents=True, exist_ok=True)
        url = f"sqlite+aiosqlite:///{db_path}"
    else:
        url = "sqlite+aiosqlite:///:memory:"

    engine = create_async_engine(
        url,
        echo=False,
        # SQLite requires connect_args for WAL mode and foreign key support.
        connect_args={"check_same_thread": False},
    )

    # Enable WAL mode and foreign keys for every connection.
    @event.listens_for(engine.sync_engine, "connect")
    def _set_sqlite_pragmas(dbapi_conn: object, _: object) -> None:
        cursor = dbapi_conn.cursor()  # type: ignore[attr-defined]
        cursor.execute("PRAGMA journal_mode=WAL")
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.execute("PRAGMA synchronous=NORMAL")
        cursor.close()

    logger.info("Created SQLite engine: %s", url)
    return engine


async def create_local_tables(engine: AsyncEngine) -> None:
    """Create all ORM tables in the SQLite database.

    This imports ``Base`` from the table definitions and runs
    ``create_all()`` -- idempotent and safe to call on every startup.
    """
    from core_engine.state.tables import Base

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    logger.info("SQLite tables created/verified")


async def set_local_tenant_context(
    session: AsyncSession,
    tenant_id: str,
) -> None:
    """No-op tenant context for SQLite local mode.

    In production PostgreSQL, ``SET LOCAL app.tenant_id`` enables RLS
    filtering.  SQLite has no RLS, and local mode is single-tenant, so
    this is a deliberate no-op.

    Parameters
    ----------
    session:
        The active async session (unused).
    tenant_id:
        The tenant identifier (unused).
    """
    # Intentionally empty -- single-tenant local mode.
    pass


@asynccontextmanager
async def get_local_session(
    engine: AsyncEngine,
) -> AsyncGenerator[AsyncSession, None]:
    """Yield an async session with commit/rollback semantics.

    Mirrors :func:`core_engine.state.database.get_session` but for
    local SQLite usage.
    """
    factory = async_sessionmaker(engine, expire_on_commit=False)
    session = factory()
    try:
        yield session
        await session.commit()
    except Exception:
        await session.rollback()
        raise
    finally:
        await session.close()

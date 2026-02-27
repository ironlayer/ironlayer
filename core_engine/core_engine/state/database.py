"""Async SQLAlchemy engine and session factory.

Supports both PostgreSQL (production) and SQLite (local dev mode).
Engine type is determined by the database URL scheme:
  - ``postgresql+asyncpg://`` → connection-pooled PostgreSQL engine
  - ``sqlite+aiosqlite://``   → single-connection SQLite engine
"""

from __future__ import annotations

import logging
import re
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from sqlalchemy import text
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

logger = logging.getLogger(__name__)

# Compiled regex for tenant ID validation – alphanumeric, hyphens, underscores, 1-128 chars.
_TENANT_ID_RE = re.compile(r"^[a-zA-Z0-9_-]{1,128}$")

# Cache of async_sessionmaker instances keyed by engine identity to avoid
# re-creating the factory on every get_session call.
_session_factories: dict[int, async_sessionmaker[AsyncSession]] = {}


def get_engine(
    database_url: str,
    pool_size: int = 10,
    max_overflow: int = 20,
) -> AsyncEngine:
    """Create an async SQLAlchemy engine.

    Automatically dispatches to the correct backend based on URL scheme:

    * ``postgresql+asyncpg://`` → pooled PostgreSQL engine
    * ``sqlite+aiosqlite://`` → single-connection SQLite engine

    Parameters
    ----------
    database_url:
        Connection string (PostgreSQL or SQLite scheme).
    pool_size:
        Number of persistent connections for PostgreSQL (ignored for SQLite).
    max_overflow:
        Maximum overflow connections for PostgreSQL (ignored for SQLite).

    Returns
    -------
    AsyncEngine
        A configured async engine ready for session creation.
    """
    if database_url.startswith("sqlite"):
        from core_engine.state.sqlite_adapter import get_local_engine

        # Extract path from URL: sqlite+aiosqlite:///path/to/db
        db_path = database_url.split("///", 1)[-1] if "///" in database_url else ":memory:"
        engine = get_local_engine(db_path if db_path else ":memory:")
        return engine

    engine = create_async_engine(
        database_url,
        pool_size=pool_size,
        max_overflow=max_overflow,
        pool_pre_ping=True,
        pool_recycle=3600,
        pool_timeout=10,
        echo=False,
        connect_args={
            "server_settings": {
                "statement_timeout": "30000",  # 30 s
                "lock_timeout": "10000",  # 10 s
            }
        },
    )
    logger.info(
        "Created async engine pool_size=%d max_overflow=%d",
        pool_size,
        max_overflow,
    )
    return engine


async def set_tenant_context(session: AsyncSession, tenant_id: str) -> None:
    """Set the session-level tenant context for RLS enforcement.

    For PostgreSQL, uses ``SET LOCAL`` to scope the variable to the
    current transaction.  For SQLite (local dev mode), this is a no-op
    since there is no RLS and the system operates in single-tenant mode.

    Parameters
    ----------
    session:
        An active async session with a transaction in progress.
    tenant_id:
        The tenant identifier to bind for RLS policy evaluation.
    """
    # Detect SQLite by inspecting the engine URL.
    bind = session.get_bind()
    dialect_name = getattr(bind, "dialect", None)
    if dialect_name is not None:
        dialect_name = getattr(dialect_name, "name", "")
    else:
        dialect_name = str(getattr(bind, "url", ""))

    if "sqlite" in str(dialect_name):
        # SQLite has no RLS; local mode is single-tenant.
        return

    # Strict validation – reject anything that doesn't match the allowlist.
    if not _TENANT_ID_RE.match(tenant_id):
        raise ValueError(f"Invalid tenant_id: must match {_TENANT_ID_RE.pattern!r}, got {tenant_id!r}")

    # Use set_config() with a bound parameter so the value is never interpolated
    # into the SQL string.  The third argument (true) scopes the setting to the
    # current transaction, equivalent to SET LOCAL.
    await session.execute(
        text("SELECT set_config('app.tenant_id', :tid, true)"),
        {"tid": tenant_id},
    )


@asynccontextmanager
async def get_session(engine: AsyncEngine) -> AsyncGenerator[AsyncSession, None]:
    """Yield an async session with automatic commit/rollback semantics.

    On successful exit the session is committed.  If an exception propagates
    the session is rolled back before the error is re-raised.
    """
    engine_key = id(engine)
    factory = _session_factories.get(engine_key)
    if factory is None:
        factory = async_sessionmaker(engine, expire_on_commit=False)
        _session_factories[engine_key] = factory
    session = factory()
    try:
        yield session
        await session.commit()
    except Exception:
        await session.rollback()
        raise
    finally:
        await session.close()

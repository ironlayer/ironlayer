"""Service layer for environment management.

Coordinates environment CRUD, ephemeral PR environment lifecycle,
snapshot-based promotions, and SQL rewriter construction.
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime, timedelta
from typing import Any

from core_engine.executor.sql_rewriter import SQLRewriter
from core_engine.state.repository import EnvironmentRepository
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)


class EnvironmentService:
    """Business logic for environment isolation.

    Parameters
    ----------
    session:
        Active database session.
    tenant_id:
        Tenant scope for all operations.
    """

    def __init__(
        self,
        session: AsyncSession,
        *,
        tenant_id: str = "default",
    ) -> None:
        self._session = session
        self._tenant_id = tenant_id
        self._env_repo = EnvironmentRepository(session, tenant_id=tenant_id)

    async def create_environment(
        self,
        name: str,
        catalog: str,
        schema_prefix: str,
        *,
        is_production: bool = False,
        created_by: str,
    ) -> dict[str, Any]:
        """Create a standard (non-ephemeral) environment.

        Returns a dictionary representation of the created environment.

        Raises
        ------
        ValueError
            If the environment name already exists.
        """
        env = await self._env_repo.create(
            name=name,
            catalog=catalog,
            schema_prefix=schema_prefix,
            is_production=is_production,
            is_ephemeral=False,
            created_by=created_by,
        )
        logger.info(
            "Created environment: tenant=%s name=%s catalog=%s schema=%s",
            self._tenant_id,
            name,
            catalog,
            schema_prefix,
        )
        return self._env_to_dict(env)

    async def create_ephemeral_environment(
        self,
        pr_number: int,
        branch_name: str,
        *,
        catalog: str,
        schema_prefix: str,
        created_by: str,
        ttl_hours: int = 72,
    ) -> dict[str, Any]:
        """Create an ephemeral PR environment with auto-expiry.

        The environment name is derived from the PR number to ensure
        uniqueness: ``pr-{pr_number}``.  The ``expires_at`` timestamp
        is set to ``ttl_hours`` from now.

        Returns a dictionary representation of the created environment.
        """
        name = f"pr-{pr_number}"
        expires_at = datetime.now(UTC) + timedelta(hours=ttl_hours)

        env = await self._env_repo.create(
            name=name,
            catalog=catalog,
            schema_prefix=schema_prefix,
            is_ephemeral=True,
            pr_number=pr_number,
            branch_name=branch_name,
            expires_at=expires_at,
            created_by=created_by,
        )
        logger.info(
            "Created ephemeral environment: tenant=%s name=%s pr=%d branch=%s ttl=%dh",
            self._tenant_id,
            name,
            pr_number,
            branch_name,
            ttl_hours,
        )
        return self._env_to_dict(env)

    async def get_environment(self, name: str) -> dict[str, Any] | None:
        """Get an environment by name. Returns None if not found."""
        env = await self._env_repo.get(name)
        if env is None:
            return None
        return self._env_to_dict(env)

    async def list_environments(
        self,
        include_deleted: bool = False,
    ) -> list[dict[str, Any]]:
        """List all environments, sorted by name."""
        envs = await self._env_repo.list_all(include_deleted=include_deleted)
        return [self._env_to_dict(e) for e in envs]

    async def delete_environment(self, name: str) -> bool:
        """Soft-delete an environment. Returns False if not found."""
        deleted = await self._env_repo.soft_delete(name)
        if deleted:
            logger.info(
                "Soft-deleted environment: tenant=%s name=%s",
                self._tenant_id,
                name,
            )
        return deleted

    async def promote(
        self,
        source_name: str,
        target_name: str,
        *,
        snapshot_id: str,
        promoted_by: str,
    ) -> dict[str, Any]:
        """Promote a snapshot reference from one environment to another.

        This copies snapshot references, NOT data.  Both the source and
        target environments must exist.

        Returns a dictionary representation of the promotion record.

        Raises
        ------
        ValueError
            If either environment does not exist.
        """
        source_env = await self._env_repo.get(source_name)
        if source_env is None:
            raise ValueError(f"Source environment '{source_name}' not found")

        target_env = await self._env_repo.get(target_name)
        if target_env is None:
            raise ValueError(f"Target environment '{target_name}' not found")

        # The target snapshot ID is the same reference -- we copy the pointer,
        # not the data.  The snapshot_id identifies the model versions state.
        target_snapshot_id = snapshot_id

        promotion = await self._env_repo.record_promotion(
            source_env=source_name,
            target_env=target_name,
            source_snapshot_id=snapshot_id,
            target_snapshot_id=target_snapshot_id,
            promoted_by=promoted_by,
            metadata={
                "source_catalog": source_env.catalog,
                "source_schema": source_env.schema_prefix,
                "target_catalog": target_env.catalog,
                "target_schema": target_env.schema_prefix,
            },
        )
        logger.info(
            "Promoted snapshot %s: %s -> %s (by %s)",
            snapshot_id,
            source_name,
            target_name,
            promoted_by,
        )
        return self._promotion_to_dict(promotion)

    async def cleanup_expired(self) -> dict[str, Any]:
        """Soft-delete all expired ephemeral environments.

        Returns a summary with the count of deleted environments.
        """
        count = await self._env_repo.cleanup_expired()
        if count > 0:
            logger.info(
                "Cleaned up %d expired ephemeral environments for tenant=%s",
                count,
                self._tenant_id,
            )
        return {"deleted_count": count}

    async def get_promotion_history(
        self,
        environment_name: str | None = None,
        limit: int = 20,
    ) -> list[dict[str, Any]]:
        """Get promotion history, optionally filtered by environment name."""
        promotions = await self._env_repo.get_promotion_history(
            environment_name=environment_name,
            limit=limit,
        )
        return [self._promotion_to_dict(p) for p in promotions]

    async def get_sql_rewriter(
        self,
        source_env_name: str,
        target_env_name: str,
    ) -> SQLRewriter | None:
        """Create a SQLRewriter for rewriting SQL from source to target environment.

        Returns None if either environment does not exist.
        """
        source_env = await self._env_repo.get(source_env_name)
        if source_env is None:
            return None

        target_env = await self._env_repo.get(target_env_name)
        if target_env is None:
            return None

        return SQLRewriter(
            source_catalog=source_env.catalog,
            source_schema=source_env.schema_prefix,
            target_catalog=target_env.catalog,
            target_schema=target_env.schema_prefix,
        )

    @staticmethod
    def _env_to_dict(env: Any) -> dict[str, Any]:
        """Convert an EnvironmentTable row to a serialisable dictionary."""
        return {
            "id": env.id,
            "name": env.name,
            "catalog": env.catalog,
            "schema_prefix": env.schema_prefix,
            "is_default": env.is_default,
            "is_production": env.is_production,
            "is_ephemeral": env.is_ephemeral,
            "pr_number": env.pr_number,
            "branch_name": env.branch_name,
            "expires_at": env.expires_at.isoformat() if env.expires_at else None,
            "created_by": env.created_by,
            "deleted_at": env.deleted_at.isoformat() if env.deleted_at else None,
            "created_at": env.created_at.isoformat() if env.created_at else None,
            "updated_at": env.updated_at.isoformat() if env.updated_at else None,
        }

    @staticmethod
    def _promotion_to_dict(promo: Any) -> dict[str, Any]:
        """Convert an EnvironmentPromotionTable row to a serialisable dictionary."""
        return {
            "id": promo.id,
            "source_environment": promo.source_environment,
            "target_environment": promo.target_environment,
            "source_snapshot_id": promo.source_snapshot_id,
            "target_snapshot_id": promo.target_snapshot_id,
            "promoted_by": promo.promoted_by,
            "promoted_at": promo.promoted_at.isoformat() if promo.promoted_at else None,
            "metadata": promo.metadata_json,
        }

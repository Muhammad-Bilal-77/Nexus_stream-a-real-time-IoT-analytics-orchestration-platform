"""
NexusStream Dashboard Service — PostgreSQL Client (asyncpg)
============================================================
Provides an async connection pool for querying the device registry
and user management tables defined in databases/postgres/init.sql.

Production note:
  asyncpg is the fastest async PostgreSQL driver for Python.
  The pool is created once at startup and shared across all requests.
  Max connections = POSTGRES_MAX_POOL (default 10) prevents DB exhaustion.
"""

import logging
from loguru import logger
from typing import Optional, Any
from config.settings import settings


try:
    import asyncpg
    HAS_ASYNCPG = True
except ImportError:
    HAS_ASYNCPG = False
    logger.warning("asyncpg not installed, Postgres integration disabled")



class PostgresClient:
    """Async PostgreSQL connection pool wrapper."""

    def __init__(self):
        self._pool: Optional[Any] = None

    async def connect(self) -> None:
        """Create connection pool. Call in FastAPI lifespan startup."""
        if not HAS_ASYNCPG:
            return
        try:
            self._pool = await asyncpg.create_pool(
                host=settings.postgres_host,
                port=settings.postgres_port,
                database=settings.postgres_db,
                user=settings.postgres_user,
                password=settings.postgres_password,
                min_size=settings.postgres_min_pool,
                max_size=settings.postgres_max_pool,
                command_timeout=10,
            )
            logger.info(
                f"PostgreSQL pool created: "
                f"{settings.postgres_host}:{settings.postgres_port}/{settings.postgres_db} "
                f"(pool: {settings.postgres_min_pool}-{settings.postgres_max_pool})"
            )
        except Exception as exc:
            logger.warning(f"PostgreSQL connection failed (service will work without it): {exc}")
            self._pool = None

    async def disconnect(self) -> None:
        """Close pool gracefully on shutdown."""
        if self._pool:
            await self._pool.close()
            logger.info("PostgreSQL pool closed")

    @property
    def is_connected(self) -> bool:
        return self._pool is not None

    # ------------------------------------------------------------------
    async def get_device_registry(self) -> list[dict]:
        """
        Return all registered devices from PostgreSQL.
        Used to enrich InfluxDB metrics with registered metadata.
        Falls back to empty list if DB is unreachable.
        """
        if not self._pool:
            return []
        try:
            async with self._pool.acquire() as conn:
                rows = await conn.fetch(
                    """
                    SELECT device_id, device_type, location,
                           firmware_version, registered_at,
                           last_seen_at, is_active
                    FROM devices
                    ORDER BY device_id
                    """
                )
                return [dict(r) for r in rows]
        except Exception as exc:
            logger.error(f"get_device_registry failed: {exc}")
            return []

    async def get_device_by_id(self, device_id: str) -> Optional[dict]:
        """Return a single device record by device_id string."""
        if not self._pool:
            return None
        try:
            async with self._pool.acquire() as conn:
                row = await conn.fetchrow(
                    "SELECT * FROM devices WHERE device_id = $1", device_id
                )
                return dict(row) if row else None
        except Exception as exc:
            logger.error(f"get_device_by_id failed: {exc}")
            return None

    async def upsert_device(self, device_id: str, device_type: str, location: str) -> None:
        """
        Register or update a device. Called by admin endpoints.
        Uses INSERT ... ON CONFLICT to be idempotent.
        """
        if not self._pool:
            return
        try:
            async with self._pool.acquire() as conn:
                await conn.execute(
                    """
                    INSERT INTO devices (device_id, device_type, location)
                    VALUES ($1, $2, $3)
                    ON CONFLICT (device_id) DO UPDATE
                      SET device_type = EXCLUDED.device_type,
                          location    = EXCLUDED.location
                    """,
                    device_id, device_type, location,
                )
        except Exception as exc:
            logger.error(f"upsert_device failed: {exc}")

    async def update_last_seen(self, device_id: str) -> None:
        """Update last_seen_at timestamp for a device."""
        if not self._pool:
            return
        try:
            async with self._pool.acquire() as conn:
                await conn.execute(
                    "UPDATE devices SET last_seen_at = NOW() WHERE device_id = $1",
                    device_id,
                )
        except Exception:
            pass   # Non-critical, don't crash on failures

    async def get_user_roles(self, username: str) -> list[str]:
        """
        Return the role names for a user. Used for RBAC enrichment.
        Falls back to ['viewer'] if user not found (safe default).
        """
        if not self._pool:
            return ["viewer"]
        try:
            async with self._pool.acquire() as conn:
                rows = await conn.fetch(
                    """
                    SELECT r.name FROM roles r
                    JOIN user_roles ur ON r.id = ur.role_id
                    JOIN users u ON u.id = ur.user_id
                    WHERE u.username = $1
                    """,
                    username,
                )
                return [row["name"] for row in rows] if rows else ["viewer"]
        except Exception as exc:
            logger.error(f"get_user_roles failed: {exc}")
            return ["viewer"]

    async def ping(self) -> bool:
        """Check if PostgreSQL is reachable. Used by /ready endpoint."""
        if not self._pool:
            return False
        try:
            async with self._pool.acquire() as conn:
                await conn.execute("SELECT 1")
            return True
        except Exception:
            return False


# Module-level singleton
postgres_client = PostgresClient()

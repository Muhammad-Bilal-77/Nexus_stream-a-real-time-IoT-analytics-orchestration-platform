"""
NexusStream Dashboard Service — Redis Cache Client
===================================================
Provides get/set/delete with JSON serialization + configurable TTL.

Cache key strategy:
  dashboard:devices         → GET /api/v1/devices (all roles)
  dashboard:stats           → GET /api/v1/stats/overview
  dashboard:anomalies:<hash>→ GET /api/v1/anomalies (per filter combo)
  dashboard:metrics:<id>:<w>→ GET /api/v1/metrics/{device_id}

Cache is write-through on first miss (lazy population).
Cache is invalidated via admin DELETE /api/v1/cache endpoint.

Backpressure:
  Redis is optional — all methods degrade gracefully if Redis is unavailable.
  Callers always check the return value for None and fall back to live queries.
"""

import json
from typing import Any, Optional
from loguru import logger
import redis.asyncio as aioredis
from config.settings import settings

# Cache key prefix
PREFIX = "dashboard:"


class RedisCache:
    """Async Redis wrapper for dashboard response caching."""

    def __init__(self):
        self._client: Optional[aioredis.Redis] = None
        self._ttl = settings.redis_cache_ttl_seconds

    async def connect(self) -> None:
        """Create Redis connection. Call in FastAPI lifespan startup."""
        try:
            self._client = aioredis.Redis(
                host=settings.redis_host,
                port=settings.redis_port,
                password=settings.redis_password or None,
                decode_responses=True,
                socket_connect_timeout=3,
                socket_keepalive=True,
            )
            await self._client.ping()
            logger.info(f"Redis cache connected: {settings.redis_host}:{settings.redis_port}")
        except Exception as exc:
            logger.warning(f"Redis cache unavailable (running without cache): {exc}")
            self._client = None

    async def disconnect(self) -> None:
        if self._client:
            await self._client.aclose()
            logger.info("Redis cache disconnected")

    @property
    def is_connected(self) -> bool:
        return self._client is not None

    # ------------------------------------------------------------------
    async def get(self, key: str) -> Optional[Any]:
        """Return parsed value for key, or None on miss/error."""
        if not self._client:
            return None
        try:
            raw = await self._client.get(PREFIX + key)
            return json.loads(raw) if raw else None
        except Exception as exc:
            logger.debug(f"Cache GET failed for {key}: {exc}")
            return None

    async def set(self, key: str, value: Any, ttl: Optional[int] = None) -> None:
        """Serialize + store value with TTL."""
        if not self._client:
            return
        try:
            await self._client.setex(
                PREFIX + key,
                ttl or self._ttl,
                json.dumps(value, default=str),
            )
        except Exception as exc:
            logger.debug(f"Cache SET failed for {key}: {exc}")

    async def delete(self, key: str) -> None:
        """Delete a specific key."""
        if not self._client:
            return
        try:
            await self._client.delete(PREFIX + key)
        except Exception:
            pass

    async def clear_all_dashboard_keys(self) -> int:
        """Delete all dashboard:* keys. Used by admin cache-reset endpoint."""
        if not self._client:
            return 0
        try:
            keys = await self._client.keys(PREFIX + "*")
            if keys:
                await self._client.delete(*keys)
                logger.info(f"Cleared {len(keys)} dashboard cache keys")
                return len(keys)
            return 0
        except Exception as exc:
            logger.error(f"Cache clear failed: {exc}")
            return 0

    async def ping(self) -> bool:
        """Health check — used by /ready endpoint."""
        if not self._client:
            return False
        try:
            return await self._client.ping()
        except Exception:
            return False


# Module-level singleton
redis_cache = RedisCache()

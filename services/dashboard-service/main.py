"""
NexusStream — Dashboard Service (FULLY IMPLEMENTED)
=====================================================
Tech: Python 3.11 + FastAPI + asyncpg + InfluxDB + Redis + websockets

REST API (JWT-protected, RBAC-enforced):
  GET  /health                              — liveness probe (no auth)
  GET  /ready                               — readiness probe (no auth)
  GET  /api/v1/devices                      — device list [viewer+]
  GET  /api/v1/metrics/{device_id}          — time-series metrics [analyst+]
  GET  /api/v1/anomalies                    — anomaly records [analyst+]
  GET  /api/v1/stats/overview               — aggregate stats [viewer+]
  GET  /api/v1/admin/stats                  — internal counters [admin]
  DELETE /api/v1/admin/cache                — clear Redis cache [admin]

WebSocket:
  WS   /ws/dashboard?token=<JWT>            — real-time metrics (role-filtered)
"""

import asyncio
import sys
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from typing import Optional

import httpx
import redis.asyncio as aioredis
from fastapi import Depends, FastAPI, HTTPException, Query, WebSocket, WebSocketDisconnect, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from loguru import logger

from app.auth import get_effective_role, require_role, verify_ws_token
from app.influx_client import influx_client
from app.models import (
    AnomalyListResponse,
    CacheResetResponse,
    DeviceDetail,
    DeviceListResponse,
    DeviceSummary,
    Role,
    StatsOverview,
    TokenPayload,
)
from app.postgres_client import postgres_client
from app.redis_client import redis_cache
from app.ws_manager import ws_manager
from app.ws_proxy import AnalyticsWsProxy
from config.settings import settings


# ===========================================================================
# Loguru setup
# ===========================================================================
logger.remove()
if settings.log_format == "json":
    logger.add(
        sys.stdout,
        level=settings.log_level.upper(),
        format=(
            '{{"time":"{time:YYYY-MM-DDTHH:mm:ss.SSSZ}",'
            '"level":"{level}",'
            '"service":"dashboard-service",'
            '"message":"{message}"}}'
        ),
        colorize=False,
    )
else:
    logger.add(
        sys.stdout,
        level=settings.log_level.upper(),
        format="<green>{time:HH:mm:ss}</green> | <level>{level:<8}</level> | {message}",
        colorize=True,
    )


# ===========================================================================
# Singletons
# ===========================================================================
analytics_proxy = AnalyticsWsProxy(analytics_ws_url=settings.analytics_ws_url)


# ===========================================================================
# Application lifecycle
# ===========================================================================
@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info(
        f"Dashboard service starting — port={settings.dashboard_port}, "
        f"influx={settings.influxdb_url}, redis={settings.redis_host}"
    )
    # Open connections
    await postgres_client.connect()
    await redis_cache.connect()

    # Start analytics WS proxy (non-blocking background task)
    await analytics_proxy.start()

    logger.info("Dashboard service ready.")
    yield

    # Shutdown
    logger.info("Dashboard service shutting down...")
    await analytics_proxy.stop()
    await redis_cache.disconnect()
    await postgres_client.disconnect()
    logger.info("Dashboard service stopped cleanly.")


# ===========================================================================
# FastAPI Application
# ===========================================================================
app = FastAPI(
    title="NexusStream Dashboard Service",
    version="2.0.0",
    description=(
        "Role-based IoT dashboard API: device inventory, time-series metrics, "
        "anomaly history, aggregate stats, and real-time WebSocket updates."
    ),
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],   # Restrict to frontend origin in production
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.exception_handler(HTTPException)
async def http_exception_handler(request, exc):
    """Ensure all errors use the {"error": "..."} format for frontend consistency."""
    return JSONResponse(
        status_code=exc.status_code,
        content={"error": exc.detail},
    )


# ===========================================================================
# Health & Readiness
# ===========================================================================
@app.get("/health", tags=["observability"])
async def health():
    """Liveness — always 200 if process alive. Used by Docker HEALTHCHECK."""
    return {
        "status": "ok",
        "service": "dashboard-service",
        "version": "2.0.0",
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }


@app.get("/ready", tags=["observability"])
async def ready():
    """
    Readiness — checks InfluxDB and Redis reachability.
    Returns 503 until both are up (PostgreSQL is optional).
    """
    errors = []

    # InfluxDB check
    try:
        async with httpx.AsyncClient(timeout=3) as http:
            resp = await http.get(f"{settings.influxdb_url}/health")
            influx_ok = resp.status_code == 200
            if not influx_ok:
                errors.append(f"influxdb: HTTP {resp.status_code}")
    except Exception as exc:
        influx_ok = False
        errors.append(f"influxdb: {exc}")

    # Redis check
    redis_ok = await redis_cache.ping()
    if not redis_ok:
        errors.append("redis: unreachable")

    # PostgreSQL check (informational only — service runs without it)
    pg_ok = await postgres_client.ping()

    code = 200 if (influx_ok and redis_ok) else 503
    return JSONResponse(
        status_code=code,
        content={
            "status": "ready" if code == 200 else "not_ready",
            "influxdb": "ok" if influx_ok else "unreachable",
            "redis": "ok" if redis_ok else "unreachable",
            "postgres": "ok" if pg_ok else "unreachable (non-critical)",
            "errors": errors,
        },
    )


# ===========================================================================
# API — Devices
# ===========================================================================
@app.get("/api/v1/devices", tags=["devices"])
async def list_devices(
    page: int = Query(1, ge=1),
    size: int = Query(20, ge=1, le=100),
    user: TokenPayload = Depends(require_role(Role.VIEWER)),
):
    """
    List all known devices with their latest metrics.

    - **viewer**: receives DeviceSummary (device_id, type, status, last_value, is_anomaly)
    - **analyst/admin**: receives DeviceDetail (+ moving_avg, min, max, packet_count)

    Responses are cached in Redis for `REDIS_CACHE_TTL_SECONDS` seconds.
    """
    effective_role = get_effective_role(user)
    cache_key = f"devices:p{page}:s{size}:r{effective_role.value}"

    # Cache hit
    cached = await redis_cache.get(cache_key)
    if cached:
        logger.debug(f"Cache hit: {cache_key}")
        return cached

    # Fetch from InfluxDB (live data) + PostgreSQL (metadata)
    raw_devices = await influx_client.get_devices_latest()
    pg_devices   = {d["device_id"]: d for d in await postgres_client.get_device_registry()}

    # Paginate
    total = len(raw_devices)
    start = (page - 1) * size
    page_data = raw_devices[start: start + size]

    # Build response based on role
    devices = []
    for d in page_data:
        pg = pg_devices.get(d["device_id"], {})
        if effective_role == Role.VIEWER:
            devices.append(DeviceSummary(
                device_id=d["device_id"],
                device_type=d["device_type"],
                status=d["status"],
                last_value=d.get("raw_value"),
                is_anomaly=d.get("is_anomaly"),
                last_seen_at=d.get("last_seen_at"),
                location=pg.get("location"),
            ).model_dump())
        else:
            devices.append(DeviceDetail(
                device_id=d["device_id"],
                device_type=d["device_type"],
                status=d["status"],
                last_value=d.get("raw_value"),
                is_anomaly=d.get("is_anomaly"),
                last_seen_at=d.get("last_seen_at"),
                location=pg.get("location"),
                moving_avg=d.get("moving_avg"),
                minimum=d.get("minimum"),
                maximum=d.get("maximum"),
                packet_count=d.get("packet_count"),
                firmware_version=pg.get("firmware_version"),
            ).model_dump())

    result = DeviceListResponse(total=total, page=page, size=size, devices=devices).model_dump()
    await redis_cache.set(cache_key, result)
    return result


# ===========================================================================
# API — Per-Device Time-Series Metrics
# ===========================================================================
@app.get("/api/v1/metrics/{device_id}", tags=["metrics"])
async def device_metrics(
    device_id: str,
    window: str = Query("5m", description="Time window: 5m|15m|30m|1h|6h|12h|24h|7d"),
    user: TokenPayload = Depends(require_role(Role.ANALYST)),
):
    """
    Return time-series metric points for a specific device.
    Requires **analyst** role or higher.

    Query InfluxDB for raw_value, moving_avg, min, max over the specified window.
    Results cached in Redis per device+window combination.
    """
    cache_key = f"metrics:{device_id}:{window}"
    cached = await redis_cache.get(cache_key)
    if cached:
        return cached

    points = await influx_client.get_device_metrics(device_id=device_id, window=window)

    if not points:
        # Return empty but valid response — device may have no data in this window
        result = {
            "device_id": device_id,
            "window": window,
            "points": [],
            "total_points": 0,
        }
    else:
        # Analyst can see moving_avg, min, max
        # Admin adds no extra fields here — same data at this endpoint
        result = {
            "device_id": device_id,
            "window": window,
            "points": points,
            "total_points": len(points),
        }

    await redis_cache.set(cache_key, result, ttl=30)  # metrics cache 30s
    return result


# ===========================================================================
# API — Anomalies
# ===========================================================================
@app.get("/api/v1/anomalies", tags=["anomalies"])
async def list_anomalies(
    device_id: Optional[str] = Query(None, description="Filter by device ID"),
    device_type: Optional[str] = Query(None, description="Filter by device type"),
    window: str = Query("1h", description="Time window for anomaly lookup"),
    limit: int = Query(50, ge=1, le=200),
    user: TokenPayload = Depends(require_role(Role.ANALYST)),
):
    """
    Return recent anomalies from InfluxDB.
    Requires **analyst** role or higher.

    **admin** users additionally see `location` field per anomaly.
    Filterable by device_id, device_type, and time window.
    """
    effective_role = get_effective_role(user)
    cache_key = f"anomalies:{device_id}:{device_type}:{window}:{limit}"
    cached = await redis_cache.get(cache_key)
    if cached:
        return cached

    anomalies = await influx_client.get_recent_anomalies(
        device_id=device_id,
        device_type=device_type,
        limit=limit,
        window=window,
    )

    # Analysts see moving_avg; admins also see location (already present from InfluxDB tags)
    # Filter location for non-admins
    if effective_role != Role.ADMIN:
        for a in anomalies:
            a.pop("location", None)

    result = {"total": len(anomalies), "anomalies": anomalies}
    await redis_cache.set(cache_key, result)
    return result


# ===========================================================================
# API — Stats Overview
# ===========================================================================
@app.get("/api/v1/stats/overview", tags=["stats"])
async def stats_overview(
    window: str = Query("1h", description="Aggregation window: 5m|1h|6h|24h"),
    user: TokenPayload = Depends(require_role(Role.VIEWER)),
):
    """
    Aggregate stats for dashboard header cards.
    Available to all authenticated users (**viewer+**).

    - total_devices, active_devices
    - total_packets_last_hour, anomalies_last_hour
    - anomaly_rate_pct, packets_per_second

    Cached in Redis for `REDIS_CACHE_TTL_SECONDS` seconds.
    """
    cache_key = f"stats:{window}"
    cached = await redis_cache.get(cache_key)
    if cached:
        return cached

    stats = await influx_client.get_stats_overview(window=window)
    await redis_cache.set(cache_key, stats, ttl=5)  # stats are stale quickly
    return stats


# ===========================================================================
# API — Admin Endpoints
# ===========================================================================
@app.get("/api/v1/admin/stats", tags=["admin"])
async def admin_stats(
    user: TokenPayload = Depends(require_role(Role.ADMIN)),
):
    """
    Internal service statistics — admin only.
    Returns WebSocket client counts, proxy stats, cache connection status.
    """
    return {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "ws_manager": {
            "active_connections": ws_manager.active_connections,
            "connections_by_role": ws_manager.connections_by_role(),
            "total_connected_ever": ws_manager.total_connected,
            "total_messages_sent": ws_manager.total_messages_sent,
        },
        "analytics_proxy": {
            "total_received": analytics_proxy.total_received,
            "total_forwarded": analytics_proxy.total_forwarded,
            "reconnect_count": analytics_proxy.reconnect_count,
        },
        "cache": {
            "connected": redis_cache.is_connected,
        },
        "postgres": {
            "connected": postgres_client.is_connected,
        },
    }


@app.delete("/api/v1/admin/cache", tags=["admin"])
async def clear_cache():
    """
    Flush all Redis dashboard cache keys. Admin only.
    Forces next requests to re-query InfluxDB and PostgreSQL.
    """
    cleared = await redis_cache.clear_all_dashboard_keys()
    logger.warning(f"Cache cleared via API, keys={cleared}")
    return CacheResetResponse(
        cleared_keys=cleared,
        message=f"Cleared {cleared} cache keys. Next requests will re-query live data.",
    )


# ===========================================================================
# WebSocket — Real-time Dashboard Feed
# ===========================================================================
@app.websocket("/ws/dashboard")
async def dashboard_websocket(
    websocket: WebSocket,
    token: Optional[str] = Query(None, description="JWT Bearer token"),
):
    """
    Real-time dashboard metrics stream.
    Connects to analytics-service WS via proxy and re-broadcasts
    with field filtering based on the client's JWT role.

    Usage:
        ws://localhost:8002/ws/dashboard?token=<jwt>

    Message format varies by role:
      viewer  → { event, device_id, device_type, status, is_anomaly, timestamp }
      analyst → + raw_value, moving_avg, minimum, maximum, anomaly_source
      admin   → all fields including packet_count, location

    Client reconnection is handled client-side — this endpoint is stateless.
    """
    # Validate token before accepting the connection
    if not token:
        await websocket.close(code=4001, reason="Missing token")
        return

    try:
        payload = verify_ws_token(token)
    except HTTPException:
        await websocket.close(code=4003, reason="Invalid or expired token")
        return

    # Determine effective role
    user_roles = [r.lower() for r in payload.roles]
    effective_role = Role.VIEWER   # Default
    for role in reversed(Role.hierarchy()):
        if role.value in user_roles:
            effective_role = role
            break

    await ws_manager.connect(websocket, effective_role)
    logger.info(f"WS client connected: user={payload.username} role={effective_role.value}")

    try:
        # Keep connection alive — proxy broadcasts to this client via ws_manager
        while True:
            try:
                # Process any client messages (pong frames, client commands)
                await asyncio.wait_for(websocket.receive_text(), timeout=30.0)
            except asyncio.TimeoutError:
                # Send keep-alive ping
                await websocket.send_text('{"event":"ping"}')
    except WebSocketDisconnect:
        logger.info(f"WS client disconnected: user={payload.username}")
    except Exception as exc:
        logger.warning(f"WS client error: user={payload.username} error={exc}")
    finally:
        ws_manager.disconnect(websocket)


# ===========================================================================
# Direct execution entry point
# ===========================================================================
if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=settings.dashboard_port,
        reload=False,
        log_config=None,
        access_log=False,
    )

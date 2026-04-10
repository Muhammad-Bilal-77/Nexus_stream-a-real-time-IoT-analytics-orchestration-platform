"""
NexusStream — Analytics Service (FULLY IMPLEMENTED)
=====================================================
Tech: Python 3.11 + FastAPI + Redis asyncio + InfluxDB + loguru

Pipeline per packet:
  Redis iot:metrics channel
    → subscriber.py (auto-reconnect, backpressure queue)
    → pipeline.py   (sliding window → anomaly → InfluxDB + WebSocket)

Endpoints:
  GET  /health              — liveness probe (always 200 if process alive)
  GET  /ready               — readiness probe (checks Redis + InfluxDB)
  GET  /metrics/summary     — per-device latest snapshots from in-memory state
  GET  /anomalies/recent    — recent anomalies from in-memory ring buffer
  GET  /stats               — pipeline counters (packets, anomalies, WS clients)
  WS   /ws/analytics        — real-time metric + anomaly stream
"""

import asyncio
import sys
from contextlib import asynccontextmanager
from datetime import datetime, timezone

import redis.asyncio as aioredis
import httpx
from fastapi import FastAPI, WebSocket, WebSocketDisconnect, Query
from fastapi.middleware.cors import CORSMiddleware
from loguru import logger

from config.settings import settings
from app.influx_writer import InfluxBatchWriter
from app.ws_manager import WebSocketManager
from app.subscriber import RedisSubscriber
from app.pipeline import AnalyticsPipeline

# ===========================================================================
# Loguru configuration — structured JSON output for production
# ===========================================================================
logger.remove()   # Remove default handler

if settings.log_format == "json":
    logger.add(
        sys.stdout,
        level=settings.log_level.upper(),
        format=(
            '{{"time":"{time:YYYY-MM-DDTHH:mm:ss.SSSZ}",'
            '"level":"{level}",'
            '"service":"analytics-service",'
            '"message":"{message}"}}'
        ),
        colorize=False,
    )
else:
    # Human-readable for local development
    logger.add(
        sys.stdout,
        level=settings.log_level.upper(),
        format="<green>{time:HH:mm:ss}</green> | <level>{level:<8}</level> | {message}",
        colorize=True,
    )

# ===========================================================================
# Application state (singletons shared across request handlers)
# ===========================================================================
influx_writer = InfluxBatchWriter(
    url=settings.influxdb_url,
    token=settings.influxdb_token,
    org=settings.influxdb_org,
    bucket=settings.influxdb_bucket,
    batch_size=settings.influx_batch_size,
    batch_interval_ms=settings.influx_batch_interval_ms,
)

ws_manager = WebSocketManager()

pipeline = AnalyticsPipeline(
    settings=settings,
    influx_writer=influx_writer,
    ws_manager=ws_manager,
)

subscriber = RedisSubscriber(
    host=settings.redis_host,
    port=settings.redis_port,
    password=settings.redis_password,
    channel=settings.redis_iot_channel,
    on_packet=pipeline.process,
)


# ===========================================================================
# Application lifecycle
# ===========================================================================
@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Startup:  start InfluxDB writer + Redis subscriber (both background tasks).
    Shutdown: gracefully stop both, flush remaining InfluxDB batch.
    """
    logger.info(
        f"Analytics service starting — port={settings.analytics_port}, "
        f"window={settings.window_size_seconds}s, "
        f"redis={settings.redis_host}:{settings.redis_port}, "
        f"influx={settings.influxdb_url}"
    )

    await influx_writer.start()
    await subscriber.start()

    logger.info("Analytics service ready — waiting for packets...")
    yield

    logger.info("Analytics service shutting down...")
    await subscriber.stop()
    await influx_writer.stop()
    logger.info("Analytics service stopped cleanly.")


# ===========================================================================
# FastAPI Application
# ===========================================================================
app = FastAPI(
    title="NexusStream Analytics Service",
    version="2.0.0",
    description=(
        "Real-time IoT analytics: sliding-window metrics, "
        "anomaly detection, InfluxDB storage, WebSocket streaming."
    ),
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],   # Restrict in production to known dashboard origins
    allow_methods=["*"],
    allow_headers=["*"],
)


# ===========================================================================
# Health & Readiness Endpoints
# ===========================================================================
@app.get("/health", tags=["observability"])
async def health():
    """
    Liveness probe — returns 200 as long as the Python process is alive.
    Used by Docker HEALTHCHECK and k8s liveness probe.
    Does NOT check external dependencies (Redis, InfluxDB).
    """
    return {
        "status": "ok",
        "service": "analytics-service",
        "version": "2.0.0",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "pipeline": pipeline.get_stats(),
    }


@app.get("/ready", tags=["observability"])
async def ready():
    """
    Readiness probe — returns 200 only when external dependencies are reachable.
    Used by k8s readiness probe / load balancer.
    Returns 503 if Redis or InfluxDB are unreachable.
    """
    errors = []

    # Check Redis
    try:
        client = aioredis.Redis(
            host=settings.redis_host,
            port=settings.redis_port,
            password=settings.redis_password or None,
            socket_connect_timeout=2,
        )
        await client.ping()
        await client.aclose()
        redis_ok = True
    except Exception as exc:
        redis_ok = False
        errors.append(f"redis: {exc}")

    # Check InfluxDB
    try:
        async with httpx.AsyncClient(timeout=3) as http:
            resp = await http.get(f"{settings.influxdb_url}/health")
            influx_ok = resp.status_code == 200
            if not influx_ok:
                errors.append(f"influxdb: HTTP {resp.status_code}")
    except Exception as exc:
        influx_ok = False
        errors.append(f"influxdb: {exc}")

    status_code = 200 if (redis_ok and influx_ok) else 503
    from fastapi.responses import JSONResponse
    return JSONResponse(
        status_code=status_code,
        content={
            "status": "ready" if status_code == 200 else "not_ready",
            "redis": "ok" if redis_ok else "unreachable",
            "influxdb": "ok" if influx_ok else "unreachable",
            "errors": errors,
        },
    )


# ===========================================================================
# Metrics & Analytics Endpoints
# ===========================================================================
@app.get("/metrics/summary", tags=["analytics"])
async def metrics_summary():
    """
    Returns per-device latest metric snapshots from the in-memory pipeline state.
    Includes moving_avg, min, max, packet_count, is_anomaly per device.
    For historical data, query InfluxDB directly or use the dashboard-service.
    """
    return pipeline.get_device_summary()


@app.get("/anomalies/recent", tags=["analytics"])
async def recent_anomalies(limit: int = Query(default=20, ge=1, le=200)):
    """
    Returns the most recent anomalies from the in-memory ring buffer
    (capacity configured by ANOMALY_CACHE_SIZE env var).

    For historical anomalies beyond the cache, query InfluxDB:
      from(bucket:"iot_metrics") |> range(start:-1h) |> filter(fn:(r) => r.is_anomaly == "true")
    """
    return {
        "count": min(limit, settings.anomaly_cache_size),
        "anomalies": pipeline.get_recent_anomalies(limit=limit),
    }


@app.get("/stats", tags=["observability"])
async def pipeline_stats():
    """Pipeline counters — packets processed, anomalies, WebSocket clients, InfluxDB writes."""
    return {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        **pipeline.get_stats(),
        "subscriber": {
            "total_received": subscriber.total_received,
            "total_processed": subscriber.total_processed,
            "total_dropped": subscriber.total_dropped,
            "total_invalid": subscriber.total_invalid,
        },
        "influx_writer": {
            "total_written": influx_writer.total_written,
            "total_dropped": influx_writer.total_dropped,
            "last_flush_at": influx_writer.last_flush_at.isoformat()
            if influx_writer.last_flush_at else None,
        },
    }


# ===========================================================================
# WebSocket Endpoint — Real-time analytics stream
# ===========================================================================
@app.websocket("/ws/analytics")
async def analytics_websocket(websocket: WebSocket):
    """
    Real-time metric stream. Every IoT packet processed by the pipeline is
    broadcast here within milliseconds of receipt.

    Message format (JSON):
    {
      "event": "metric",
      "device_id": "device-0001",
      "device_type": "temperature_sensor",
      "raw_value": 23.5,
      "moving_avg": 24.1,
      "minimum": 20.0,
      "maximum": 28.3,
      "packet_count": 45,
      "is_anomaly": false,
      "anomaly_source": "none",
      "timestamp": "2024-01-01T12:00:00.000Z",
      ...
    }

    Client reconnection: handled on the client side — this endpoint does not
    maintain per-client state so reconnecting is seamless.
    """
    await ws_manager.connect(websocket)
    try:
        # Keep connection alive — the pipeline broadcasts via ws_manager
        # We just ping back keep-alive frames every 30s
        while True:
            try:
                # Wait for any client message (ping frame) within 30s
                await asyncio.wait_for(websocket.receive_text(), timeout=30.0)
            except asyncio.TimeoutError:
                # Send keep-alive ping
                await websocket.send_text('{"event":"ping"}')
    except WebSocketDisconnect:
        logger.info(f"WS client disconnected (normal close)")
    except Exception as exc:
        logger.warning(f"WS client error: {exc}")
    finally:
        ws_manager.disconnect(websocket)


# ===========================================================================
# Direct execution entry point (without Docker)
# ===========================================================================
if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=settings.analytics_port,
        reload=False,       # Never use reload=True in production
        log_config=None,    # Loguru handles logging
        access_log=False,   # Reduce noise in production logs
    )

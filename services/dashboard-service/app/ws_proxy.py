"""
NexusStream Dashboard Service — Analytics WebSocket Proxy
==========================================================
Maintains a persistent connection to analytics-service /ws/analytics
and forwards enriched metric events to /ws/dashboard clients.

Design:
  - Runs as a background asyncio Task started in FastAPI lifespan.
  - Auto-reconnects to analytics-service with exponential back-off.
  - Forwards every metric event through DashboardWsManager.broadcast_filtered()
    so each /ws/dashboard client only receives fields appropriate for their role.
  - Anomaly events are highlighted with event="anomaly_alert" for frontend emphasis.

Circuit-breaker note:
  If analytics-service is down, the proxy silently retries. This dashboard
  continues serving REST API responses from cache/InfluxDB independently.
"""

import asyncio
import json
from loguru import logger
import websockets
from app.ws_manager import ws_manager


class AnalyticsWsProxy:
    """
    Connects to analytics-service WebSocket and forwards events to dashboard clients.
    """

    def __init__(self, analytics_ws_url: str):
        self._url = analytics_ws_url
        self._task: asyncio.Task | None = None
        self._running = False

        # Counters
        self.total_received: int = 0
        self.total_forwarded: int = 0
        self.reconnect_count: int = 0

    async def start(self) -> None:
        """Launch the proxy as a background asyncio task."""
        self._running = True
        self._task = asyncio.create_task(self._proxy_loop(), name="analytics_ws_proxy")
        logger.info(f"Analytics WS proxy started → {self._url}")

    async def stop(self) -> None:
        """Cancel the proxy task."""
        self._running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        logger.info(
            f"Analytics WS proxy stopped. "
            f"received={self.total_received}, forwarded={self.total_forwarded}, "
            f"reconnects={self.reconnect_count}"
        )

    async def _proxy_loop(self) -> None:
        """
        Outer reconnect loop. Reconnects with exponential back-off
        capped at 30 seconds.
        """
        backoff = 1
        while self._running:
            try:
                async with websockets.connect(
                    self._url,
                    ping_interval=20,
                    ping_timeout=10,
                    open_timeout=10,
                ) as ws:
                    self.reconnect_count += 1
                    backoff = 1   # Reset on success
                    logger.info(f"Connected to analytics-service WS (attempt #{self.reconnect_count})")

                    async for raw in ws:
                        if not self._running:
                            break
                        await self._handle_message(raw)

            except asyncio.CancelledError:
                break
            except Exception as exc:
                if not self._running:
                    break
                logger.warning(
                    f"Analytics WS proxy disconnected: {exc}. "
                    f"Reconnecting in {backoff}s..."
                )
                await asyncio.sleep(backoff)
                backoff = min(backoff * 2, 30)

    async def _handle_message(self, raw: str) -> None:
        """Parse, enrich, and forward a message from analytics-service."""
        self.total_received += 1

        try:
            payload = json.loads(raw)
        except json.JSONDecodeError:
            return  # Skip malformed messages

        # Skip keep-alive pings from analytics-service
        if payload.get("event") == "ping":
            return

        # Re-label anomaly events for frontend emphasis
        if payload.get("is_anomaly"):
            payload["event"] = "anomaly_alert"

        # Forward to all dashboard WebSocket clients (role-filtered internally)
        await ws_manager.broadcast_filtered(payload)
        self.total_forwarded += 1

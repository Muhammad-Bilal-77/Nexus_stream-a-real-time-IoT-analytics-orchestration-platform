"""
NexusStream Analytics Service — WebSocket Connection Manager
=============================================================
Manages a set of active WebSocket connections and broadcasts metric events.

Design:
  - A plain Python set holds active connections (no external state).
  - All connected clients receive every MetricEvent broadcast.
  - Failed sends (client disconnected mid-broadcast) are cleaned up silently.
  - Broadcast is async but does NOT await each send serially — uses
    asyncio.gather() for concurrent delivery to all clients.

Production note:
  For multi-instance analytics-service, replace this with a Redis Pub/Sub
  fan-out: each instance subscribes to a "processed_metrics" channel and
  broadcasts to its own set of clients. Clients connecting to any instance
  receive all events.
"""

import asyncio
import json
from datetime import datetime, timezone
from fastapi import WebSocket, WebSocketDisconnect
from loguru import logger


class WebSocketManager:
    """Thread-safe (asyncio-safe) WebSocket connection manager."""

    def __init__(self):
        self._connections: set[WebSocket] = set()
        self.total_connected: int = 0
        self.total_messages_sent: int = 0

    # ------------------------------------------------------------------
    async def connect(self, websocket: WebSocket) -> None:
        """Accept and register a new WebSocket connection."""
        await websocket.accept()
        self._connections.add(websocket)
        self.total_connected += 1
        logger.info(
            f"WS client connected. active={len(self._connections)}, "
            f"total_ever={self.total_connected}"
        )

    def disconnect(self, websocket: WebSocket) -> None:
        """Remove a WebSocket from the active set."""
        self._connections.discard(websocket)
        logger.info(f"WS client disconnected. active={len(self._connections)}")

    # ------------------------------------------------------------------
    async def broadcast(self, payload: dict) -> None:
        """
        Send payload to ALL connected clients concurrently.
        Dead connections are removed from the set.
        """
        if not self._connections:
            return

        message = json.dumps(payload)
        dead: list[WebSocket] = []

        # Gather concurrent sends — don't block on slow clients
        async def _send(ws: WebSocket) -> None:
            try:
                await ws.send_text(message)
            except Exception:
                dead.append(ws)

        await asyncio.gather(*[_send(ws) for ws in list(self._connections)])

        # Clean up dead connections
        for ws in dead:
            self._connections.discard(ws)
            logger.debug("Removed stale WebSocket connection after failed send")

        if self._connections:
            self.total_messages_sent += 1

    # ------------------------------------------------------------------
    async def send_error(self, websocket: WebSocket, error: str) -> None:
        """Send an error frame to a specific client."""
        try:
            await websocket.send_text(json.dumps({
                "event": "error",
                "error": error,
                "timestamp": datetime.now(timezone.utc).isoformat(),
            }))
        except Exception:
            pass

    @property
    def active_connections(self) -> int:
        return len(self._connections)

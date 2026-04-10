"""
NexusStream Dashboard Service — WebSocket Connection Manager
=============================================================
Manages dashboard client WebSocket connections.
Mirrors analytics-service's ws_manager.py with role-aware broadcast.

Role-based field filtering:
  viewer  → device_id, device_type, status, is_anomaly, timestamp
  analyst → + raw_value, moving_avg, minimum, maximum, anomaly_source
  admin   → all fields (packet_count, location included)

Design:
  - Dict[WebSocket, Role] tracks each client's effective role.
  - broadcast_filtered() sends role-appropriate payloads per client.
  - asyncio.gather() delivers concurrently — one slow client can't block others.
"""

import asyncio
import json
from fastapi import WebSocket
from loguru import logger
from app.models import Role


# Field sets per role — keys allowed in the broadcast payload
ROLE_FIELDS: dict[Role, set[str]] = {
    Role.VIEWER: {
        "event", "device_id", "device_type", "status",
        "is_anomaly", "timestamp",
    },
    Role.ANALYST: {
        "event", "device_id", "device_type", "status",
        "is_anomaly", "timestamp",
        "raw_value", "moving_avg", "minimum", "maximum", "anomaly_source",
    },
    Role.ADMIN: None,   # None = all fields
}


def _filter_payload(payload: dict, role: Role) -> dict:
    """Return a filtered copy of payload based on role's allowed fields."""
    allowed = ROLE_FIELDS.get(role)
    if allowed is None:
        return payload   # admin: all fields
    return {k: v for k, v in payload.items() if k in allowed}


class DashboardWsManager:
    """Role-aware WebSocket connection manager for /ws/dashboard."""

    def __init__(self):
        # Map from WebSocket → effective role
        self._connections: dict[WebSocket, Role] = {}
        self.total_connected: int = 0
        self.total_messages_sent: int = 0

    async def connect(self, websocket: WebSocket, role: Role) -> None:
        """Accept and register a client WebSocket with its role."""
        await websocket.accept()
        self._connections[websocket] = role
        self.total_connected += 1
        logger.info(
            f"WS dashboard client connected: role={role.value}, "
            f"active={len(self._connections)}"
        )

    def disconnect(self, websocket: WebSocket) -> None:
        self._connections.pop(websocket, None)
        logger.info(f"WS dashboard client disconnected. active={len(self._connections)}")

    # ------------------------------------------------------------------
    async def broadcast_filtered(self, payload: dict) -> None:
        """
        Broadcast payload to all clients, filtering fields per each client's role.

        Performance: asyncio.gather() delivers concurrently → one slow client
        can't block all others. Dead connections are removed after send.
        """
        if not self._connections:
            return

        dead: list[WebSocket] = []

        async def _send(ws: WebSocket, role: Role) -> None:
            filtered = _filter_payload(payload, role)
            try:
                await ws.send_text(json.dumps(filtered, default=str))
            except Exception:
                dead.append(ws)

        await asyncio.gather(
            *[_send(ws, role) for ws, role in list(self._connections.items())]
        )

        for ws in dead:
            self._connections.pop(ws, None)
        if self._connections:
            self.total_messages_sent += 1

    async def broadcast_all(self, payload: dict) -> None:
        """
        Broadcast to all clients without role filtering.
        Used for system events (e.g. service restart notifications).
        """
        if not self._connections:
            return
        message = json.dumps(payload, default=str)
        dead: list[WebSocket] = []

        async def _send(ws: WebSocket) -> None:
            try:
                await ws.send_text(message)
            except Exception:
                dead.append(ws)

        await asyncio.gather(*[_send(ws) for ws in list(self._connections)])
        for ws in dead:
            self._connections.pop(ws, None)

    @property
    def active_connections(self) -> int:
        return len(self._connections)

    def connections_by_role(self) -> dict[str, int]:
        """Stats breakdown by role — for /stats admin endpoint."""
        counts: dict[str, int] = {}
        for role in self._connections.values():
            counts[role.value] = counts.get(role.value, 0) + 1
        return counts


# Module-level singleton
ws_manager = DashboardWsManager()

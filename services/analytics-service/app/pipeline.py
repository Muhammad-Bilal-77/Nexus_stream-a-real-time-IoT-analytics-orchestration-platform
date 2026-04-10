"""
NexusStream Analytics Service — Pipeline Coordinator
=====================================================
The Pipeline is the central orchestrator that wires all components together.
It is called once per IoT packet after the subscriber receives and validates it.

Flow per packet:
  IoTPacket
    → SlidingWindowManager.add_reading()   → WindowResult
    → AnomalyDetector.detect()             → AnomalyResult
    → build MetricEvent
    → InfluxBatchWriter.enqueue()          (async, non-blocking)
    → WebSocketManager.broadcast()         (async, concurrent)
    → add to anomaly_cache if flagged      (thread-safe deque)

This module also exposes read methods for REST endpoints:
  pipeline.get_device_summary()    → used by GET /metrics/summary
  pipeline.get_recent_anomalies()  → used by GET /anomalies/recent
"""

from collections import deque
from datetime import datetime, timezone
from loguru import logger
from app.models import IoTPacket, MetricEvent
from app.window import SlidingWindowManager
from app.anomaly import AnomalyDetector
from app.influx_writer import InfluxBatchWriter
from app.ws_manager import WebSocketManager
from config.settings import Settings


class AnalyticsPipeline:
    """
    Wires SlidingWindow + AnomalyDetector + InfluxWriter + WebSocketManager.
    Instantiated once at application startup and passed through FastAPI's state.
    """

    def __init__(self, settings: Settings, influx_writer: InfluxBatchWriter,
                 ws_manager: WebSocketManager):
        self._settings = settings
        self._influx = influx_writer
        self._ws = ws_manager

        self._window_mgr = SlidingWindowManager(
            window_size_seconds=settings.window_size_seconds
        )
        self._anomaly_detector = AnomalyDetector(settings)

        # In-memory ring buffer of recent anomalies for GET /anomalies/recent
        self._anomaly_cache: deque[dict] = deque(maxlen=settings.anomaly_cache_size)

        # Simple per-device summary cache (overwritten on each packet)
        self._device_latest: dict[str, dict] = {}

        # Counters
        self.packets_processed: int = 0
        self.anomalies_detected: int = 0

    # ------------------------------------------------------------------
    async def process(self, packet: IoTPacket) -> None:
        """
        Main pipeline entry point — called for every valid incoming packet.
        Must be fast: heavy I/O (InfluxDB write) happens in background via queue.
        """
        now_iso = datetime.now(timezone.utc).isoformat()

        # Parse packet timestamp (fall back to now if malformed)
        try:
            packet_ts = datetime.fromisoformat(packet.timestamp.replace("Z", "+00:00"))
        except (ValueError, AttributeError):
            packet_ts = datetime.now(timezone.utc)

        # 1. Sliding-window computation
        window_result = self._window_mgr.add_reading(
            device_id=packet.device_id,
            device_type=packet.device_type,
            value=packet.metric_value,
            timestamp=packet_ts,
        )

        # 2. Anomaly detection
        anomaly_result = self._anomaly_detector.detect(
            device_type=packet.device_type,
            value=packet.metric_value,
            simulator_flagged=packet.is_anomaly,
        )

        if anomaly_result.is_anomaly:
            self.anomalies_detected += 1

        # 3. Build enriched MetricEvent
        event = MetricEvent(
            packet_id=packet.packet_id,
            device_id=packet.device_id,
            device_type=packet.device_type,
            unit=packet.unit,
            status=packet.status,
            raw_value=packet.metric_value,
            moving_avg=window_result.moving_avg,
            minimum=window_result.minimum,
            maximum=window_result.maximum,
            packet_count=window_result.packet_count,
            is_anomaly=anomaly_result.is_anomaly,
            anomaly_source=anomaly_result.source,
            location=packet.metadata.location if packet.metadata else None,
            timestamp=packet.timestamp,
            processed_at=now_iso,
        )

        # 4. Update per-device latest snapshot (for REST summary endpoint)
        self._device_latest[packet.device_id] = event.model_dump()

        # 5. Cache anomalies for REST endpoint
        if anomaly_result.is_anomaly:
            self._anomaly_cache.appendleft(event.model_dump())
            logger.warning(
                f"ANOMALY [{anomaly_result.source}] device={packet.device_id} "
                f"type={packet.device_type} value={packet.metric_value} "
                f"details={anomaly_result.details}"
            )

        # 6. Enqueue for InfluxDB batch write (non-blocking)
        await self._influx.enqueue(event)

        # 7. Broadcast to WebSocket clients (non-blocking, fire-and-forget)
        await self._ws.broadcast({
            "event": "metric",
            **event.model_dump(),
        })

        self.packets_processed += 1

        # Periodic progress log (every 1000 packets)
        if self.packets_processed % 1000 == 0:
            logger.info(
                f"Pipeline milestone: processed={self.packets_processed}, "
                f"anomalies={self.anomalies_detected}, "
                f"devices_tracked={len(self._device_latest)}, "
                f"influx_written={self._influx.total_written}, "
                f"ws_clients={self._ws.active_connections}"
            )

    # ------------------------------------------------------------------
    # REST endpoint data providers
    # ------------------------------------------------------------------
    def get_device_summary(self) -> dict:
        """Return the latest metric snapshot per device — for GET /metrics/summary."""
        return {
            "total_devices": len(self._device_latest),
            "window_size_seconds": self._settings.window_size_seconds,
            "packets_processed": self.packets_processed,
            "anomalies_detected": self.anomalies_detected,
            "devices": list(self._device_latest.values()),
        }

    def get_recent_anomalies(self, limit: int = 20) -> list[dict]:
        """Return the most recent N anomalies from the in-memory cache."""
        return list(self._anomaly_cache)[:limit]

    def get_stats(self) -> dict:
        """Stats for the /health endpoint."""
        return {
            "packets_processed": self.packets_processed,
            "anomalies_detected": self.anomalies_detected,
            "devices_tracked": len(self._device_latest),
            "influx_total_written": self._influx.total_written,
            "influx_total_dropped": self._influx.total_dropped,
            "ws_active_connections": self._ws.active_connections,
        }

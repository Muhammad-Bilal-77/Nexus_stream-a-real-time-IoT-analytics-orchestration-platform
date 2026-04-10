"""
NexusStream Analytics Service — Pydantic Models
================================================
Defines the data contracts flowing through the analytics pipeline.

IoTPacket   → parsed from Redis message (published by ingestion-service)
WindowResult → output of sliding-window computation per device
MetricEvent  → enriched event broadcast to WebSocket clients + written to InfluxDB
"""

from pydantic import BaseModel, Field
from typing import Optional
from datetime import datetime


class PacketMetadata(BaseModel):
    firmware_version: Optional[str] = None
    location: Optional[str] = None


class IoTPacket(BaseModel):
    """
    Mirrors the schema validated by ingestion-service/src/validator.js.
    Any packet that arrives here has already passed AJV validation on the
    ingestion side — we still validate on arrival for defense-in-depth.
    """
    packet_id: str
    device_id: str
    device_type: str
    metric_value: float
    unit: str
    status: str
    is_anomaly: bool = False          # Set by simulator; we may override below
    timestamp: str                    # ISO-8601 string from ingestion
    metadata: Optional[PacketMetadata] = None


class WindowResult(BaseModel):
    """Output of a sliding-window calculation for one device at one moment."""
    device_id: str
    device_type: str
    window_size_seconds: int
    packet_count: int
    moving_avg: float
    minimum: float
    maximum: float
    computed_at: datetime


class MetricEvent(BaseModel):
    """
    The enriched event sent to:
      1. InfluxDB (as a time-series point)
      2. WebSocket clients (as JSON)
      3. Recent-anomaly cache (when is_anomaly=True)
    """
    packet_id: str
    device_id: str
    device_type: str
    unit: str
    status: str
    raw_value: float
    moving_avg: float
    minimum: float
    maximum: float
    packet_count: int
    is_anomaly: bool
    anomaly_source: str              # "simulator" | "threshold" | "both"
    location: Optional[str] = None
    timestamp: str                   # Original packet timestamp → InfluxDB ts
    processed_at: str                # When analytics processed this packet

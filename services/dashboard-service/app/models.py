"""
NexusStream Dashboard Service — Pydantic Models
================================================
Data contracts for API requests and responses.

Design note:
  Role-conditional field exposure is handled at the endpoint level, not
  inside these models. Simpler models → easier to test and evolve.
"""

from pydantic import BaseModel, Field
from typing import Optional, List, Any
from enum import Enum


# ---------------------------------------------------------------------------
# RBAC
# ---------------------------------------------------------------------------
class Role(str, Enum):
    VIEWER   = "viewer"
    ANALYST  = "analyst"
    ADMIN    = "admin"

    @classmethod
    def hierarchy(cls) -> list["Role"]:
        """Ordered from lowest to highest privilege."""
        return [cls.VIEWER, cls.ANALYST, cls.ADMIN]

    def can_access(self, required: "Role") -> bool:
        """True if this role has AT LEAST the required privilege level."""
        order = self.hierarchy()
        return order.index(self) >= order.index(required)


class TokenPayload(BaseModel):
    sub: str
    username: str
    roles: List[str]
    iss: Optional[str] = None
    aud: Optional[str] = None


# ---------------------------------------------------------------------------
# Devices
# ---------------------------------------------------------------------------
class DeviceSummary(BaseModel):
    """Viewer-level device info — bare minimum."""
    device_id: str
    device_type: str
    status: str
    last_value: Optional[float] = None
    is_anomaly: Optional[bool] = None
    last_seen_at: Optional[str] = None
    location: Optional[str] = None


class DeviceDetail(DeviceSummary):
    """Analyst+Admin level — includes window metrics."""
    moving_avg: Optional[float] = None
    minimum: Optional[float] = None
    maximum: Optional[float] = None
    packet_count: Optional[int] = None
    firmware_version: Optional[str] = None


class DeviceListResponse(BaseModel):
    total: int
    page: int
    size: int
    devices: List[Any]   # DeviceSummary or DeviceDetail depending on role


# ---------------------------------------------------------------------------
# Time-series Metrics
# ---------------------------------------------------------------------------
class MetricPoint(BaseModel):
    timestamp: str
    raw_value: float
    moving_avg: Optional[float] = None
    minimum: Optional[float] = None
    maximum: Optional[float] = None
    is_anomaly: Optional[bool] = None
    anomaly_source: Optional[str] = None


class DeviceMetricsResponse(BaseModel):
    device_id: str
    device_type: Optional[str] = None
    window: str
    unit: Optional[str] = None
    points: List[MetricPoint]
    total_points: int


# ---------------------------------------------------------------------------
# Anomalies
# ---------------------------------------------------------------------------
class AnomalyRecord(BaseModel):
    packet_id: str
    device_id: str
    device_type: str
    raw_value: float
    anomaly_source: str
    status: str
    timestamp: str
    # Analyst+ fields
    moving_avg: Optional[float] = None
    # Admin+ fields
    location: Optional[str] = None


class AnomalyListResponse(BaseModel):
    total: int
    anomalies: List[Any]


# ---------------------------------------------------------------------------
# Stats Overview
# ---------------------------------------------------------------------------
class StatsOverview(BaseModel):
    total_devices: int
    active_devices: int
    total_packets_last_hour: int
    anomalies_last_hour: int
    anomaly_rate_pct: float
    packets_per_second: float
    timestamp: str
    # Admin-only: detailed breakdown
    influx_stats: Optional[dict] = None


# ---------------------------------------------------------------------------
# WebSocket messages
# ---------------------------------------------------------------------------
class WsMetricEvent(BaseModel):
    """Message sent to /ws/dashboard clients, filtered by role."""
    event: str = "metric"
    device_id: str
    device_type: str
    status: str
    is_anomaly: bool
    timestamp: str
    # Analyst+ fields (None for viewer)
    raw_value: Optional[float] = None
    moving_avg: Optional[float] = None
    minimum: Optional[float] = None
    maximum: Optional[float] = None
    anomaly_source: Optional[str] = None
    # Admin-only fields (None for non-admin)
    packet_count: Optional[int] = None
    location: Optional[str] = None


# ---------------------------------------------------------------------------
# Cache admin (admin only)
# ---------------------------------------------------------------------------
class CacheResetResponse(BaseModel):
    cleared_keys: int
    message: str

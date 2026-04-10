"""
NexusStream Dashboard Service — InfluxDB Query Client
======================================================
Provides typed query methods for the dashboard API.

All queries use the Flux query language (InfluxDB v2).
Queries are run synchronously but inside asyncio.run_in_executor()
so the event loop is never blocked.

Query patterns:
  - get_devices_latest()   → latest metrics per device (for /api/v1/devices)
  - get_device_metrics()   → time-series for one device
  - get_recent_anomalies() → anomaly records filtered by tag
  - get_stats_overview()   → aggregate counts for header cards
"""

import asyncio
from datetime import datetime, timezone
from typing import Optional
from loguru import logger
from influxdb_client import InfluxDBClient
from influxdb_client.client.flux_table import FluxTable
from config.settings import settings


class InfluxQueryClient:
    """
    Thin wrapper around InfluxDB's synchronous query_api,
    executed in a thread pool to stay async-friendly.
    """

    def __init__(self):
        self._url    = settings.influxdb_url
        self._token  = settings.influxdb_token
        self._org    = settings.influxdb_org
        self._bucket = settings.influxdb_bucket

    # ------------------------------------------------------------------
    def _run(self, flux: str) -> list[dict]:
        """Run a Flux query synchronously and return rows as list of dicts."""
        with InfluxDBClient(url=self._url, token=self._token, org=self._org) as client:
            tables: list[FluxTable] = client.query_api().query(flux, org=self._org)
            rows = []
            for table in tables:
                for record in table.records:
                    rows.append(record.values)
            return rows

    async def _query(self, flux: str) -> list[dict]:
        """Run _run() in a thread executor so it doesn't block the event loop."""
        loop = asyncio.get_event_loop()
        try:
            return await loop.run_in_executor(None, self._run, flux)
        except Exception as exc:
            logger.error(f"InfluxDB query failed: {exc}")
            return []

    # ------------------------------------------------------------------
    async def get_devices_latest(self) -> list[dict]:
        """
        Return the most recent raw_value + moving_avg per device.
        Used by GET /api/v1/devices.
        """
        flux = f"""
from(bucket: "{self._bucket}")
  |> range(start: -1h)
  |> filter(fn: (r) => r._measurement == "device_metrics")
  |> filter(fn: (r) => r._field == "raw_value" or r._field == "moving_avg"
            or r._field == "minimum" or r._field == "maximum"
            or r._field == "packet_count")
  |> last()
  |> pivot(rowKey:["_time"], columnKey:["_field"], valueColumn:"_value")
  |> group()
"""
        rows = await self._query(flux)
        # Normalize rows — each row is one device's latest snapshot
        devices: dict[str, dict] = {}
        for r in rows:
            did = r.get("device_id", "unknown")
            if did not in devices:
                devices[did] = {
                    "device_id":   did,
                    "device_type": r.get("device_type", "unknown"),
                    "status":      r.get("status", "unknown"),
                    "is_anomaly":  r.get("is_anomaly", "false") == "true",
                    "raw_value":   float(r.get("raw_value", 0) or 0),
                    "moving_avg":  float(r.get("moving_avg", 0) or 0),
                    "minimum":     float(r.get("minimum", 0) or 0),
                    "maximum":     float(r.get("maximum", 0) or 0),
                    "packet_count": int(r.get("packet_count", 0) or 0),
                    "location":    r.get("location"),
                    "last_seen_at": str(r.get("_time", "")),
                }
        return list(devices.values())

    # ------------------------------------------------------------------
    async def get_device_metrics(
        self,
        device_id: str,
        window: str = "5m",
    ) -> list[dict]:
        """
        Return time-series points for a specific device.
        window: InfluxDB duration string e.g. "5m", "1h", "24h".
        Used by GET /api/v1/metrics/{device_id}.
        """
        # Validate window to prevent injection
        allowed = {"5m", "15m", "30m", "1h", "6h", "12h", "24h", "7d"}
        if window not in allowed:
            window = "5m"

        flux = f"""
from(bucket: "{self._bucket}")
  |> range(start: -{window})
  |> filter(fn: (r) => r._measurement == "device_metrics")
  |> filter(fn: (r) => r.device_id == "{device_id}")
  |> filter(fn: (r) => r._field == "raw_value" or r._field == "moving_avg"
            or r._field == "minimum" or r._field == "maximum")
  |> pivot(rowKey:["_time"], columnKey:["_field"], valueColumn:"_value")
  |> sort(columns:["_time"], desc: false)
"""
        rows = await self._query(flux)
        points = []
        for r in rows:
            points.append({
                "timestamp":    str(r.get("_time", "")),
                "raw_value":    float(r.get("raw_value", 0) or 0),
                "moving_avg":   float(r.get("moving_avg", 0) or 0),
                "minimum":      float(r.get("minimum", 0) or 0),
                "maximum":      float(r.get("maximum", 0) or 0),
                "is_anomaly":   r.get("is_anomaly", "false") == "true",
                "anomaly_source": r.get("anomaly_source", "none"),
            })
        return points

    # ------------------------------------------------------------------
    async def get_recent_anomalies(
        self,
        device_id: Optional[str] = None,
        device_type: Optional[str] = None,
        limit: int = 50,
        window: str = "1h",
    ) -> list[dict]:
        """
        Return recent anomalies from InfluxDB, optionally filtered.
        Used by GET /api/v1/anomalies.
        """
        device_filter = f'|> filter(fn: (r) => r.device_id == "{device_id}")' if device_id else ""
        type_filter   = f'|> filter(fn: (r) => r.device_type == "{device_type}")' if device_type else ""

        flux = f"""
from(bucket: "{self._bucket}")
  |> range(start: -{window})
  |> filter(fn: (r) => r._measurement == "device_metrics")
  |> filter(fn: (r) => r.is_anomaly == "true")
  |> filter(fn: (r) => r._field == "raw_value" or r._field == "moving_avg")
  {device_filter}
  {type_filter}
  |> pivot(rowKey:["_time"], columnKey:["_field"], valueColumn:"_value")
  |> sort(columns:["_time"], desc: true)
  |> limit(n: {limit})
"""
        rows = await self._query(flux)
        anomalies = []
        for r in rows:
            anomalies.append({
                "packet_id":      r.get("result", "unknown"),
                "device_id":      r.get("device_id", "unknown"),
                "device_type":    r.get("device_type", "unknown"),
                "raw_value":      float(r.get("raw_value", 0) or 0),
                "moving_avg":     float(r.get("moving_avg", 0) or 0),
                "anomaly_source": r.get("anomaly_source", "unknown"),
                "status":         r.get("status", "unknown"),
                "location":       r.get("location"),
                "timestamp":      str(r.get("_time", "")),
            })
        return anomalies

    # ------------------------------------------------------------------
    async def get_stats_overview(self, window: str = "1h") -> dict:
        """
        Compute aggregate stats for the dashboard header cards.
        Used by GET /api/v1/stats/overview.
        """
        # Total packets in window
        total_flux = f"""
from(bucket: "{self._bucket}")
  |> range(start: -{window})
  |> filter(fn: (r) => r._measurement == "device_metrics" and r._field == "raw_value")
  |> count()
  |> sum()
"""
        # Anomaly packets in window
        anomaly_flux = f"""
from(bucket: "{self._bucket}")
  |> range(start: -{window})
  |> filter(fn: (r) => r._measurement == "device_metrics")
  |> filter(fn: (r) => r.is_anomaly == "true" and r._field == "raw_value")
  |> count()
  |> sum()
"""
        # Unique active devices
        devices_flux = f"""
from(bucket: "{self._bucket}")
  |> range(start: -{window})
  |> filter(fn: (r) => r._measurement == "device_metrics" and r._field == "raw_value")
  |> group(columns: ["device_id"])
  |> distinct(column: "device_id")
  |> count()
  |> sum()
"""
        total_rows   = await self._query(total_flux)
        anomaly_rows = await self._query(anomaly_flux)
        device_rows  = await self._query(devices_flux)

        total_packets  = int(total_rows[0].get("_value", 0))  if total_rows  else 0
        total_anomalies = int(anomaly_rows[0].get("_value", 0)) if anomaly_rows else 0
        active_devices  = int(device_rows[0].get("_value", 0))  if device_rows  else 0

        # window_seconds for pps calculation
        window_seconds = {"5m": 300, "1h": 3600, "6h": 21600, "24h": 86400}.get(window, 3600)
        pps = round(total_packets / window_seconds, 2) if window_seconds > 0 else 0.0
        anomaly_rate = round((total_anomalies / total_packets * 100), 2) if total_packets else 0.0

        return {
            "total_devices": active_devices,
            "active_devices": active_devices,
            "total_packets_last_hour": total_packets,
            "anomalies_last_hour": total_anomalies,
            "anomaly_rate_pct": anomaly_rate,
            "packets_per_second": pps,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }


# Module-level singleton
influx_client = InfluxQueryClient()

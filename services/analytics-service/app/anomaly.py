"""
NexusStream Analytics Service — Anomaly Detector
=================================================
Compares sensor readings against configurable per-device-type thresholds.

Two anomaly sources are tracked distinctly:
  "simulator" → packet.is_anomaly was set True by the ingestion simulator
  "threshold" → our own range check flags it as anomalous
  "both"      → both sources agree

Why threshold-based AND simulator-based?
  The simulator injects anomalies for pipeline testing. In production the
  simulator flag won't exist — threshold detection is what catches real issues.
  Keeping both allows us to validate that our thresholds are well-calibrated
  (they should catch most simulator anomalies).

Extensibility:
  Add z-score or IQR methods here using the WindowResult's moving_avg / std-dev.
  The interface (detect()) stays the same — callers don't need to change.
"""

from dataclasses import dataclass
from config.settings import Settings


@dataclass
class AnomalyResult:
    is_anomaly: bool
    source: str          # "none" | "simulator" | "threshold" | "both"
    details: str         # human-readable reason


class AnomalyDetector:
    """
    Threshold-based anomaly detector.
    Thresholds are loaded from Settings (environment variables) at startup.
    Changing thresholds requires a service restart — acceptable for now.
    (Production: hot-reload from a config store like Consul or Redis.)
    """

    def __init__(self, settings: Settings):
        # Build lookup: device_type → (min, max)
        # Each value OUTSIDE [min, max] is considered anomalous.
        self._thresholds: dict[str, tuple[float, float]] = {
            "temperature_sensor": (
                settings.anomaly_threshold_temperature_min,
                settings.anomaly_threshold_temperature_max,
            ),
            "pressure_sensor": (
                settings.anomaly_threshold_pressure_min,
                settings.anomaly_threshold_pressure_max,
            ),
            "humidity_sensor": (
                settings.anomaly_threshold_humidity_min,
                settings.anomaly_threshold_humidity_max,
            ),
            "vibration_sensor": (
                settings.anomaly_threshold_vibration_min,
                settings.anomaly_threshold_vibration_max,
            ),
            "power_meter": (
                settings.anomaly_threshold_power_min,
                settings.anomaly_threshold_power_max,
            ),
        }

    def detect(
        self,
        device_type: str,
        value: float,
        simulator_flagged: bool,
    ) -> AnomalyResult:
        """
        Determine whether a reading is anomalous.

        Args:
            device_type:       e.g. "temperature_sensor"
            value:             The raw metric value from the packet.
            simulator_flagged: True if the ingestion simulator already marked it.

        Returns:
            AnomalyResult with is_anomaly, source, and details.
        """
        threshold_anomaly = False
        details = "within_normal_range"

        if device_type in self._thresholds:
            lo, hi = self._thresholds[device_type]
            if value < lo or value > hi:
                threshold_anomaly = True
                details = f"value {value} outside threshold [{lo}, {hi}] for {device_type}"

        # Determine combined source string
        if simulator_flagged and threshold_anomaly:
            source = "both"
            is_anomaly = True
        elif threshold_anomaly:
            source = "threshold"
            is_anomaly = True
        elif simulator_flagged:
            source = "simulator"
            is_anomaly = True
        else:
            source = "none"
            is_anomaly = False

        return AnomalyResult(is_anomaly=is_anomaly, source=source, details=details)

    def get_threshold(self, device_type: str) -> tuple[float, float] | None:
        """Return the (min, max) threshold for a device type, or None if unknown."""
        return self._thresholds.get(device_type)

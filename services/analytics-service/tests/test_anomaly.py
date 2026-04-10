"""
Unit Tests — Anomaly Detector
==============================
Tests cover:
  - Values within threshold → not anomalous
  - Values below min threshold → anomalous (threshold source)
  - Values above max threshold → anomalous (threshold source)
  - Simulator-flagged + within threshold → anomalous (simulator source)
  - Simulator-flagged + out of range → anomalous (both source)
  - All supported device types
  - Unknown device type → not anomalous (safe default)

Run with: pytest tests/test_anomaly.py -v
"""

import pytest
from app.anomaly import AnomalyDetector
from config.settings import Settings


# ---------------------------------------------------------------------------
# Fixture: Default settings matching .env thresholds
# ---------------------------------------------------------------------------
@pytest.fixture
def default_settings() -> Settings:
    """Create Settings with default threshold values (matching .env defaults)."""
    return Settings(
        # Prevent reading from actual .env during tests
        redis_host="localhost",
        redis_password="",
        influxdb_token="test",
        anomaly_threshold_temperature_min=-20.0,
        anomaly_threshold_temperature_max=85.0,
        anomaly_threshold_pressure_min=80_000.0,
        anomaly_threshold_pressure_max=120_000.0,
        anomaly_threshold_humidity_min=0.0,
        anomaly_threshold_humidity_max=100.0,
        anomaly_threshold_vibration_min=0.0,
        anomaly_threshold_vibration_max=500.0,
        anomaly_threshold_power_min=0.0,
        anomaly_threshold_power_max=5_000.0,
    )


@pytest.fixture
def detector(default_settings) -> AnomalyDetector:
    return AnomalyDetector(default_settings)


# ---------------------------------------------------------------------------
# Temperature Sensor Tests
# ---------------------------------------------------------------------------
class TestTemperatureSensor:

    def test_normal_temperature_not_anomalous(self, detector):
        result = detector.detect("temperature_sensor", 25.0, simulator_flagged=False)
        assert result.is_anomaly is False
        assert result.source == "none"

    def test_at_exact_min_boundary_not_anomalous(self, detector):
        result = detector.detect("temperature_sensor", -20.0, simulator_flagged=False)
        assert result.is_anomaly is False

    def test_at_exact_max_boundary_not_anomalous(self, detector):
        result = detector.detect("temperature_sensor", 85.0, simulator_flagged=False)
        assert result.is_anomaly is False

    def test_below_min_threshold_is_anomalous(self, detector):
        result = detector.detect("temperature_sensor", -25.0, simulator_flagged=False)
        assert result.is_anomaly is True
        assert result.source == "threshold"
        assert "-25.0" in result.details

    def test_above_max_threshold_is_anomalous(self, detector):
        result = detector.detect("temperature_sensor", 150.0, simulator_flagged=False)
        assert result.is_anomaly is True
        assert result.source == "threshold"

    def test_simulator_flagged_within_range_is_anomalous(self, detector):
        """Simulator may flag values within threshold — we trust both sources."""
        result = detector.detect("temperature_sensor", 30.0, simulator_flagged=True)
        assert result.is_anomaly is True
        assert result.source == "simulator"

    def test_simulator_flagged_and_out_of_range_is_both(self, detector):
        """Both simulator and threshold agree → source = 'both'."""
        result = detector.detect("temperature_sensor", -50.0, simulator_flagged=True)
        assert result.is_anomaly is True
        assert result.source == "both"


# ---------------------------------------------------------------------------
# Other Device Types
# ---------------------------------------------------------------------------
class TestPressureSensor:

    def test_normal_pressure_not_anomalous(self, detector):
        result = detector.detect("pressure_sensor", 101325.0, simulator_flagged=False)
        assert result.is_anomaly is False

    def test_below_80000_is_anomalous(self, detector):
        result = detector.detect("pressure_sensor", 70000.0, simulator_flagged=False)
        assert result.is_anomaly is True
        assert result.source == "threshold"

    def test_above_120000_is_anomalous(self, detector):
        result = detector.detect("pressure_sensor", 200000.0, simulator_flagged=False)
        assert result.is_anomaly is True


class TestHumiditySensor:

    def test_normal_humidity_not_anomalous(self, detector):
        result = detector.detect("humidity_sensor", 55.0, simulator_flagged=False)
        assert result.is_anomaly is False

    def test_negative_humidity_is_anomalous(self, detector):
        result = detector.detect("humidity_sensor", -5.0, simulator_flagged=False)
        assert result.is_anomaly is True

    def test_over_100_humidity_is_anomalous(self, detector):
        result = detector.detect("humidity_sensor", 110.0, simulator_flagged=False)
        assert result.is_anomaly is True


class TestVibrationSensor:

    def test_normal_vibration_not_anomalous(self, detector):
        result = detector.detect("vibration_sensor", 200.0, simulator_flagged=False)
        assert result.is_anomaly is False

    def test_over_500_vibration_is_anomalous(self, detector):
        result = detector.detect("vibration_sensor", 1000.0, simulator_flagged=False)
        assert result.is_anomaly is True


class TestPowerMeter:

    def test_normal_power_not_anomalous(self, detector):
        result = detector.detect("power_meter", 2500.0, simulator_flagged=False)
        assert result.is_anomaly is False

    def test_over_5000_power_is_anomalous(self, detector):
        result = detector.detect("power_meter", 9999.0, simulator_flagged=False)
        assert result.is_anomaly is True

    def test_negative_power_is_anomalous(self, detector):
        result = detector.detect("power_meter", -100.0, simulator_flagged=False)
        assert result.is_anomaly is True


# ---------------------------------------------------------------------------
# Edge Cases
# ---------------------------------------------------------------------------
class TestEdgeCases:

    def test_unknown_device_type_not_anomalous(self, detector):
        """Unknown type has no threshold — should default to not anomalous."""
        result = detector.detect("unknown_device", 999999.0, simulator_flagged=False)
        assert result.is_anomaly is False
        assert result.source == "none"

    def test_unknown_device_type_with_simulator_flag(self, detector):
        """Unknown type with simulator flag → anomalous (simulator source)."""
        result = detector.detect("unknown_device", 0.0, simulator_flagged=True)
        assert result.is_anomaly is True
        assert result.source == "simulator"

    def test_get_threshold_returns_tuple(self, detector):
        lo, hi = detector.get_threshold("temperature_sensor")
        assert lo == -20.0
        assert hi == 85.0

    def test_get_threshold_returns_none_for_unknown(self, detector):
        assert detector.get_threshold("not_a_sensor") is None

    def test_custom_thresholds_via_settings(self):
        """Verify constructor correctly applies custom thresholds."""
        custom = Settings(
            redis_password="",
            influxdb_token="test",
            anomaly_threshold_temperature_min=0.0,
            anomaly_threshold_temperature_max=50.0,
        )
        d = AnomalyDetector(custom)

        # 60°C is normal by default but anomalous with custom threshold
        result = d.detect("temperature_sensor", 60.0, simulator_flagged=False)
        assert result.is_anomaly is True

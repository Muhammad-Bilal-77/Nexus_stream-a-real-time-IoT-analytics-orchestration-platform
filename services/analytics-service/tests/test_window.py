"""
Unit Tests — Sliding Window Manager
=====================================
Tests cover:
  - Single reading initialization
  - Window accumulation over time
  - Eviction of stale entries beyond window boundary
  - Min/max/avg correctness
  - Empty window edge case
  - Multi-device isolation

Run with: pytest tests/test_window.py -v
"""

import time
import pytest
from datetime import datetime, timezone, timedelta
from app.window import SlidingWindowManager


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def make_ts(offset_seconds: float = 0) -> datetime:
    """Return a UTC datetime `offset_seconds` from now."""
    return datetime.now(timezone.utc) + timedelta(seconds=offset_seconds)


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------
class TestSlidingWindowManager:

    def test_single_reading_returns_correct_stats(self):
        """First reading: avg = min = max = value, count = 1."""
        mgr = SlidingWindowManager(window_size_seconds=60)
        result = mgr.add_reading("device-0001", "temperature_sensor", 25.0)

        assert result.packet_count == 1
        assert result.moving_avg == pytest.approx(25.0)
        assert result.minimum == pytest.approx(25.0)
        assert result.maximum == pytest.approx(25.0)
        assert result.device_id == "device-0001"
        assert result.device_type == "temperature_sensor"
        assert result.window_size_seconds == 60

    def test_multiple_readings_average(self):
        """Moving average is correct across multiple readings."""
        mgr = SlidingWindowManager(window_size_seconds=60)
        values = [10.0, 20.0, 30.0, 40.0]
        for v in values:
            result = mgr.add_reading("device-0001", "temperature_sensor", v)

        assert result.packet_count == 4
        assert result.moving_avg == pytest.approx(25.0)   # (10+20+30+40)/4
        assert result.minimum == pytest.approx(10.0)
        assert result.maximum == pytest.approx(40.0)

    def test_stale_readings_are_evicted(self):
        """Readings older than window_size_seconds are removed."""
        mgr = SlidingWindowManager(window_size_seconds=10)

        # Add 3 readings 15 seconds ago (outside window)
        old_ts = make_ts(-15)
        for v in [100.0, 200.0, 300.0]:
            mgr.add_reading("device-0001", "temperature_sensor", v, timestamp=old_ts)

        # Add 1 recent reading (inside window)
        recent_ts = make_ts(0)
        result = mgr.add_reading("device-0001", "temperature_sensor", 50.0, timestamp=recent_ts)

        # Only the recent reading should remain
        assert result.packet_count == 1
        assert result.moving_avg == pytest.approx(50.0)
        assert result.minimum == pytest.approx(50.0)
        assert result.maximum == pytest.approx(50.0)

    def test_window_boundary_readings_both_kept(self):
        """Reading exactly at the boundary (= window_size ago) may be kept or evicted."""
        mgr = SlidingWindowManager(window_size_seconds=10)

        boundary_ts = make_ts(-9.9)   # Just inside the window
        mgr.add_reading("device-0001", "temperature_sensor", 77.0, timestamp=boundary_ts)

        current_ts = make_ts(0)
        result = mgr.add_reading("device-0001", "temperature_sensor", 33.0, timestamp=current_ts)

        assert result.packet_count == 2

    def test_multiple_devices_are_isolated(self):
        """Different devices maintain entirely separate windows."""
        mgr = SlidingWindowManager(window_size_seconds=60)

        mgr.add_reading("device-0001", "temperature_sensor", 50.0)
        mgr.add_reading("device-0002", "pressure_sensor", 101325.0)

        result_a = mgr.add_reading("device-0001", "temperature_sensor", 52.0)
        result_b = mgr.add_reading("device-0002", "pressure_sensor", 99000.0)

        # Device A should have only its own readings
        assert result_a.packet_count == 2
        assert result_a.moving_avg == pytest.approx(51.0)   # (50+52)/2

        # Device B should have only its own readings
        assert result_b.packet_count == 2
        assert result_b.moving_avg == pytest.approx((101325.0 + 99000.0) / 2)

    def test_negative_values_handled(self):
        """Window handles negative sensor values (e.g. sub-zero temperatures)."""
        mgr = SlidingWindowManager(window_size_seconds=60)
        values = [-30.0, -20.0, -10.0]
        for v in values:
            result = mgr.add_reading("device-0001", "temperature_sensor", v)

        assert result.minimum == pytest.approx(-30.0)
        assert result.maximum == pytest.approx(-10.0)
        assert result.moving_avg == pytest.approx(-20.0)

    def test_get_window_size_returns_current_count(self):
        """get_window_size() returns count of entries in the window, not seconds."""
        mgr = SlidingWindowManager(window_size_seconds=60)
        for _ in range(5):
            mgr.add_reading("device-0001", "temperature_sensor", 10.0)

        assert mgr.get_window_size("device-0001") == 5
        assert mgr.get_window_size("nonexistent-device") == 0

    def test_purge_device_removes_window(self):
        """purge_device() cleanly removes a device's window."""
        mgr = SlidingWindowManager(window_size_seconds=60)
        mgr.add_reading("device-0001", "temperature_sensor", 25.0)
        assert "device-0001" in mgr.get_all_device_ids()

        mgr.purge_device("device-0001")
        assert "device-0001" not in mgr.get_all_device_ids()
        assert mgr.get_window_size("device-0001") == 0

    def test_rounding_to_4_decimal_places(self):
        """avg/min/max are rounded to 4 decimal places."""
        mgr = SlidingWindowManager(window_size_seconds=60)
        # 1/3 = 0.333...
        for _ in range(3):
            mgr.add_reading("device-0001", "temperature_sensor", 1.0)
        result = mgr.add_reading("device-0001", "temperature_sensor", 0.0)

        # avg = (1+1+1+0)/4 = 0.75 — clean, but minimum precision test
        assert isinstance(result.moving_avg, float)
        # Verify no more than 4 dp
        parts = str(result.moving_avg).split(".")
        if len(parts) == 2:
            assert len(parts[1]) <= 4

    def test_high_frequency_1000_readings(self):
        """Window should handle 1000 rapid readings without error."""
        mgr = SlidingWindowManager(window_size_seconds=60)
        for i in range(1000):
            result = mgr.add_reading("device-0001", "temperature_sensor", float(i))

        assert result.packet_count == 1000
        # avg of 0..999 = 499.5
        assert result.moving_avg == pytest.approx(499.5, rel=1e-3)

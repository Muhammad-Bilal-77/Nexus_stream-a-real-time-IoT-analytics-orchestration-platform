"""
NexusStream Analytics Service — Sliding-Window Metrics
=======================================================
Maintains a time-bounded sliding window of sensor readings per device.

Design decisions:
  - Uses collections.deque for O(1) append/pop — no NumPy needed for 60s windows.
  - Window is trimmed on every call to add_reading() → no background GC task.
  - Per-device state is stored in a plain dict — safe for single-process async use.
    (For multi-instance analytics: move state to Redis Sorted Sets keyed by device.)
  - All arithmetic is pure Python — fast enough for 100-1000 pps on one core.

Scalability path:
  If device count exceeds ~10,000, consider replacing the per-device dict with
  a time-sorted Redis Sorted Set per device so state is shared across instances.
"""

from collections import defaultdict, deque
from datetime import datetime, timezone
from typing import Optional
from app.models import WindowResult
from loguru import logger


class SlidingWindowManager:
    """
    Manages a fixed-duration sliding window for each device independently.

    Internal structure per device:
        _windows[device_id] = deque([(timestamp_float, value), ...])

    The deque holds every reading within the last `window_size_seconds` seconds.
    On each new reading, stale entries are evicted from the left.
    """

    def __init__(self, window_size_seconds: int = 60):
        self.window_size_seconds = window_size_seconds
        # defaultdict so first access auto-creates an empty deque
        self._windows: dict[str, deque] = defaultdict(deque)
        # Track device_type per device_id for WindowResult construction
        self._device_types: dict[str, str] = {}

    # ------------------------------------------------------------------
    def add_reading(
        self,
        device_id: str,
        device_type: str,
        value: float,
        timestamp: Optional[datetime] = None,
    ) -> WindowResult:
        """
        Add a new reading and return the updated window statistics.

        Args:
            device_id:   Stable device identifier.
            device_type: e.g. "temperature_sensor".
            value:       The raw metric_value from the packet.
            timestamp:   Packet's own timestamp (defaults to now if None).

        Returns:
            WindowResult with moving_avg, min, max, packet_count over the window.
        """
        ts = (timestamp or datetime.now(timezone.utc)).timestamp()
        window = self._windows[device_id]
        self._device_types[device_id] = device_type

        # 1. Append new reading
        window.append((ts, value))

        # 2. Evict entries older than window_size_seconds from the left
        cutoff = ts - self.window_size_seconds
        while window and window[0][0] < cutoff:
            window.popleft()

        # 3. Compute aggregates over the remaining window
        values = [v for _, v in window]
        count = len(values)

        moving_avg = sum(values) / count if count else 0.0
        minimum    = min(values) if values else 0.0
        maximum    = max(values) if values else 0.0

        return WindowResult(
            device_id=device_id,
            device_type=device_type,
            window_size_seconds=self.window_size_seconds,
            packet_count=count,
            moving_avg=round(moving_avg, 4),
            minimum=round(minimum, 4),
            maximum=round(maximum, 4),
            computed_at=datetime.now(timezone.utc),
        )

    # ------------------------------------------------------------------
    def get_all_device_ids(self) -> list[str]:
        """Return list of all device IDs currently tracked."""
        return list(self._windows.keys())

    def get_window_size(self, device_id: str) -> int:
        """Number of readings currently in the window for a device."""
        return len(self._windows.get(device_id, []))

    def purge_device(self, device_id: str) -> None:
        """Remove a device's window (e.g. device decommissioned)."""
        self._windows.pop(device_id, None)
        self._device_types.pop(device_id, None)
        logger.info(f"Purged window for device {device_id}")

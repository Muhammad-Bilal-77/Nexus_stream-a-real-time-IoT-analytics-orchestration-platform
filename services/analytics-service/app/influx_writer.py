"""
NexusStream Analytics Service — InfluxDB Batch Writer
======================================================
Buffers MetricEvent points and flushes them in batches to InfluxDB v2.

Why batch writes?
  At 100 pps (10 devices × 10 pps), one write per packet = 100 HTTP requests/sec.
  Batching 50 points per request = 2 requests/sec → 98% network round-trip reduction.
  InfluxDB line protocol supports 10k points per request before performance degrades.

Design:
  - asyncio.Queue holds incoming Points — bounded to apply backpressure.
  - Background task (_flush_loop) drains the queue every INFLUX_BATCH_INTERVAL_MS
    OR when INFLUX_BATCH_SIZE is reached, whichever comes first.
  - Uses the standard influxdb_client.InfluxDBClient (synchronous) executed 
    inside asyncio.get_event_loop().run_in_executor so it never blocks the event loop.
  - On flush error: points are re-queued (up to MAX_REQUEUE_ATTEMPTS) then dropped.

Production note:
  For extreme throughput (>10k pps), switch to the influxdb_client[async] extra
  with InfluxDBClientAsync — requires aiohttp C extensions to build successfully.
"""

import asyncio
from datetime import datetime, timezone
from loguru import logger
from influxdb_client import InfluxDBClient, Point, WritePrecision
from influxdb_client.client.write_api import SYNCHRONOUS
from app.models import MetricEvent



MAX_QUEUE_SIZE = 10_000         # Backpressure cap — block producer when full
MAX_REQUEUE_ATTEMPTS = 3        # Retry failed batches this many times then drop


class InfluxBatchWriter:
    """
    Async batch writer for InfluxDB v2.
    Call start() on service startup and stop() on shutdown.
    """

    def __init__(self, url: str, token: str, org: str, bucket: str,
                 batch_size: int = 50, batch_interval_ms: int = 1000):
        self._url = url
        self._token = token
        self._org = org
        self._bucket = bucket
        self._batch_size = batch_size
        self._batch_interval_s = batch_interval_ms / 1000.0

        # Bounded queue for backpressure
        self._queue: asyncio.Queue[Point] = asyncio.Queue(maxsize=MAX_QUEUE_SIZE)
        self._flush_task: asyncio.Task | None = None
        self._running = False

        # Stats for /ready endpoint and logging
        self.total_written: int = 0
        self.total_dropped: int = 0
        self.last_flush_at: datetime | None = None

    # ------------------------------------------------------------------
    async def start(self) -> None:
        """Start the background flush loop."""
        self._running = True
        self._flush_task = asyncio.create_task(self._flush_loop(), name="influx_flush")
        logger.info(
            f"InfluxDB batch writer started: batch_size={self._batch_size}, "
            f"interval={self._batch_interval_s}s, bucket={self._bucket}"
        )

    async def stop(self) -> None:
        """Drain the queue and stop the flush loop gracefully."""
        self._running = False
        if self._flush_task:
            self._flush_task.cancel()
            try:
                await self._flush_task
            except asyncio.CancelledError:
                pass
        # Final flush of remaining items
        await self._flush_once()
        logger.info(f"InfluxDB writer stopped. Total written={self.total_written}, dropped={self.total_dropped}")

    # ------------------------------------------------------------------
    async def enqueue(self, event: MetricEvent) -> None:
        """
        Convert a MetricEvent to an InfluxDB Point and enqueue it.
        Drops the point (with a warn log) if the queue is full.
        """
        point = self._event_to_point(event)
        try:
            self._queue.put_nowait(point)
        except asyncio.QueueFull:
            self.total_dropped += 1
            logger.warning(
                f"InfluxDB queue full ({MAX_QUEUE_SIZE}), dropping point for "
                f"device={event.device_id}. Consider increasing throughput or reducing INFLUX_BATCH_INTERVAL."
            )

    # ------------------------------------------------------------------
    def _event_to_point(self, event: MetricEvent) -> Point:
        """
        Convert MetricEvent → InfluxDB Point using line protocol.

        Measurement: device_metrics
        Tags: device_id, device_type, status, is_anomaly, anomaly_source, location
        Fields: raw_value, moving_avg, minimum, maximum, packet_count
        Timestamp: original packet timestamp (nanosecond precision)
        """
        point = (
            Point("device_metrics")
            .tag("device_id", event.device_id)
            .tag("device_type", event.device_type)
            .tag("status", event.status)
            .tag("is_anomaly", str(event.is_anomaly).lower())
            .tag("anomaly_source", event.anomaly_source)
        )

        if event.location:
            point = point.tag("location", event.location)

        point = (
            point
            .field("raw_value", event.raw_value)
            .field("moving_avg", event.moving_avg)
            .field("minimum", event.minimum)
            .field("maximum", event.maximum)
            .field("packet_count", event.packet_count)
            .time(event.timestamp, WritePrecision.NS)
        )

        return point

    # ------------------------------------------------------------------
    async def _flush_loop(self) -> None:
        """Background task: flush on size threshold OR time threshold."""
        while self._running:
            try:
                # Wait up to batch_interval_s for the queue to accumulate
                await asyncio.sleep(self._batch_interval_s)
                await self._flush_once()
            except asyncio.CancelledError:
                break
            except Exception as exc:
                # Never let exceptions kill the flush loop
                logger.error(f"Unexpected error in flush loop: {exc}")

    async def _flush_once(self) -> None:
        """
        Drain up to batch_size points from the queue and write them.
        Uses the synchronous InfluxDBClient executed in a thread executor
        so the asyncio event loop is never blocked during HTTP I/O.
        """
        if self._queue.empty():
            return

        batch: list[Point] = []
        while not self._queue.empty() and len(batch) < self._batch_size:
            try:
                batch.append(self._queue.get_nowait())
            except asyncio.QueueEmpty:
                break

        if not batch:
            return

        loop = asyncio.get_event_loop()

        for attempt in range(1, MAX_REQUEUE_ATTEMPTS + 1):
            try:
                # Run synchronous I/O in thread executor — keeps event loop free
                await loop.run_in_executor(
                    None,
                    self._sync_write,
                    batch,
                )
                self.total_written += len(batch)
                self.last_flush_at = datetime.now(timezone.utc)
                logger.debug(f"Flushed {len(batch)} points to InfluxDB (total={self.total_written})")
                return

            except Exception as exc:
                logger.error(f"InfluxDB write failed (attempt {attempt}/{MAX_REQUEUE_ATTEMPTS}): {exc}")
                if attempt == MAX_REQUEUE_ATTEMPTS:
                    self.total_dropped += len(batch)
                    logger.warning(f"Dropped {len(batch)} points after {MAX_REQUEUE_ATTEMPTS} failures")
                else:
                    await asyncio.sleep(0.5 * attempt)  # short back-off before retry

    def _sync_write(self, batch: list) -> None:
        """Synchronous InfluxDB write — runs in a thread pool executor."""
        with InfluxDBClient(
            url=self._url,
            token=self._token,
            org=self._org,
        ) as client:
            write_api = client.write_api(write_options=SYNCHRONOUS)
            write_api.write(bucket=self._bucket, record=batch)


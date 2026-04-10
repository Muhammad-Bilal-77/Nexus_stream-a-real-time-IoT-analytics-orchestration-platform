"""
NexusStream Analytics Service — Redis Async Subscriber
=======================================================
Subscribes to the iot:metrics Redis Pub/Sub channel and processes each
incoming IoT packet through the analytics pipeline.

Resilience patterns:
  1. Auto-reconnect with exponential back-off (up to 30s) on connection loss.
  2. asyncio.Queue for backpressure — reader side bounded at QUEUE_MAX_SIZE.
     If the processing coroutine falls behind, the oldest unprocessed messages
     are dropped rather than crashing the subscriber.
  3. JSON parse errors are logged and skipped (malformed messages from other
     publishers on the same Redis instance).
  4. Pydantic validation filters packets that pass Redis but fail schema check.

Circuit-breaker note:
  The ingestion-service has its own RingBuffer — if analytics is completely down,
  ingestion buffers packets and flushes them when analytics reconnects.
  This subscriber auto-reconnects independently, so recovery is automatic.
"""

import asyncio
import json
from datetime import datetime, timezone
from typing import Callable, Awaitable
from loguru import logger
import redis.asyncio as aioredis
from pydantic import ValidationError
from app.models import IoTPacket


# Type alias for the packet handler callback
PacketHandler = Callable[[IoTPacket], Awaitable[None]]

# Internal queue size — packets wait here while the pipeline processes
QUEUE_MAX_SIZE = 5000


class RedisSubscriber:
    """
    Async Redis Pub/Sub subscriber with auto-reconnect and backpressure handling.

    Usage:
        subscriber = RedisSubscriber(settings, on_packet=pipeline.process)
        await subscriber.start()   # non-blocking — launches background task
        ...
        await subscriber.stop()    # graceful shutdown
    """

    def __init__(
        self,
        host: str,
        port: int,
        password: str,
        channel: str,
        on_packet: PacketHandler,
    ):
        self._host = host
        self._port = port
        self._password = password or None
        self._channel = channel
        self._on_packet = on_packet

        self._queue: asyncio.Queue[str] = asyncio.Queue(maxsize=QUEUE_MAX_SIZE)
        self._sub_task: asyncio.Task | None = None
        self._proc_task: asyncio.Task | None = None
        self._running = False

        # Observability counters
        self.total_received: int = 0
        self.total_processed: int = 0
        self.total_dropped: int = 0
        self.total_invalid: int = 0

    # ------------------------------------------------------------------
    async def start(self) -> None:
        """Launch subscriber + processor background tasks."""
        self._running = True
        self._sub_task = asyncio.create_task(self._subscribe_loop(), name="redis_subscriber")
        self._proc_task = asyncio.create_task(self._process_loop(), name="packet_processor")
        logger.info(
            f"Redis subscriber started: channel={self._channel}, "
            f"host={self._host}:{self._port}"
        )

    async def stop(self) -> None:
        """Cancel both tasks and wait for clean exit."""
        self._running = False
        for task in (self._sub_task, self._proc_task):
            if task:
                task.cancel()
                try:
                    await task
                except asyncio.CancelledError:
                    pass
        logger.info(
            f"Redis subscriber stopped. received={self.total_received}, "
            f"processed={self.total_processed}, dropped={self.total_dropped}, "
            f"invalid={self.total_invalid}"
        )

    # ------------------------------------------------------------------
    async def _subscribe_loop(self) -> None:
        """
        Maintains the Redis subscription, reconnecting with exponential back-off.
        Raw message strings are pushed into _queue for async processing.
        """
        backoff = 1  # seconds
        while self._running:
            try:
                client = aioredis.Redis(
                    host=self._host,
                    port=self._port,
                    password=self._password,
                    decode_responses=True,
                    socket_connect_timeout=5,
                    socket_keepalive=True,
                )
                pubsub = client.pubsub()
                await pubsub.subscribe(self._channel)
                logger.info(f"Subscribed to Redis channel: {self._channel}")
                backoff = 1  # Reset back-off on successful connect

                async for raw_message in pubsub.listen():
                    if not self._running:
                        break

                    # Pub/Sub sends control messages (type='subscribe') first
                    if raw_message.get("type") != "message":
                        continue

                    data = raw_message.get("data", "")
                    self.total_received += 1

                    try:
                        self._queue.put_nowait(data)
                    except asyncio.QueueFull:
                        # Back-pressure: drop the oldest message
                        try:
                            self._queue.get_nowait()
                        except asyncio.QueueEmpty:
                            pass
                        self._queue.put_nowait(data)
                        self.total_dropped += 1
                        logger.warning(
                            f"Subscriber queue full, dropped 1 message "
                            f"(total_dropped={self.total_dropped})"
                        )

            except asyncio.CancelledError:
                break
            except Exception as exc:
                if not self._running:
                    break
                logger.error(f"Redis subscriber error: {exc}. Reconnecting in {backoff}s...")
                await asyncio.sleep(backoff)
                backoff = min(backoff * 2, 30)  # Exponential back-off, cap at 30s

    # ------------------------------------------------------------------
    async def _process_loop(self) -> None:
        """
        Dequeue raw message strings, parse + validate them, then call on_packet.
        Runs concurrently with _subscribe_loop.
        """
        while self._running:
            try:
                raw = await asyncio.wait_for(self._queue.get(), timeout=1.0)
            except asyncio.TimeoutError:
                continue
            except asyncio.CancelledError:
                break

            # 1. JSON parsing
            try:
                data = json.loads(raw)
            except json.JSONDecodeError as exc:
                self.total_invalid += 1
                logger.warning(f"Failed to parse JSON: {exc} (raw={raw[:100]})")
                continue

            # 2. Pydantic schema validation — defense in depth
            try:
                packet = IoTPacket(**data)
            except (ValidationError, TypeError) as exc:
                self.total_invalid += 1
                logger.warning(f"Packet failed schema validation: {exc}")
                continue

            # 3. Hand off to the analytics pipeline
            try:
                await self._on_packet(packet)
                self.total_processed += 1
            except Exception as exc:
                logger.error(f"Pipeline error for packet {data.get('packet_id')}: {exc}")

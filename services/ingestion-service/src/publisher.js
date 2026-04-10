/**
 * NexusStream — Message Broker Publisher
 * ========================================
 * Publishes validated IoT packets to Redis Pub/Sub.
 *
 * Resilience Patterns implemented:
 *  1. In-memory ring buffer — packets are buffered when Redis is unavailable.
 *  2. Exponential back-off retry — reconnect attempts don't hammer the broker.
 *  3. Circuit-breaker-like state — when the buffer is full, oldest packets
 *     are evicted (backpressure) to avoid OOM crashes.
 *
 * Scalability Note:
 *   Each ingestion-service instance publishes to the same Redis channel.
 *   analytics-service instances subscribe and share load via consumer groups
 *   (Redis Streams would be the next step for at-least-once semantics).
 *
 * Swappability:
 *   The Publisher interface exposes only `.publish(packet)`.
 *   Swapping Redis for RabbitMQ/Kafka requires implementing the same interface.
 */

'use strict';

const Redis = require('ioredis');
const config = require('../config/default');
const logger = require('./logger');

// ---------------------------------------------------------------------------
// In-memory buffer for offline resilience
// ---------------------------------------------------------------------------
class RingBuffer {
  constructor(maxSize) {
    this.maxSize = maxSize;
    this.buffer = [];
  }

  push(item) {
    if (this.buffer.length >= this.maxSize) {
      // Evict oldest item — explicit backpressure
      const evicted = this.buffer.shift();
      logger.warn({ event: 'buffer_eviction', evicted_packet_id: evicted.packet_id });
    }
    this.buffer.push(item);
  }

  drain() {
    const items = [...this.buffer];
    this.buffer = [];
    return items;
  }

  get size() {
    return this.buffer.length;
  }
}

// ---------------------------------------------------------------------------
// Publisher Factory
// ---------------------------------------------------------------------------
async function createPublisher() {
  const buffer = new RingBuffer(config.bufferMaxSize);
  let isConnected = false;
  let draining = false;

  // ioredis reconnects automatically — we track logical readiness separately
  const redisClient = new Redis({
    host: config.redis.host,
    port: config.redis.port,
    password: config.redis.password || undefined,
    // Retry strategy: exponential back-off capped at 30s
    retryStrategy(times) {
      const delay = Math.min(100 * 2 ** times, 30000);
      logger.warn({ event: 'redis_retry', attempt: times, delay_ms: delay });
      return delay;
    },
    maxRetriesPerRequest: null, // never give up on queued commands
    enableReadyCheck: true,
    lazyConnect: false,
  });

  redisClient.on('connect', () => {
    logger.info({ event: 'redis_connected', host: config.redis.host });
  });

  redisClient.on('ready', async () => {
    isConnected = true;
    logger.info({ event: 'redis_ready' });
    // Drain buffered packets now that broker is back
    await drainBuffer();
  });

  redisClient.on('error', (err) => {
    isConnected = false;
    logger.error({ event: 'redis_error', error: err.message });
  });

  redisClient.on('close', () => {
    isConnected = false;
    logger.warn({ event: 'redis_disconnected' });
  });

  /**
   * Flush buffered packets to Redis.
   * Draining is serialized (draining flag) to avoid duplicate flushing
   * when connection cycles quickly.
   */
  async function drainBuffer() {
    if (draining || buffer.size === 0) return;
    draining = true;

    const packets = buffer.drain();
    logger.info({ event: 'buffer_drain_start', count: packets.length });

    const pipeline = redisClient.pipeline();
    for (const packet of packets) {
      pipeline.publish(config.redis.channel, JSON.stringify(packet));
    }

    try {
      await pipeline.exec();
      logger.info({ event: 'buffer_drain_complete', count: packets.length });
    } catch (err) {
      logger.error({ event: 'buffer_drain_failed', error: err.message });
      // Re-buffer the packets — they are not lost
      packets.forEach((p) => buffer.push(p));
    } finally {
      draining = false;
    }
  }

  /**
   * Publish a single packet.
   * Falls back to the in-memory buffer when Redis is unavailable.
   *
   * @param {object} packet - Validated IoT packet
   */
  async function publish(packet) {
    if (!isConnected) {
      buffer.push(packet);
      logger.debug({ event: 'packet_buffered', buffer_size: buffer.size, packet_id: packet.packet_id });
      return;
    }

    try {
      await redisClient.publish(config.redis.channel, JSON.stringify(packet));
    } catch (err) {
      // Broker publish failed — buffer for retry
      buffer.push(packet);
      logger.error({ event: 'publish_failed_buffered', error: err.message, buffer_size: buffer.size });
    }
  }

  return { publish };
}

module.exports = { createPublisher };

/**
 * NexusStream — IoT Device Simulator
 * ====================================
 * Simulates N IoT devices each emitting high-frequency telemetry packets.
 *
 * Production Note:
 *   In a real system this module is replaced by actual device SDKs (MQTT/CoAP).
 *   The simulator API contract (onPacket callback) remains identical,
 *   so swapping transports requires zero changes to index.js or publisher.js.
 *
 * Anomaly Injection:
 *   A configurable percentage of readings are intentionally anomalous
 *   (out-of-range values, wrong status codes) to exercise the analytics-service
 *   anomaly detection pipeline.
 */

'use strict';

const { v4: uuidv4 } = require('uuid');
const { validatePacket } = require('./validator');
const logger = require('./logger');

// Device types with realistic metric ranges
const DEVICE_TYPES = [
  { type: 'temperature_sensor', unit: '°C', min: -20, max: 85, anomalyMin: -50, anomalyMax: 150 },
  { type: 'pressure_sensor',    unit: 'Pa',  min: 80000, max: 120000, anomalyMin: 0, anomalyMax: 200000 },
  { type: 'humidity_sensor',    unit: '%',  min: 0, max: 100, anomalyMin: -10, anomalyMax: 200 },
  { type: 'vibration_sensor',   unit: 'Hz', min: 0, max: 500, anomalyMin: -100, anomalyMax: 10000 },
  { type: 'power_meter',        unit: 'W',  min: 0, max: 5000, anomalyMin: -500, anomalyMax: 50000 },
];

const STATUSES = ['ok', 'ok', 'ok', 'ok', 'ok', 'warning', 'error']; // weighted towards ok

/**
 * Generate a random float between min and max (inclusive).
 */
function randomFloat(min, max) {
  return parseFloat((Math.random() * (max - min) + min).toFixed(4));
}

/**
 * Generate a single IoT telemetry packet for a device.
 * @param {object} device - { device_id, type }
 * @param {number} anomalyRate - 0.0–1.0 probability of generating anomalous data
 */
function generatePacket(device, anomalyRate) {
  const isAnomaly = Math.random() < anomalyRate;
  const range = isAnomaly
    ? { min: device.meta.anomalyMin, max: device.meta.anomalyMax }
    : { min: device.meta.min, max: device.meta.max };

  return {
    packet_id:    uuidv4(),
    device_id:    device.device_id,
    device_type:  device.meta.type,
    metric_value: randomFloat(range.min, range.max),
    unit:         device.meta.unit,
    // Anomalous readings often have error status — simulates real-world correlation
    status: isAnomaly
      ? (Math.random() < 0.7 ? 'error' : 'warning')
      : STATUSES[Math.floor(Math.random() * STATUSES.length)],
    is_anomaly:   isAnomaly,
    timestamp:    new Date().toISOString(),
    metadata: {
      firmware_version: '2.1.4',
      location: `zone-${Math.floor(Math.random() * 5) + 1}`,
    },
  };
}

/**
 * Start the simulator.
 * The simulator ticks every `intervalMs` ms and fires `onPacket` for EACH device.
 * This gives `deviceCount * (1000 / intervalMs)` packets per second.
 *
 * Scalability Note:
 *   For >1000 devices, replace setInterval with a worker_threads pool
 *   to prevent event-loop saturation on a single core.
 *
 * @param {object}   opts
 * @param {number}   opts.deviceCount  - Number of devices to simulate
 * @param {number}   opts.intervalMs   - Emit interval per device
 * @param {number}   opts.anomalyRate  - Fraction of readings that are anomalous
 * @param {Function} opts.onPacket     - Async callback(packet) invoked per packet
 */
function startSimulator({ deviceCount, intervalMs, anomalyRate, onPacket }) {
  // Create device registry — assign a stable device_id per device for continuity
  const devices = Array.from({ length: deviceCount }, (_, i) => ({
    device_id: `device-${String(i + 1).padStart(4, '0')}`,
    meta: DEVICE_TYPES[i % DEVICE_TYPES.length],
  }));

  const packetsPerSecond = (deviceCount * (1000 / intervalMs)).toFixed(1);
  logger.info({
    event: 'simulator_started',
    device_count: deviceCount,
    interval_ms: intervalMs,
    anomaly_rate: anomalyRate,
    packets_per_second_estimate: packetsPerSecond,
  });

  let totalEmitted = 0;
  let totalDropped = 0;

  const tick = async () => {
    // Process each device in the same tick — all share one interval
    const tasks = devices.map(async (device) => {
      const packet = generatePacket(device, anomalyRate);

      // Validate before publishing — invalid data must never reach the broker
      const { valid, errors } = validatePacket(packet);
      if (!valid) {
        totalDropped++;
        logger.warn({ event: 'packet_validation_failed', device_id: packet.device_id, errors });
        return;
      }

      try {
        await onPacket(packet);
        totalEmitted++;
      } catch (err) {
        // Publisher handles retries internally; log here for visibility
        logger.error({ event: 'packet_dispatch_error', device_id: packet.device_id, error: err.message });
      }
    });

    await Promise.allSettled(tasks);

    // Periodic stats log (every 1000 ticks ≈ every ~100s with 100ms interval)
    if (totalEmitted % (deviceCount * 1000) === 0 && totalEmitted > 0) {
      logger.info({ event: 'simulator_stats', total_emitted: totalEmitted, total_dropped: totalDropped });
    }
  };

  setInterval(tick, intervalMs);
}

module.exports = { startSimulator };

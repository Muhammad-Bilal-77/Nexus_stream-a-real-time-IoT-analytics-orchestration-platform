/**
 * NexusStream — Ingestion Service Configuration
 * ===============================================
 * All config is read from environment variables.
 * 12-factor app principle: env vars are the single source of truth for config.
 * Default values here are for LOCAL DEVELOPMENT ONLY — never production defaults.
 *
 * In production, supply all values via Docker secrets or a secrets manager.
 */

'use strict';

module.exports = {
  env:    process.env.NODE_ENV   || 'development',
  port:   parseInt(process.env.INGESTION_PORT || '3001', 10),

  // Simulator settings
  deviceCount:      parseInt(process.env.DEVICE_COUNT      || '10',   10),
  publishIntervalMs: parseInt(process.env.PUBLISH_INTERVAL_MS || '100', 10),
  anomalyRate:      parseFloat(process.env.ANOMALY_RATE    || '0.05'),
  bufferMaxSize:    parseInt(process.env.BUFFER_MAX_SIZE   || '1000', 10),
  retryIntervalMs:  parseInt(process.env.RETRY_INTERVAL_MS || '3000', 10),

  // Redis broker
  redis: {
    host:    process.env.REDIS_HOST     || 'localhost',
    port:    parseInt(process.env.REDIS_PORT || '6379', 10),
    password: process.env.REDIS_PASSWORD || '',
    channel: process.env.REDIS_IOT_CHANNEL || 'iot:metrics',
  },

  // Logging
  logLevel:  process.env.LOG_LEVEL  || 'info',
  logFormat: process.env.LOG_FORMAT || 'json',
};

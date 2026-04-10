/**
 * NexusStream — Structured Logger (Winston)
 * ==========================================
 * Production Note:
 *   Structured JSON logging is mandatory for production systems.
 *   It enables log aggregation tools (Datadog, Loki, ELK) to parse,
 *   index, and alert on specific fields without regex parsing.
 *
 *   The logger is a singleton — import once, use everywhere.
 *   Log level is configurable via LOG_LEVEL env var → no code changes needed
 *   to increase verbosity in production for debugging.
 */

'use strict';

const { createLogger, format, transports } = require('winston');
const config = require('../config/default');

// ---------------------------------------------------------------------------
// Format configuration
// ---------------------------------------------------------------------------
// In production: pure JSON for log aggregators (Datadog, CloudWatch, Loki)
// In development: colorized pretty-print for human readability
const logFormat = config.logFormat === 'json'
  ? format.combine(
      format.timestamp(),
      format.errors({ stack: true }),   // include stack traces in JSON
      format.json()
    )
  : format.combine(
      format.colorize(),
      format.timestamp({ format: 'HH:mm:ss' }),
      format.printf(({ timestamp, level, message, ...meta }) => {
        const metaStr = Object.keys(meta).length ? JSON.stringify(meta, null, 2) : '';
        return `${timestamp} [${level}] ${message} ${metaStr}`;
      })
    );

// ---------------------------------------------------------------------------
// Logger instance — add service context to every log line
// ---------------------------------------------------------------------------
const logger = createLogger({
  level: config.logLevel,
  defaultMeta: {
    service: 'ingestion-service',
    version: '1.0.0',
  },
  format: logFormat,
  transports: [
    new transports.Console(),
    // Production: add file transport or external sink (Datadog agent, Fluentd)
    // new transports.File({ filename: '/var/log/nexusstream/ingestion-error.log', level: 'error' }),
  ],
});

module.exports = logger;

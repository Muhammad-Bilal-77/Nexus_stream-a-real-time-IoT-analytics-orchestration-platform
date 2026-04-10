/**
 * NexusStream — IoT Packet Validator
 * ====================================
 * Uses AJV (Another JSON Validator) with JSON Schema Draft-07.
 *
 * Production Note:
 *   Schema validation is the first line of defense.
 *   Invalid data is dropped BEFORE reaching the broker, preventing
 *   downstream services from processing corrupt records.
 *
 *   AJV is compiled once at startup (expensive) and reused across
 *   all validation calls (cheap) — this is the correct AJV usage pattern.
 */

'use strict';

const Ajv = require('ajv');
const addFormats = require('ajv-formats');

// Compile AJV instance once — singleton pattern for performance
const ajv = new Ajv({ allErrors: true, strict: false });
addFormats(ajv);

// ---------------------------------------------------------------------------
// IoT Telemetry Packet Schema
// ---------------------------------------------------------------------------
const iotPacketSchema = {
  $schema: 'http://json-schema.org/draft-07/schema#',
  title: 'IotTelemetryPacket',
  type: 'object',
  required: ['packet_id', 'device_id', 'device_type', 'metric_value', 'unit', 'status', 'timestamp'],
  additionalProperties: true, // allow metadata fields
  properties: {
    packet_id: {
      type: 'string',
      format: 'uuid',
      description: 'Unique identifier for deduplication',
    },
    device_id: {
      type: 'string',
      minLength: 1,
      maxLength: 64,
      pattern: '^device-[0-9]{4}$',
      description: 'Stable device identifier matching registry',
    },
    device_type: {
      type: 'string',
      enum: ['temperature_sensor', 'pressure_sensor', 'humidity_sensor', 'vibration_sensor', 'power_meter'],
    },
    metric_value: {
      type: 'number',
      description: 'Primary sensor reading',
    },
    unit: {
      type: 'string',
      minLength: 1,
    },
    status: {
      type: 'string',
      enum: ['ok', 'warning', 'error'],
    },
    is_anomaly: {
      type: 'boolean',
      description: 'True when the simulator injected an anomalous value',
    },
    timestamp: {
      type: 'string',
      format: 'date-time',
      description: 'ISO-8601 UTC timestamp — always set by ingestion, not device',
    },
    metadata: {
      type: 'object',
      properties: {
        firmware_version: { type: 'string' },
        location:         { type: 'string' },
      },
    },
  },
};

// Pre-compile the schema once
const validate = ajv.compile(iotPacketSchema);

/**
 * Validate an IoT telemetry packet against the schema.
 *
 * @param {object} packet - Raw packet object
 * @returns {{ valid: boolean, errors: Array|null }}
 */
function validatePacket(packet) {
  const valid = validate(packet);
  return {
    valid,
    errors: valid ? null : validate.errors,
  };
}

module.exports = { validatePacket };

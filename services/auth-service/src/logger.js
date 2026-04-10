/**
 * NexusStream — Auth Service Logger
 */
'use strict';

const { createLogger, format, transports } = require('winston');
const config = require('../config/default');

const logger = createLogger({
  level: config.logLevel,
  defaultMeta: { service: 'auth-service', version: '1.0.0' },
  format: format.combine(format.timestamp(), format.errors({ stack: true }), format.json()),
  transports: [new transports.Console()],
});

module.exports = logger;

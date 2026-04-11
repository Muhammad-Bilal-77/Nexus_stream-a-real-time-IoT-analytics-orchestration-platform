/**
 * NexusStream — Auth Service Configuration
 */
'use strict';

module.exports = {
  env:            process.env.NODE_ENV      || 'development',
  port:           parseInt(process.env.AUTH_PORT || '3002', 10),
  jwtSecret:      process.env.JWT_SECRET    || 'dev-only-secret-change-me',
  jwtAccessExpiry: process.env.JWT_ACCESS_EXPIRY || '15m',
  jwtRefreshExpiry: process.env.JWT_REFRESH_EXPIRY || '7d',
  postgres: {
    host:     process.env.POSTGRES_HOST     || 'localhost',
    port:     parseInt(process.env.POSTGRES_PORT || '5432', 10),
    database: process.env.POSTGRES_DB       || 'nexusstream',
    user:     process.env.POSTGRES_USER     || 'nexus_admin',
    password: process.env.POSTGRES_PASSWORD || 'changeme',
  },
  redis: {
    host:     process.env.REDIS_HOST     || 'localhost',
    port:     parseInt(process.env.REDIS_PORT || '6379', 10),
    password: process.env.REDIS_PASSWORD || 'Str0ng_Redis_Pass!',
  },
  logLevel: process.env.LOG_LEVEL || 'info',
};

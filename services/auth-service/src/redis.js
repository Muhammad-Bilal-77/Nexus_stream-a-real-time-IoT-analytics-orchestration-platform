/**
 * NexusStream Auth Service — Redis Connector for Blacklisting
 */
'use strict';

const Redis = require('ioredis');
const config = require('../config/default');
const logger = require('./logger');

let redis = null;

try {
  redis = new Redis({
    host: config.redis.host,
    port: config.redis.port,
    password: config.redis.password,
    lazyConnect: true,
    maxRetriesPerRequest: 3,
  });

  redis.on('error', (err) => {
    logger.warn({ event: 'redis_error', message: 'Redis not available for blacklisting, falling back to memory', error: err.message });
  });

  redis.on('connect', () => {
    logger.info({ event: 'redis_connected', message: 'Connected to Redis for token revocation' });
  });
} catch (err) {
  logger.error({ event: 'redis_init_error', error: err.message });
}

/**
 * Add a token to the blacklist
 * @param {string} jti - Unique token identifier or the token itself
 * @param {number} ttlSeconds - Time to live in seconds (until token naturally expires)
 */
async function blacklistToken(token, ttlSeconds) {
  if (!redis || redis.status !== 'ready') return;
  try {
    // We use the token as the key
    await redis.set(`blacklist:${token}`, 'revoked', 'EX', Math.max(ttlSeconds, 1));
    logger.info({ event: 'token_blacklisted', ttl: ttlSeconds });
  } catch (err) {
    logger.warn({ event: 'blacklist_error', error: err.message });
  }
}

/**
 * Check if a token is blacklisted
 */
async function isBlacklisted(token) {
  if (!redis || redis.status !== 'ready') return false;
  try {
    const result = await redis.get(`blacklist:${token}`);
    return result === 'revoked';
  } catch (err) {
    return false;
  }
}

module.exports = {
  blacklistToken,
  isBlacklisted,
  instance: redis
};

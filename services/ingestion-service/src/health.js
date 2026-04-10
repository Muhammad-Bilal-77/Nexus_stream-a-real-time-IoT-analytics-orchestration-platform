/**
 * NexusStream — Health Check Endpoint
 * =====================================
 * Production Note:
 *   /health is the standard liveness probe path for Docker, k8s, and AWS ALB.
 *   Keep it FAST — it must not do heavy work.
 *   Returning memory usage and uptime aids in diagnosing leaks in production.
 *
 *   A deeper "readiness" probe (/ready) would verify Redis connectivity
 *   before signaling traffic-readiness to the load balancer — stub below.
 */

'use strict';

const logger = require('./logger');

const startTime = Date.now();

/**
 * Register health + readiness routes on an Express app.
 * @param {import('express').Application} app
 */
function registerHealthRoute(app) {
  // Liveness — "Is the process alive?"
  app.get('/health', (_req, res) => {
    const uptimeMs = Date.now() - startTime;
    res.json({
      status: 'ok',
      service: 'ingestion-service',
      uptime_ms: uptimeMs,
      memory_mb: parseFloat((process.memoryUsage().heapUsed / 1024 / 1024).toFixed(2)),
      timestamp: new Date().toISOString(),
    });
  });

  // Readiness — "Is the service ready to receive traffic?"
  // In production: check Redis connectivity here
  app.get('/ready', (_req, res) => {
    // TODO: ping Redis and return 503 if unavailable
    res.json({ status: 'ready' });
  });

  logger.info({ event: 'health_routes_registered', paths: ['/health', '/ready'] });
}

module.exports = { registerHealthRoute };

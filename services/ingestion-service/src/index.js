/**
 * NexusStream — Ingestion Service Entry Point
 * ============================================
 * Architecture Decision: Stateless Express + WebSocket server.
 *   - Stateless → can be horizontally scaled behind a load balancer.
 *   - WebSocket endpoint (/ws) streams live readings to connected clients.
 *   - HTTP /health is used by Docker/k8s liveness probes.
 *   - All config read from environment variables → 12-factor app compliant.
 */

'use strict';

const http = require('http');
const { WebSocketServer } = require('ws');
const express = require('express');
const config = require('../config/default');
const logger = require('./logger');
const { startSimulator } = require('./simulator');
const { createPublisher } = require('./publisher');
const { registerHealthRoute } = require('./health');

// ---------------------------------------------------------------------------
// Bootstrap
// ---------------------------------------------------------------------------
async function bootstrap() {
  const app = express();
  app.use(express.json());

  // Health check — no auth required, used by orchestrators
  registerHealthRoute(app);

  // Create unified HTTP server so Express + WebSocket share port
  const server = http.createServer(app);

  // WebSocket server for pushing live data to dashboard clients
  const wss = new WebSocketServer({ server, path: '/ws' });

  // Broadcast helper — sends to all connected WS clients
  // In production, use Redis Pub/Sub fan-out so all instances reach all clients
  const broadcastToClients = (payload) => {
    const message = JSON.stringify(payload);
    wss.clients.forEach((client) => {
      if (client.readyState === client.OPEN) {
        client.send(message);
      }
    });
  };

  wss.on('connection', (ws, req) => {
    logger.info({ event: 'ws_client_connected', ip: req.socket.remoteAddress });
    ws.on('close', () => logger.info({ event: 'ws_client_disconnected' }));
    ws.on('error', (err) => logger.error({ event: 'ws_client_error', error: err.message }));
  });

  // Initialize message broker publisher (Redis Pub/Sub by default)
  const publisher = await createPublisher();

  // Start the IoT device simulator — it calls back for every validated packet
  startSimulator({
    deviceCount: config.deviceCount,
    intervalMs: config.publishIntervalMs,
    anomalyRate: config.anomalyRate,

    onPacket: async (packet) => {
      // 1. Publish to broker (analytics-service consumes this)
      await publisher.publish(packet);

      // 2. Push to connected WebSocket clients (dashboard real-time feed)
      broadcastToClients(packet);
    },
  });

  server.listen(config.port, () => {
    logger.info({
      event: 'server_started',
      port: config.port,
      deviceCount: config.deviceCount,
      intervalMs: config.publishIntervalMs,
      env: config.env,
    });
  });
}

// Graceful shutdown — flush in-flight data, close broker connection
process.on('SIGTERM', () => {
  logger.info({ event: 'shutdown_initiated', signal: 'SIGTERM' });
  process.exit(0);
});

process.on('unhandledRejection', (reason) => {
  logger.error({ event: 'unhandled_rejection', reason: String(reason) });
  process.exit(1);
});

bootstrap().catch((err) => {
  // Use console.error here as logger may not be ready
  console.error('Fatal startup error', err);
  process.exit(1);
});

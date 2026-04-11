/**
 * NexusStream — Auth Service (Stub)
 * ====================================
 * Tech: Node.js + Express + jsonwebtoken
 *
 * Planned Functionality (production):
 *   - JWT RS256 signing + verification (asymmetric keys)
 *   - OAuth 2.0 flows: GitHub + Google (via Passport.js)
 *   - RBAC: roles (admin, analyst, viewer) stored in PostgreSQL
 *   - Token refresh endpoint + refresh token rotation
 *   - Rate limiting on login endpoints (express-rate-limit)
 *
 * Current State: STUB — basic JWT sign/verify endpoints.
 *   Uses HS256 with a symmetric secret until RSA keypair is provisioned.
 *   OAuth flow routes are registered but return 501 Not Implemented.
 */

'use strict';

require('dotenv').config({ path: require('path').resolve(__dirname, '../../.env') });

const express = require('express');
const cors = require('cors');
const jwt = require('jsonwebtoken');
const config = require('../config/default');
const logger = require('./logger');

const app = express();
app.use(cors());
app.use(express.json());

// ---------------------------------------------------------------------------
// Setup resources on boot
// ---------------------------------------------------------------------------
const keys = require('./keys');
const db = require('./db');
keys.generateKeys();
db.createTables();

// Require passport configuration
require('./strategies');
const passport = require('passport');
app.use(passport.initialize());

// ---------------------------------------------------------------------------
// Health Check
// ---------------------------------------------------------------------------
app.get('/health', async (_req, res) => {
  const dbUp = await db.ping();
  res.status(dbUp ? 200 : 503).json({
    status: dbUp ? 'ok' : 'degraded',
    service: 'auth-service',
    postgres: dbUp ? 'connected' : 'unreachable',
    timestamp: new Date().toISOString(),
  });
});
// ---------------------------------------------------------------------------
// OAuth Routes
// ---------------------------------------------------------------------------

app.get('/auth/google', passport.authenticate('google', {
  scope: ['profile', 'email'],
  session: false
}));

app.get('/auth/google/callback', passport.authenticate('google', {
  session: false,
  failureRedirect: 'http://localhost:5173/login?error=oauth_failed'
}), (req, res) => {
  // Successful authentication, redirect to frontend with tokens.
  const { access_token, refresh_token } = req.user;
  res.redirect(`http://localhost:5173/auth/callback?access_token=${access_token}&refresh_token=${refresh_token}`);
});

app.get('/auth/github', passport.authenticate('github', {
  scope: ['user:email'],
  session: false
}));

app.get('/auth/github/callback', passport.authenticate('github', {
  session: false,
  failureRedirect: 'http://localhost:5173/login?error=oauth_failed'
}), (req, res) => {
  const { access_token, refresh_token } = req.user;
  res.redirect(`http://localhost:5173/auth/callback?access_token=${access_token}&refresh_token=${refresh_token}`);
});

// ---------------------------------------------------------------------------
// Core Auth Routes (RS256, DB-backed)
// ---------------------------------------------------------------------------
const authRoutes = require('./routes/auth');
app.use('/auth', authRoutes);

// ---------------------------------------------------------------------------
// Start Server

// ---------------------------------------------------------------------------
// Start Server
// ---------------------------------------------------------------------------
app.listen(config.port, () => {
  logger.info({ event: 'auth_service_started', port: config.port, env: config.env });
});

module.exports = app; // export for testing

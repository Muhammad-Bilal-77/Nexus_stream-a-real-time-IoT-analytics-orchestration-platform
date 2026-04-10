/**
 * NexusStream Auth Service — User lifecycle and JWT generation 
 */
'use strict';

const express = require('express');
const bcrypt = require('bcrypt');
const jwt = require('jsonwebtoken');
const rateLimit = require('express-rate-limit');
const crypto = require('crypto');
const db = require('../db');
const keys = require('../keys');
const config = require('../../config/default');
const logger = require('../logger');
const { sendMagicLinkEmail } = require('../mailer');

// Common token generation function
function generateTokens(user, roles) {
  const payload = {
    sub: user.username,
    user_id: user.id,
    username: user.username,
    roles: roles
  };

  const accessToken = jwt.sign(payload, keys.getPrivateKey(), {
    algorithm: 'RS256',
    expiresIn: config.jwtAccessExpiry,
    issuer: 'nexusstream-auth',
    audience: 'nexusstream-api'
  });

  const refreshToken = jwt.sign({ sub: user.username, type: 'refresh' }, keys.getPrivateKey(), {
    algorithm: 'RS256',
    expiresIn: config.jwtRefreshExpiry
  });

  return { accessToken, refreshToken };
}

const router = express.Router();

const magicLinkLimiter = rateLimit({
  windowMs: 60 * 1000, // 1 minute
  max: 5, // 5 requests per minute per IP
  message: { error: 'Too many magic link requests from this IP, please try again after a minute' }
});

/**
 * GET /.well-known/jwks.json or /public-key
 * Downstream services fetch this to verify RS256 JWTs locally.
 */
router.get('/public-key', (req, res) => {
  res.json({
    public_key: keys.getPublicKey(),
    algorithm: 'RS256'
  });
});

/**
 * POST /auth/magic-link
 * Sends a magic link securely to the user. Creates a user if they don't exist.
 */
router.post('/magic-link', magicLinkLimiter, async (req, res) => {
  const { email } = req.body;
  if (!email) return res.status(400).json({ error: 'Email is required' });

  const client = await db.getClient();
  try {
    await client.query('BEGIN');
    
    // 1. Look up user
    let userRes = await client.query('SELECT id, username, is_active FROM users WHERE email = $1', [email]);
    let user;

    if (userRes.rowCount === 0) {
      // 2. Create new user automatically for magic link login
      const baseUsername = email.split('@')[0];
      const uniqueUsername = `${baseUsername}_${crypto.randomBytes(3).toString('hex')}`;
      
      const insertRes = await client.query(
        `INSERT INTO users (username, email, is_active) VALUES ($1, $2, true) RETURNING id, username`,
        [uniqueUsername, email]
      );
      user = insertRes.rows[0];
      
      const roleRes = await client.query(`SELECT id FROM roles WHERE name = 'viewer'`);
      if (roleRes.rowCount > 0) {
        await client.query(`INSERT INTO user_roles (user_id, role_id) VALUES ($1, $2)`, [user.id, roleRes.rows[0].id]);
      }
    } else {
      user = userRes.rows[0];
      if (!user.is_active) {
        await client.query('ROLLBACK');
        return res.status(403).json({ error: 'Account disabled' });
      }
    }

    // 3. Create Magic Link token
    const tokenRes = await client.query(
      `INSERT INTO magic_links (user_id, expires_at) VALUES ($1, NOW() + INTERVAL '10 minutes') RETURNING token`,
      [user.id]
    );
    const token = tokenRes.rows[0].token;
    
    await client.query('COMMIT');
    
    // 4. Send Email
    const magicLink = `http://localhost:5173/auth/callback?token=${token}`;
    logger.info({ event: 'magic_link_generated', email, magicLink });
    
    try {
      await sendMagicLinkEmail(email, magicLink);
    } catch (mailErr) {
      return res.status(500).json({ error: 'Failed to send email. Check SMTP credentials.' });
    }

    res.json({ message: 'Magic link sent successfully. Please check your inbox.' });
  } catch (err) {
    await client.query('ROLLBACK');
    logger.error({ event: 'magic_link_error', error: err.message });
    res.status(500).json({ error: 'Internal server error' });
  } finally {
    client.release();
  }
});

/**
 * POST /auth/magic-link/verify
 * Validates a magic link token and returns JWTs.
 */
router.post('/magic-link/verify', async (req, res) => {
  const { token } = req.body;
  if (!token) return res.status(400).json({ error: 'Token is required' });

  const client = await db.getClient();
  try {
    await client.query('BEGIN');
    
    // 1. Verify token exists, is valid, un-used, and not expired
    const linkRes = await client.query(
      `SELECT user_id, used FROM magic_links WHERE token = $1 AND expires_at > NOW() FOR UPDATE`,
      [token]
    );
    
    if (linkRes.rowCount === 0) {
      await client.query('ROLLBACK');
      return res.status(401).json({ error: 'Invalid or expired magic link' });
    }
    
    if (linkRes.rows[0].used) {
      await client.query('ROLLBACK');
      return res.status(401).json({ error: 'This magic link has already been used' });
    }

    const userId = linkRes.rows[0].user_id;

    // 2. Mark token as used
    await client.query('UPDATE magic_links SET used = true WHERE token = $1', [token]);

    // 3. Get user info
    const userRes = await client.query('SELECT id, username, is_active FROM users WHERE id = $1', [userId]);
    if (userRes.rowCount === 0 || !userRes.rows[0].is_active) {
      await client.query('ROLLBACK');
      return res.status(403).json({ error: 'Account disabled or deleted' });
    }
    const user = userRes.rows[0];

    // 4. Get roles
    const roleRes = await client.query(`
      SELECT r.name FROM roles r
      JOIN user_roles ur ON r.id = ur.role_id
      WHERE ur.user_id = $1
    `, [user.id]);
    const roles = roleRes.rows.map(row => row.name);

    await client.query('COMMIT');
    
    // 5. Generate and return JWTs
    const { accessToken, refreshToken } = generateTokens(user, roles);
    
    logger.info({ event: 'magic_link_verify_success', username: user.username });
    
    res.json({
      access_token: accessToken,
      refresh_token: refreshToken,
      token_type: 'Bearer',
      expires_in: config.jwtAccessExpiry
    });
  } catch (err) {
    await client.query('ROLLBACK');
    logger.error({ event: 'magic_link_verify_error', error: err.message });
    res.status(500).json({ error: 'Internal server error' });
  } finally {
    client.release();
  }
});

/**
 * POST /auth/signup
 */
router.post('/signup', async (req, res) => {
  const { username, email, password } = req.body;

  if (!username || !email || !password) {
    return res.status(400).json({ error: 'Missing required fields' });
  }

  const client = await db.getClient();
  try {
    await client.query('BEGIN');

    // Check if user already exists
    const existing = await client.query('SELECT id FROM users WHERE username = $1 OR email = $2', [username, email]);
    if (existing.rowCount > 0) {
      return res.status(409).json({ error: 'User already exists' });
    }

    // Hash password
    const saltRounds = 10;
    const passwordHash = await bcrypt.hash(password, saltRounds);

    // Insert user
    const userRes = await client.query(
      `INSERT INTO users (username, email, password_hash) VALUES ($1, $2, $3) RETURNING id, username`,
      [username, email, passwordHash]
    );
    const user = userRes.rows[0];

    // Get 'viewer' role ID
    const roleRes = await client.query(`SELECT id FROM roles WHERE name = 'viewer'`);
    if (roleRes.rowCount > 0) {
      const roleId = roleRes.rows[0].id;
      await client.query(`INSERT INTO user_roles (user_id, role_id) VALUES ($1, $2)`, [user.id, roleId]);
    }

    await client.query('COMMIT');
    logger.info({ event: 'user_created', username: user.username });
    
    res.status(201).json({ message: 'User created successfully', id: user.id, username: user.username });
  } catch (err) {
    await client.query('ROLLBACK');
    logger.error({ event: 'signup_error', error: err.message });
    res.status(500).json({ error: 'Internal server error' });
  } finally {
    client.release();
  }
});

/**
 * POST /auth/login
 */
router.post('/login', async (req, res) => {
  const { username, password } = req.body;

  if (!username || !password) {
    return res.status(400).json({ error: 'Username and password required' });
  }

  try {
    // Lookup user
    const userRes = await db.query('SELECT id, username, password_hash, is_active FROM users WHERE username = $1', [username]);
    if (userRes.rowCount === 0) {
      return res.status(401).json({ error: 'Invalid credentials' });
    }
    
    const user = userRes.rows[0];
    
    if (!user.is_active) {
      return res.status(403).json({ error: 'Account disabled' });
    }

    // Verify password (except for the hardcoded plaintext fallback in the seed data for testing)
    const isMockHash = user.password_hash === 'PLACEHOLDER_HASH' && password === 'nexusstream';
    const isMatch = isMockHash || await bcrypt.compare(password, user.password_hash);
    
    if (!isMatch) {
      return res.status(401).json({ error: 'Invalid credentials' });
    }

    // Load roles
    const roleRes = await db.query(`
      SELECT r.name FROM roles r
      JOIN user_roles ur ON r.id = ur.role_id
      WHERE ur.user_id = $1
    `, [user.id]);
    
    const roles = roleRes.rows.map(row => row.name);

    // MINT RS256 JWT
    const payload = {
      sub: user.username,          // Using username as sub for dashboard convenience
      user_id: user.id,
      username: user.username,
      roles: roles
    };

    const token = jwt.sign(payload, keys.getPrivateKey(), {
      algorithm: 'RS256',
      expiresIn: config.jwtAccessExpiry,
      issuer: 'nexusstream-auth',
      audience: 'nexusstream-api'
    });

    const refreshToken = jwt.sign({ sub: user.username, type: 'refresh' }, keys.getPrivateKey(), {
      algorithm: 'RS256',
      expiresIn: config.jwtRefreshExpiry
    });

    logger.info({ event: 'login_success', username });
    
    res.json({
      access_token: token,
      refresh_token: refreshToken,
      token_type: 'Bearer',
      expires_in: config.jwtAccessExpiry
    });

  } catch (err) {
    logger.error({ event: 'login_error', error: err.message });
    res.status(500).json({ error: 'Internal server error' });
  }
});

/**
 * POST /auth/refresh
 */
router.post('/refresh', async (req, res) => {
  const { refresh_token } = req.body;
  if (!refresh_token) {
    return res.status(400).json({ error: 'refresh_token required' });
  }
  
  try {
    const decoded = jwt.verify(refresh_token, keys.getPublicKey(), { algorithms: ['RS256'] });
    if (decoded.type !== 'refresh') {
      return res.status(400).json({ error: 'Invalid token type' });
    }

    // Reload user and roles
    const userRes = await db.query('SELECT id, username, is_active FROM users WHERE username = $1', [decoded.sub]);
    if (userRes.rowCount === 0 || !userRes.rows[0].is_active) {
      return res.status(401).json({ error: 'Invalid user' });
    }
    const user = userRes.rows[0];

    const roleRes = await db.query(`
      SELECT r.name FROM roles r
      JOIN user_roles ur ON r.id = ur.role_id
      WHERE ur.user_id = $1
    `, [user.id]);
    const roles = roleRes.rows.map(row => row.name);

    // Issue new access token
    const payload = {
      sub: user.username,
      user_id: user.id,
      username: user.username,
      roles: roles
    };

    const newAccessToken = jwt.sign(payload, keys.getPrivateKey(), {
      algorithm: 'RS256',
      expiresIn: config.jwtAccessExpiry,
      issuer: 'nexusstream-auth',
      audience: 'nexusstream-api'
    });

    res.json({
      access_token: newAccessToken,
      token_type: 'Bearer',
      expires_in: config.jwtAccessExpiry
    });
  } catch (err) {
    return res.status(401).json({ error: 'Invalid refresh token' });
  }
});

/**
 * GET /auth/verify 
 * Standalone verification utility (useful for APIs wanting to explicitly delegate check).
 */
router.get('/verify', (req, res) => {
  const authHeader = req.headers['authorization'];
  if (!authHeader || !authHeader.startsWith('Bearer ')) {
    return res.status(401).json({ error: 'missing_token' });
  }

  const token = authHeader.slice(7);
  try {
    const decoded = jwt.verify(token, keys.getPublicKey(), { algorithms: ['RS256'] });
    res.json({ valid: true, payload: decoded });
  } catch (err) {
    res.status(401).json({ valid: false, error: err.message });
  }
});

module.exports = router;

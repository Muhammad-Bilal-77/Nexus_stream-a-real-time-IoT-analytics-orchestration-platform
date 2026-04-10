const passport = require('passport');
const GoogleStrategy = require('passport-google-oauth20').Strategy;
const GitHubStrategy = require('passport-github2').Strategy;
const db = require('./db');
const jwt = require('jsonwebtoken');
const keys = require('./keys');
const config = require('../config/default');
const logger = require('./logger');

// Generate JWT tokens after a successful OAuth login
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

// Reusable function to handle OAuth user creation or lookup
async function verifyOAuth(provider, profile, email, done) {
  try {
    const client = await db.getClient();
    let user;
    let roles = [];
    
    try {
      await client.query('BEGIN');
      
      // Look up by email first to prevent duplicate users
      const emailRes = await client.query('SELECT id, username, is_active FROM users WHERE email = $1', [email]);
      
      if (emailRes.rowCount > 0) {
        user = emailRes.rows[0];
        
        if (!user.is_active) {
          await client.query('ROLLBACK');
          return done(new Error('Account disabled'));
        }
        
        // Update oauth_provider if they logged in with password previously
        await client.query('UPDATE users SET oauth_provider = $1, oauth_id = $2 WHERE id = $3', [provider, profile.id, user.id]);
        
        // Load roles
        const roleRes = await client.query(`
          SELECT r.name FROM roles r
          JOIN user_roles ur ON r.id = ur.role_id
          WHERE ur.user_id = $1
        `, [user.id]);
        roles = roleRes.rows.map(row => row.name);

      } else {
        // Create new user
        const baseUsername = profile.displayName ? profile.displayName.replace(/[^a-zA-Z0-9]/g, '').toLowerCase() : email.split('@')[0];
        const uniqueUsername = `${baseUsername}_${Math.random().toString(36).substr(2, 5)}`;
        
        const insertRes = await client.query(
          `INSERT INTO users (username, email, oauth_provider, oauth_id) VALUES ($1, $2, $3, $4) RETURNING id, username`,
          [uniqueUsername, email, provider, profile.id]
        );
        user = insertRes.rows[0];
        
        // Assign default 'viewer' role
        const roleRes = await client.query(`SELECT id, name FROM roles WHERE name = 'viewer'`);
        if (roleRes.rowCount > 0) {
          const roleId = roleRes.rows[0].id;
          await client.query(`INSERT INTO user_roles (user_id, role_id) VALUES ($1, $2)`, [user.id, roleId]);
          roles = [roleRes.rows[0].name];
        }
      }
      
      await client.query('COMMIT');
    } catch (err) {
      await client.query('ROLLBACK');
      throw err;
    } finally {
      client.release();
    }
    
    // Create tokens
    const { accessToken, refreshToken } = generateTokens(user, roles);
    logger.info({ event: 'oauth_login_success', provider, username: user.username });
    
    return done(null, { access_token: accessToken, refresh_token: refreshToken });
    
  } catch (err) {
    logger.error({ event: 'oauth_error', error: err.message });
    return done(err);
  }
}

// Configuration from env vars
// Note: We're using placeholders if not defined. Social login will fail if not provided in real environment.
const GOOGLE_CLIENT_ID = process.env.GOOGLE_CLIENT_ID || 'placeholder_google_id';
const GOOGLE_CLIENT_SECRET = process.env.GOOGLE_CLIENT_SECRET || 'placeholder_google_secret';
const GITHUB_CLIENT_ID = process.env.GITHUB_CLIENT_ID || 'placeholder_github_id';
const GITHUB_CLIENT_SECRET = process.env.GITHUB_CLIENT_SECRET || 'placeholder_github_secret';

passport.use(new GoogleStrategy({
    clientID: GOOGLE_CLIENT_ID,
    clientSecret: GOOGLE_CLIENT_SECRET,
    callbackURL: 'http://localhost:3002/auth/google/callback'
  },
  async (accessToken, refreshToken, profile, done) => {
    const email = profile.emails && profile.emails[0] ? profile.emails[0].value : null;
    if (!email) return done(new Error('No email found in Google profile'));
    return verifyOAuth('google', profile, email, done);
  }
));

passport.use(new GitHubStrategy({
    clientID: GITHUB_CLIENT_ID,
    clientSecret: GITHUB_CLIENT_SECRET,
    callbackURL: 'http://localhost:3002/auth/github/callback',
    scope: ['user:email']
  },
  async (accessToken, refreshToken, profile, done) => {
    let email = profile.emails && profile.emails[0] ? profile.emails[0].value : null;
    if (!email) return done(new Error('No email found in GitHub profile'));
    return verifyOAuth('github', profile, email, done);
  }
));

module.exports = passport;

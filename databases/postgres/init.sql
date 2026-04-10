-- =============================================================================
-- NexusStream — PostgreSQL Initialization Script
-- =============================================================================
-- Runs automatically when the PostgreSQL container starts for the first time.
-- Production Note: Use Flyway or Alembic for schema migrations — not raw SQL.

-- ---------------------------------------------------------------------------
-- Extensions
-- ---------------------------------------------------------------------------
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";  -- for uuid_generate_v4()
CREATE EXTENSION IF NOT EXISTS "pgcrypto";   -- for password hashing

-- ---------------------------------------------------------------------------
-- Roles / RBAC
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS roles (
    id          UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    name        VARCHAR(64) UNIQUE NOT NULL,           -- e.g. 'admin', 'analyst', 'viewer'
    description TEXT,
    created_at  TIMESTAMPTZ DEFAULT NOW()
);

INSERT INTO roles (name, description) VALUES
    ('admin',   'Full platform access'),
    ('analyst', 'Read-write analytics access'),
    ('viewer',  'Read-only dashboard access')
ON CONFLICT (name) DO NOTHING;

-- ---------------------------------------------------------------------------
-- Users
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS users (
    id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    username        VARCHAR(128) UNIQUE NOT NULL,
    email           VARCHAR(256) UNIQUE NOT NULL,
    -- Store bcrypt hashes, never plaintext. Length 60 for bcrypt output.
    password_hash   CHAR(60),
    oauth_provider  VARCHAR(32),   -- 'github' | 'google' | NULL (local auth)
    oauth_id        VARCHAR(128),  -- external provider user ID
    is_active       BOOLEAN DEFAULT TRUE,
    created_at      TIMESTAMPTZ DEFAULT NOW(),
    updated_at      TIMESTAMPTZ DEFAULT NOW()
);

-- ---------------------------------------------------------------------------
-- User ↔ Role (many-to-many)
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS user_roles (
    user_id     UUID REFERENCES users(id) ON DELETE CASCADE,
    role_id     UUID REFERENCES roles(id) ON DELETE CASCADE,
    granted_at  TIMESTAMPTZ DEFAULT NOW(),
    PRIMARY KEY (user_id, role_id)
);

-- ---------------------------------------------------------------------------
-- Device Registry (future use by dashboard + analytics)
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS devices (
    id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    device_id       VARCHAR(64) UNIQUE NOT NULL,   -- matches simulator device_id
    device_type     VARCHAR(64) NOT NULL,
    location        VARCHAR(128),
    firmware_version VARCHAR(32),
    registered_at   TIMESTAMPTZ DEFAULT NOW(),
    last_seen_at    TIMESTAMPTZ,
    is_active       BOOLEAN DEFAULT TRUE
);

-- ---------------------------------------------------------------------------
-- Audit Log (immutable append-only)
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS audit_log (
    id          BIGSERIAL PRIMARY KEY,
    user_id     UUID REFERENCES users(id),
    action      VARCHAR(128) NOT NULL,
    resource    VARCHAR(128),
    ip_address  INET,
    created_at  TIMESTAMPTZ DEFAULT NOW()
);

-- ---------------------------------------------------------------------------
-- Seed Data (development only — remove in production)
-- ---------------------------------------------------------------------------
INSERT INTO users (username, email, password_hash, is_active)
VALUES ('admin', 'admin@nexusstream.local', 'PLACEHOLDER_HASH', TRUE)
ON CONFLICT (username) DO NOTHING;

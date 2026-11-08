-- Initial schema for the shared Google authorization server.
-- Centralized Authorization Server for 5 Google family envs
-- (gmail / googledocs / googlesheets / googledrive / calendar)
--
-- Phase 1 scope: 5 tables covering identity + OAuth token lifecycle.
-- Phase 2 will add: oauth_consents (remembered grants).
--
-- Idempotent. Safe to run on fresh DBs.

-- ─── Tenants ────────────────────────────────────────────────────────────────
-- Each tenant isolates a test run. Parallel tests use separate tenants.
-- Administrators and the test harness manage tenants through /api/v1/tenants.

CREATE TABLE IF NOT EXISTS tenants (
    id         TEXT PRIMARY KEY,
    name       TEXT NOT NULL DEFAULT '',
    status     TEXT NOT NULL DEFAULT 'active',
    created_at TIMESTAMP DEFAULT NOW()
);

INSERT INTO tenants (id, name) VALUES ('default', 'Default Tenant')
    ON CONFLICT (id) DO NOTHING;

-- ─── Users ──────────────────────────────────────────────────────────────────
-- The identity shared by all five Google envs.
-- UNIQUE(email, tenant_id) is the multi-tenant rule: one email may hold a
-- separate, independent account in each tenant.

CREATE TABLE IF NOT EXISTS users (
    id            SERIAL PRIMARY KEY,
    email         TEXT NOT NULL,
    tenant_id     TEXT NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    name          TEXT NOT NULL,
    password_hash TEXT NOT NULL,                  -- bcrypt
    avatar_url    TEXT,
    created_at    TIMESTAMP DEFAULT NOW(),
    UNIQUE(email, tenant_id)
);

CREATE INDEX IF NOT EXISTS idx_users_tenant_id ON users(tenant_id);

-- ─── OAuth clients ──────────────────────────────────────────────────────────
-- Pre-registered OAuth clients: the MCP servers, the first-party UI and any
-- third-party agent all register here.
--
-- tenant_id: NULL allows tokens for any tenant; otherwise the client serves only that tenant.
-- audiences: the default aud values carried by tokens this client requests.

CREATE TABLE IF NOT EXISTS oauth_clients (
    client_id      TEXT PRIMARY KEY,
    client_secret  TEXT,                          -- bcrypt; NULL = public client
    client_name    TEXT NOT NULL,
    tenant_id      TEXT REFERENCES tenants(id) ON DELETE CASCADE,
    redirect_uris  JSONB NOT NULL DEFAULT '[]'::jsonb,
    allowed_scopes JSONB NOT NULL DEFAULT '[]'::jsonb,
    audiences      JSONB NOT NULL DEFAULT '[]'::jsonb,   -- default aud array for this client's tokens
    created_at     TIMESTAMP DEFAULT NOW()
);

-- ─── OAuth access tokens ────────────────────────────────────────────────────
-- The JWT itself lives with the client; this table keeps only the jti, so a
-- resource server can check whether it has been revoked.

CREATE TABLE IF NOT EXISTS oauth_access_tokens (
    jti        TEXT PRIMARY KEY,                  -- uuid; the same value as the JWT's jti claim
    client_id  TEXT NOT NULL,
    user_id    INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    tenant_id  TEXT NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    scope      TEXT NOT NULL DEFAULT '',
    audiences  JSONB NOT NULL DEFAULT '[]'::jsonb,
    expires_at TIMESTAMP NOT NULL,
    revoked    BOOLEAN NOT NULL DEFAULT FALSE,
    created_at TIMESTAMP DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_oauth_access_user ON oauth_access_tokens(user_id);
CREATE INDEX IF NOT EXISTS idx_oauth_access_expires ON oauth_access_tokens(expires_at);

-- ─── OAuth refresh tokens ───────────────────────────────────────────────────
-- Opaque random strings (gidr_xxx). Rotation marks the old one revoked=TRUE
-- and issues a replacement.

CREATE TABLE IF NOT EXISTS oauth_refresh_tokens (
    refresh_token TEXT PRIMARY KEY,
    access_jti    TEXT NOT NULL,                  -- jti of the access token currently paired with it
    client_id     TEXT NOT NULL,
    user_id       INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    tenant_id     TEXT NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    scope         TEXT NOT NULL DEFAULT '',
    audiences     JSONB NOT NULL DEFAULT '[]'::jsonb,
    expires_at    TIMESTAMP,
    revoked       BOOLEAN NOT NULL DEFAULT FALSE,
    created_at    TIMESTAMP DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_oauth_refresh_access ON oauth_refresh_tokens(access_jti);
CREATE INDEX IF NOT EXISTS idx_oauth_refresh_user ON oauth_refresh_tokens(user_id);

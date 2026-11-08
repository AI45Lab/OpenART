-- Databricks Sandbox — OAuth2 control-plane schema (PostgreSQL).
--
-- This file is mounted at docker-entrypoint-initdb.d and runs ONCE when the
-- Postgres data volume is first created. It owns ONLY the control plane:
--   * `tenants`  — the tenant registry
--   * `users`    — synthetic identities (databricks has no native identity;
--                  these exist purely so the env is a standard OAuth2 AS)
--   * `oauth_*`  — the OAuth2 Authorization Server tables
-- all in the `public` schema.
--
-- The data warehouse (products / revenue / orders / customers / inventory /
-- reviews / tags / ...) is NOT here. databricks-dbsql-exec runs arbitrary
-- agent SQL, so each tenant gets its own Postgres SCHEMA `tenant_<id>` that
-- the env API creates at init-tenant time from api/warehouse/{schema,seed}.sql
-- and fences with a per-tenant low-privilege role. See api/main.py.

-- ─── Tenancy ──────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS tenants(
  id         TEXT PRIMARY KEY,
  name       TEXT NOT NULL DEFAULT '',
  status     TEXT NOT NULL DEFAULT 'active',
  created_at TIMESTAMP DEFAULT NOW()
);

-- ─── Identity (synthetic — only so the env is a standard OAuth2 AS) ────
-- Rows are created only by the admin-only POST /auth/register.
CREATE TABLE IF NOT EXISTS users(
  id            SERIAL PRIMARY KEY,
  tenant_id     TEXT NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
  email         TEXT NOT NULL,
  username      TEXT NOT NULL,
  name          TEXT,
  password_hash TEXT,
  created_at    TIMESTAMP DEFAULT NOW(),
  UNIQUE(email, tenant_id),
  UNIQUE(username, tenant_id)
);

-- ─── OAuth2 Authorization Server (env-oauth-blueprint) ────────────────
CREATE TABLE IF NOT EXISTS oauth_clients(
  client_id                  TEXT PRIMARY KEY,
  client_secret              TEXT,
  client_name                TEXT NOT NULL DEFAULT '',
  redirect_uris              TEXT NOT NULL DEFAULT '[]',
  grant_types                TEXT NOT NULL DEFAULT '["authorization_code"]',
  response_types             TEXT NOT NULL DEFAULT '["code"]',
  scope                      TEXT NOT NULL DEFAULT '',
  token_endpoint_auth_method TEXT NOT NULL DEFAULT 'none',
  created_at                 TIMESTAMP DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS oauth_authorization_codes(
  code                  TEXT PRIMARY KEY,
  client_id             TEXT NOT NULL,
  user_id               INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  redirect_uri          TEXT NOT NULL,
  scope                 TEXT NOT NULL DEFAULT '',
  code_challenge        TEXT,
  code_challenge_method TEXT,
  resource              TEXT,
  expires_at            TIMESTAMP NOT NULL,
  used                  BOOLEAN NOT NULL DEFAULT FALSE,
  created_at            TIMESTAMP DEFAULT NOW()
);

-- ─── Indexes ──────────────────────────────────────────────────────────
CREATE INDEX IF NOT EXISTS idx_users_tenant ON users(tenant_id);
CREATE INDEX IF NOT EXISTS idx_oauth_codes_client_id ON oauth_authorization_codes(client_id);
CREATE INDEX IF NOT EXISTS idx_oauth_codes_expires ON oauth_authorization_codes(expires_at);

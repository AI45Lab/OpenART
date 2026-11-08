-- Phase 2: authorization_code flow + consent reuse
--
-- Adds:
--   - oauth_authorization_codes  (short-TTL codes issued by /oauth/authorize)
--   - oauth_consents             (remember what a user granted to a client)
-- Idempotent.

CREATE TABLE IF NOT EXISTS oauth_authorization_codes (
    code                  TEXT PRIMARY KEY,
    client_id             TEXT NOT NULL REFERENCES oauth_clients(client_id) ON DELETE CASCADE,
    user_id               INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    tenant_id             TEXT NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    redirect_uri          TEXT NOT NULL,
    scope                 TEXT NOT NULL DEFAULT '',
    audiences             JSONB NOT NULL DEFAULT '[]'::jsonb,
    code_challenge        TEXT NOT NULL,
    code_challenge_method TEXT NOT NULL DEFAULT 'S256',
    expires_at            TIMESTAMP NOT NULL,
    used                  BOOLEAN NOT NULL DEFAULT FALSE,
    created_at            TIMESTAMP DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_oauth_authcode_expires ON oauth_authorization_codes(expires_at);

-- Remember which scopes a user has granted to a client.
-- Composite PK: (user_id, client_id, tenant_id) — one row per triple.
-- Re-authorizing with scope ⊆ stored skips the consent page.

CREATE TABLE IF NOT EXISTS oauth_consents (
    user_id    INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    client_id  TEXT    NOT NULL REFERENCES oauth_clients(client_id) ON DELETE CASCADE,
    tenant_id  TEXT    NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    scopes     TEXT    NOT NULL DEFAULT '',
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW(),
    PRIMARY KEY (user_id, client_id, tenant_id)
);

CREATE INDEX IF NOT EXISTS idx_oauth_consents_user ON oauth_consents(user_id);

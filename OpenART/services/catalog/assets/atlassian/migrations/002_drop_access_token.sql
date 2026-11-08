-- Migration: drop the `app_user.access_token` anti-pattern column and add
-- the OAuth2 AS support tables (oauth_clients, oauth_authorization_codes).
--
-- env-oauth-blueprint: per-user opaque bearer tokens stored on the users
-- row prevent rotation, multi-session, and per-token revocation. JWTs are
-- stateless — the AS issues them, the RS verifies them via JWKS, no DB
-- lookup per request.
--
-- Idempotent: safe to re-run on DBs that have already been migrated.

DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM information_schema.columns
               WHERE table_name = 'app_user' AND column_name = 'access_token') THEN
        -- The original registration endpoint stored passwords as supplied.
        -- Convert them once, while the old column identifies this schema.
        -- The original seed's placeholder means the sandbox default password.
        UPDATE app_user SET password_hash = encode(sha256(convert_to(
            (CASE WHEN password_hash = 'hashed-password' THEN 'password' ELSE password_hash END)
            || 'atlassian_sandbox_salt_2024', 'UTF8')), 'hex');
    END IF;
END $$;
DROP INDEX IF EXISTS idx_app_user_access_token;
ALTER TABLE app_user DROP COLUMN IF EXISTS access_token;

CREATE TABLE IF NOT EXISTS oauth_clients (
    client_id TEXT PRIMARY KEY,
    client_secret TEXT,
    client_name TEXT NOT NULL DEFAULT '',
    redirect_uris JSONB NOT NULL DEFAULT '[]'::jsonb,
    grant_types JSONB NOT NULL DEFAULT '["authorization_code"]'::jsonb,
    response_types JSONB NOT NULL DEFAULT '["code"]'::jsonb,
    scope TEXT NOT NULL DEFAULT '',
    token_endpoint_auth_method TEXT NOT NULL DEFAULT 'none',
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS oauth_authorization_codes (
    code TEXT PRIMARY KEY,
    client_id TEXT NOT NULL,
    user_id UUID NOT NULL REFERENCES app_user(id) ON DELETE CASCADE,
    redirect_uri TEXT NOT NULL,
    scope TEXT NOT NULL DEFAULT '',
    code_challenge TEXT,
    code_challenge_method TEXT,
    resource TEXT,
    expires_at TIMESTAMPTZ NOT NULL,
    used BOOLEAN NOT NULL DEFAULT false,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_oauth_codes_client_id ON oauth_authorization_codes (client_id);
CREATE INDEX IF NOT EXISTS idx_oauth_codes_expires ON oauth_authorization_codes (expires_at);

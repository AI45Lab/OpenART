-- Slack Sandbox Database Schema
-- Multi-tenant: tenant_id column on users + tenants table.
-- OAuth2 AS state (clients, authorization codes) is tenant-agnostic.

CREATE TABLE IF NOT EXISTS tenants (
    id          TEXT PRIMARY KEY,
    name        TEXT NOT NULL DEFAULT '',
    status      TEXT NOT NULL DEFAULT 'active',
    created_at  TIMESTAMP DEFAULT NOW()
);

INSERT INTO tenants (id, name) VALUES ('default', 'Default Tenant')
    ON CONFLICT (id) DO NOTHING;

CREATE TABLE IF NOT EXISTS users (
    id              SERIAL PRIMARY KEY,
    email           TEXT NOT NULL,
    tenant_id       TEXT NOT NULL DEFAULT 'default' REFERENCES tenants(id) ON DELETE CASCADE,
    name            TEXT NOT NULL,
    password_hash   TEXT NOT NULL,
    created_at      TIMESTAMP DEFAULT NOW(),
    UNIQUE (email, tenant_id),
    UNIQUE (tenant_id, id)
);

CREATE UNIQUE INDEX IF NOT EXISTS idx_users_email_tenant_id ON users(email, tenant_id);

CREATE TABLE IF NOT EXISTS oauth_clients (
    client_id                   TEXT PRIMARY KEY,
    client_secret               TEXT,
    client_name                 TEXT NOT NULL DEFAULT '',
    redirect_uris               TEXT NOT NULL DEFAULT '[]',
    grant_types                 TEXT NOT NULL DEFAULT '["authorization_code"]',
    response_types              TEXT NOT NULL DEFAULT '["code"]',
    scope                       TEXT NOT NULL DEFAULT '',
    token_endpoint_auth_method  TEXT NOT NULL DEFAULT 'none',
    created_at                  TIMESTAMP DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS oauth_authorization_codes (
    code                    TEXT PRIMARY KEY,
    client_id               TEXT NOT NULL,
    tenant_id               TEXT NOT NULL DEFAULT 'default' REFERENCES tenants(id) ON DELETE CASCADE,
    user_id                 INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    redirect_uri            TEXT NOT NULL,
    scope                   TEXT NOT NULL DEFAULT '',
    code_challenge          TEXT,
    code_challenge_method   TEXT,
    resource                TEXT,
    expires_at              TIMESTAMP NOT NULL,
    used                    BOOLEAN NOT NULL DEFAULT FALSE,
    created_at              TIMESTAMP DEFAULT NOW(),
    CONSTRAINT fk_oauth_codes_tenant_user
        FOREIGN KEY (tenant_id, user_id) REFERENCES users(tenant_id, id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_oauth_codes_client_id ON oauth_authorization_codes(client_id);

-- ─── Business state (was TenantStore, a per-process dict) ─────────────
-- Judge-visible: 994 judges across five domains read this back, and for crm
-- and legal it is the channel the task instruction itself arrives on.  A dict
-- dies with the worker, which is why a 46h-old container can hold 12 tenants
-- in `users` while every one of their workspaces is gone.
--
-- Ordering columns are load-bearing, not cosmetic:
--   * messages was a List and its position is what channels.history returns;
--   * channel_members[c][0] picks "the first member" as a seed sender;
--   * a DM is looked up by tuple(sorted(members)) == key, so conversation
--     membership order is the lookup key.
-- Hence `pos` on both membership tables and BIGSERIAL on messages.
--
-- NOT ported: TenantStore.pins.  It is written by nothing and read by nothing
-- in the whole repo — only __init__ and clear() mention it.

CREATE TABLE IF NOT EXISTS slack_workspaces (
    position   BIGSERIAL,
    tenant_id  TEXT NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    id         TEXT NOT NULL,
    name       TEXT NOT NULL,
    PRIMARY KEY (tenant_id, id)
);

CREATE TABLE IF NOT EXISTS slack_channels (
    position   BIGSERIAL,
    tenant_id    TEXT NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    id           TEXT NOT NULL,
    name         TEXT NOT NULL,
    is_private   BOOLEAN NOT NULL DEFAULT FALSE,
    workspace_id TEXT NOT NULL,
    PRIMARY KEY (tenant_id, id)
);

CREATE TABLE IF NOT EXISTS slack_workspace_members (
    tenant_id    TEXT NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    workspace_id TEXT NOT NULL,
    email        TEXT NOT NULL,
    pos          INTEGER NOT NULL DEFAULT 0,
    PRIMARY KEY (tenant_id, workspace_id, email)
);

CREATE TABLE IF NOT EXISTS slack_channel_members (
    tenant_id  TEXT NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    channel_id TEXT NOT NULL,
    email      TEXT NOT NULL,
    pos        INTEGER NOT NULL DEFAULT 0,
    PRIMARY KEY (tenant_id, channel_id, email)
);

CREATE TABLE IF NOT EXISTS slack_conversations (
    position   BIGSERIAL,
    tenant_id    TEXT NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    id           TEXT NOT NULL,
    workspace_id TEXT NOT NULL,
    is_group     BOOLEAN NOT NULL DEFAULT FALSE,
    PRIMARY KEY (tenant_id, id)
);

CREATE TABLE IF NOT EXISTS slack_conversation_members (
    tenant_id       TEXT NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    conversation_id TEXT NOT NULL,
    email           TEXT NOT NULL,
    pos             INTEGER NOT NULL DEFAULT 0,
    PRIMARY KEY (tenant_id, conversation_id, email)
);

CREATE TABLE IF NOT EXISTS slack_messages (
    -- BIGSERIAL, not ts: the semantics being replaced are list-append order and
    -- ts is a float that repeats within a millisecond.
    seq        BIGSERIAL PRIMARY KEY,
    tenant_id  TEXT NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    id         TEXT NOT NULL,
    channel    TEXT NOT NULL,
    user_email TEXT NOT NULL,
    text       TEXT NOT NULL DEFAULT '',
    ts         DOUBLE PRECISION NOT NULL,
    thread_ts  DOUBLE PRECISION
);

CREATE INDEX IF NOT EXISTS idx_slack_ws_members   ON slack_workspace_members(tenant_id, workspace_id, pos);
CREATE INDEX IF NOT EXISTS idx_slack_ch_members   ON slack_channel_members(tenant_id, channel_id, pos);
CREATE INDEX IF NOT EXISTS idx_slack_conv_members ON slack_conversation_members(tenant_id, conversation_id, pos);
CREATE INDEX IF NOT EXISTS idx_slack_channels_ws  ON slack_channels(tenant_id, workspace_id);
CREATE INDEX IF NOT EXISTS idx_slack_messages_ch  ON slack_messages(tenant_id, channel, seq);
CREATE INDEX IF NOT EXISTS idx_slack_messages_t   ON slack_messages(tenant_id, seq);

-- Native Slack-app (Socket Mode) credentials: a bot's xoxb/xapp tokens, bound
-- to an existing account (tenant_id + email). Lets self-hosted frameworks
-- (OpenClaw, Hermes) connect as Slack bots. slack_socket.py creates this lazily
-- too, so an already-running container is upgraded without a migration.
CREATE TABLE IF NOT EXISTS slack_bot_tokens (
    token      TEXT PRIMARY KEY,
    tenant_id  TEXT NOT NULL,
    email      TEXT NOT NULL,
    kind       TEXT NOT NULL,           -- 'bot' (xoxb-) or 'app' (xapp-)
    -- Tokens die with their account, so reset and tenant deletion revoke them.
    CONSTRAINT slack_bot_tokens_account FOREIGN KEY (email, tenant_id)
        REFERENCES users (email, tenant_id) ON DELETE CASCADE
);
CREATE INDEX IF NOT EXISTS slack_bot_tokens_principal ON slack_bot_tokens(tenant_id, email, kind);

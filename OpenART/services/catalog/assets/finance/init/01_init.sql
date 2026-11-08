-- Finance Sandbox Schema — multi-tenant.
--
-- Two groups of tables:
--
--   Identity      tenants and their users for the embedded AS
--                 (server/oauth_as.py): /auth/register (admin token) stores a
--                 scrypt password hash, /auth/login verifies it and mints a
--                 tenant-scoped JWT. Tenants exist only once the env server
--                 creates them; there is no built-in tenant.
--
--   Business      the per-tenant state that used to live on the Flask app
--                 object: portfolios, the action log, article comments, and the
--                 injection engine's rules and fabricated content.
--
-- Everything is keyed by tenant_id and cascades from `tenants`, so
-- DELETE FROM tenants WHERE id = ... tears a task down completely.
--
-- NOTE: Postgres runs this file only when PGDATA is empty, and finance_pgdata
-- is a persistent volume. A table added here will never appear on a pool that
-- has already booted. server/web.py::_ensure_state_schema re-applies the
-- business DDL on every boot for exactly that reason, and RAISES if it cannot.

-- ─── Tenancy ──────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS tenants (
    id         TEXT PRIMARY KEY,
    name       TEXT NOT NULL DEFAULT '',
    status     TEXT NOT NULL DEFAULT 'active',
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- ─── Identity ─────────────────────────────────────────────────────────
-- email is stored lowercased. A NULL password_hash is a user that cannot log in.
CREATE TABLE IF NOT EXISTS users (
    id            SERIAL PRIMARY KEY,
    tenant_id     TEXT NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    email         TEXT NOT NULL,
    name          TEXT,
    password_hash TEXT,
    created_at    TIMESTAMP DEFAULT NOW(),
    UNIQUE (email, tenant_id)
);

-- ─── OAuth2 Authorization Server ──────────────────────────────────────
CREATE TABLE IF NOT EXISTS oauth_clients (
    client_id TEXT PRIMARY KEY,
    client_secret TEXT,
    client_name TEXT NOT NULL DEFAULT '',
    redirect_uris TEXT NOT NULL DEFAULT '[]',
    grant_types TEXT NOT NULL DEFAULT '["authorization_code"]',
    response_types TEXT NOT NULL DEFAULT '["code"]',
    scope TEXT NOT NULL DEFAULT '',
    token_endpoint_auth_method TEXT NOT NULL DEFAULT 'none',
    created_at TIMESTAMP DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS oauth_authorization_codes (
    code TEXT PRIMARY KEY,
    client_id TEXT NOT NULL,
    tenant_id TEXT NOT NULL DEFAULT 'default',
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    redirect_uri TEXT NOT NULL,
    scope TEXT NOT NULL DEFAULT '',
    code_challenge TEXT,
    code_challenge_method TEXT,
    resource TEXT,
    expires_at TIMESTAMP NOT NULL,
    used BOOLEAN NOT NULL DEFAULT FALSE,
    created_at TIMESTAMP DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_users_tenant ON users(tenant_id);
CREATE INDEX IF NOT EXISTS idx_oauth_codes_client_id ON oauth_authorization_codes(client_id);

-- Tenant ownership applies to authorization codes as well as their users.
-- Backfill before setting a default so existing non-default users keep ownership.
ALTER TABLE oauth_authorization_codes ADD COLUMN IF NOT EXISTS tenant_id TEXT;
UPDATE oauth_authorization_codes c SET tenant_id = u.tenant_id
    FROM users u WHERE c.user_id = u.id AND c.tenant_id IS NULL;
ALTER TABLE oauth_authorization_codes ALTER COLUMN tenant_id SET NOT NULL;
ALTER TABLE oauth_authorization_codes ALTER COLUMN tenant_id SET DEFAULT 'default';
CREATE UNIQUE INDEX IF NOT EXISTS idx_fin_users_tenant_id ON users(tenant_id, id);
DO $$ BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_constraint
        WHERE conrelid = 'oauth_authorization_codes'::regclass
          AND conname = 'fk_fin_oauth_codes_tenant') THEN
        ALTER TABLE oauth_authorization_codes ADD CONSTRAINT fk_fin_oauth_codes_tenant
            FOREIGN KEY (tenant_id) REFERENCES tenants(id) ON DELETE CASCADE;
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_constraint
        WHERE conrelid = 'oauth_authorization_codes'::regclass
          AND conname = 'fk_fin_oauth_codes_tenant_user') THEN
        ALTER TABLE oauth_authorization_codes ADD CONSTRAINT fk_fin_oauth_codes_tenant_user
            FOREIGN KEY (tenant_id, user_id) REFERENCES users(tenant_id, id) ON DELETE CASCADE;
    END IF;
END $$;
CREATE INDEX IF NOT EXISTS idx_fin_oauth_codes_tenant ON oauth_authorization_codes(tenant_id);

-- ─── Business state ───────────────────────────────────────────────────
-- Kept in sync with server/web.py::_STATE_DDL, which re-applies these on every
-- boot. Change one, change the other.

-- One row per (tenant, account). `state` is PortfolioManager._state verbatim:
-- cash / positions / transactions / pending_orders / cancelled_orders /
-- created_at / updated_at, plus `options` once an option is bought (it is
-- setdefault-ed lazily, so readers must tolerate its absence). Every value is
-- JSON-native — timestamps are already .isoformat() strings — so it round-trips
-- unchanged.
--
-- `json`, not `jsonb`: jsonb normalises object key order, and `positions` renders
-- in insertion order, so jsonb silently re-sorts the holdings table on every page
-- that lists it. Nothing queries inside these blobs, so there is no reason to pay
-- jsonb's normalisation. Same for every other JSON column below.
--
-- `position` preserves the order of _account_names, which /api/accounts and the
-- account switcher surface to the agent. `is_active` marks _active_account.
CREATE TABLE IF NOT EXISTS finance_portfolios (
    tenant_id  TEXT NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    account    TEXT NOT NULL,
    position   INTEGER NOT NULL DEFAULT 0,
    is_active  BOOLEAN NOT NULL DEFAULT FALSE,
    state      JSON  NOT NULL DEFAULT '{}'::json,
    PRIMARY KEY (tenant_id, account)
);

-- Append-only agent trace, written only by the backend from the requests it
-- served (server/action_log.py); no route appends to it. BIGSERIAL rather than
-- a timestamp because the env runs on a frozen clock (web.py's SIMULATED_DATE).
CREATE TABLE IF NOT EXISTS finance_action_log (
    id        BIGSERIAL PRIMARY KEY,
    tenant_id TEXT NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    entry     JSON  NOT NULL
);

-- Comments the agent posts on articles. article_key is web.py's "SYMBOL_id".
-- Ordered by id: comment ids are minted from the frozen clock and collide, so
-- they cannot order anything.
CREATE TABLE IF NOT EXISTS finance_comments (
    id          BIGSERIAL PRIMARY KEY,
    tenant_id   TEXT NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    article_key TEXT NOT NULL,
    comment     JSON  NOT NULL
);

-- HtmlInjector.config.rules — the indirect-attack lures. `position` keeps
-- insertion order, which decides which rule wins when several match a page.
--
-- Deliberately NO primary key on (tenant_id, rule_id): rule_id is not unique
-- within a tenant. /api/injection/custom derives it from hash(prompt), so
-- injecting the same lure twice collides, and the config path defaults every
-- rule to the literal "custom". `position` carries the identity that matters.
CREATE TABLE IF NOT EXISTS finance_injection_rules (
    tenant_id TEXT NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    rule_id   TEXT NOT NULL,
    position  INTEGER NOT NULL DEFAULT 0,
    rule      JSON  NOT NULL
);

-- ContentInjector's fabricated material and delivery history: kind is one of
-- news / comments / analyst_ratings / modifications / enabled / delivery_log /
-- engine_config / engine_runtime / news_metadata. Rendering persists events and HTML
-- injection counters so the original readback APIs survive request boundaries.
-- `key` is the symbol or article key the item is filed under ('' when the kind
-- is a flat list), `position` its index within that key.
CREATE TABLE IF NOT EXISTS finance_injected_content (
    id        BIGSERIAL PRIMARY KEY,
    tenant_id TEXT NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    kind      TEXT NOT NULL,
    key       TEXT NOT NULL DEFAULT '',
    position  INTEGER NOT NULL DEFAULT 0,
    payload   JSON  NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_fin_portfolios_tenant  ON finance_portfolios(tenant_id);
CREATE INDEX IF NOT EXISTS idx_fin_action_log_tenant  ON finance_action_log(tenant_id, id);
CREATE INDEX IF NOT EXISTS idx_fin_comments_tenant    ON finance_comments(tenant_id, article_key, id);
CREATE INDEX IF NOT EXISTS idx_fin_rules_tenant       ON finance_injection_rules(tenant_id, position);
CREATE INDEX IF NOT EXISTS idx_fin_content_tenant     ON finance_injected_content(tenant_id, kind, key, position);

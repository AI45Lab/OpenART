-- Telegram Sandbox Database Schema (multi-tenant)

CREATE TABLE IF NOT EXISTS tenants (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL DEFAULT '',
    status TEXT NOT NULL DEFAULT 'active',
    created_at TIMESTAMP DEFAULT NOW()
);

INSERT INTO tenants (id, name) VALUES ('default', 'Default Tenant')
    ON CONFLICT (id) DO NOTHING;

-- No `access_token` / `token_expires_at` columns and no plaintext password:
-- users authenticate only with the signed login JWT (expiry is its `exp`
-- claim), and only the salted password hash is stored.
CREATE TABLE IF NOT EXISTS users (
    id SERIAL PRIMARY KEY,
    email TEXT NOT NULL,
    tenant_id TEXT NOT NULL DEFAULT 'default' REFERENCES tenants(id) ON DELETE CASCADE,
    name TEXT NOT NULL,
    password_hash TEXT NOT NULL,
    phone TEXT,
    created_at TIMESTAMP DEFAULT NOW(),
    UNIQUE(email, tenant_id)
);

-- OAuth2 clients (RFC 7591 Dynamic Client Registration).
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

-- OAuth2 authorization codes (short-lived, single-use; PKCE-bound).
CREATE TABLE IF NOT EXISTS oauth_authorization_codes (
    code TEXT PRIMARY KEY,
    client_id TEXT NOT NULL,
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
CREATE INDEX IF NOT EXISTS idx_oauth_codes_client_id ON oauth_authorization_codes (client_id);
CREATE INDEX IF NOT EXISTS idx_oauth_codes_expires ON oauth_authorization_codes (expires_at);

CREATE TABLE IF NOT EXISTS contacts (
    id TEXT PRIMARY KEY,
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    first_name TEXT NOT NULL,
    last_name TEXT,
    email TEXT,
    phone TEXT,
    company TEXT,
    job_title TEXT,
    address TEXT,
    notes TEXT,
    favorite BOOLEAN DEFAULT FALSE,
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS messages (
    id TEXT PRIMARY KEY,
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    contact_id TEXT,
    phone_number TEXT NOT NULL,
    direction TEXT NOT NULL,
    body TEXT NOT NULL,
    media_url TEXT,
    message_type TEXT NOT NULL DEFAULT 'text',
    status TEXT NOT NULL DEFAULT 'sent',
    is_read BOOLEAN DEFAULT FALSE,
    thread_id TEXT,
    reply_to_id TEXT,
    created_at TIMESTAMP DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS message_threads (
    id TEXT PRIMARY KEY,
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    phone_number TEXT NOT NULL,
    contact_id TEXT,
    last_message_at TIMESTAMP,
    unread_count INTEGER DEFAULT 0,
    created_at TIMESTAMP DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS calls (
    id TEXT PRIMARY KEY,
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    contact_id TEXT,
    phone_number TEXT NOT NULL,
    direction TEXT NOT NULL DEFAULT 'outgoing',
    status TEXT NOT NULL DEFAULT 'completed',
    duration INTEGER DEFAULT 0,
    started_at TIMESTAMP DEFAULT NOW(),
    ended_at TIMESTAMP,
    created_at TIMESTAMP DEFAULT NOW()
);

-- Groups and channels. Neither is owned by a single user, so unlike
-- contacts/messages/threads/calls they cannot inherit isolation transitively
-- through user_id -> users.tenant_id; both carry tenant_id directly.
--
-- Membership keys on `phone`, not the `username` main used: this schema has no
-- users.username column (dropped with access_token when tokens went stateless),
-- and phone is the identifier the rest of this env already addresses people by.
--
-- `id` is a server-minted surrogate and `ext_id` is the id a fixture declared —
-- two tenants seeded from the same file would otherwise collide on a shared
-- primary key. Per-tenant uniqueness on the natural keys is the pattern
-- instagram (UNIQUE(tenant_id, username)) and atlassian already use.
--
-- Prefixed tg_ rather than main's bare `groups`/`channels`: GROUPS is a
-- reserved word in SQL:2011 window frames, and the prefix matches whatsapp's
-- wa_ tables next door.
CREATE TABLE IF NOT EXISTS tg_groups (
    id TEXT PRIMARY KEY,
    tenant_id TEXT NOT NULL DEFAULT 'default' REFERENCES tenants(id) ON DELETE CASCADE,
    ext_id TEXT,
    name TEXT NOT NULL,
    description TEXT,
    admin_phone TEXT,
    created_at TIMESTAMP DEFAULT NOW(),
    UNIQUE (tenant_id, name),
    UNIQUE (tenant_id, ext_id)
);

CREATE TABLE IF NOT EXISTS tg_group_members (
    group_id TEXT NOT NULL REFERENCES tg_groups(id) ON DELETE CASCADE,
    phone TEXT NOT NULL,
    PRIMARY KEY (group_id, phone)
);

CREATE TABLE IF NOT EXISTS tg_group_messages (
    id TEXT PRIMARY KEY,
    group_id TEXT NOT NULL REFERENCES tg_groups(id) ON DELETE CASCADE,
    from_phone TEXT,
    user_id INTEGER REFERENCES users(id) ON DELETE SET NULL,
    body TEXT NOT NULL,
    media_url TEXT,
    message_type TEXT NOT NULL DEFAULT 'text',
    created_at TIMESTAMP DEFAULT NOW()
);

-- A channel is a broadcast surface: subscribers read, an admin posts. That
-- asymmetry is what makes it the cleanest indirect-injection carrier in the
-- suite, and whatsapp has no equivalent.
CREATE TABLE IF NOT EXISTS tg_channels (
    id TEXT PRIMARY KEY,
    tenant_id TEXT NOT NULL DEFAULT 'default' REFERENCES tenants(id) ON DELETE CASCADE,
    ext_id TEXT,
    name TEXT NOT NULL,
    description TEXT,
    admin_phone TEXT,
    created_at TIMESTAMP DEFAULT NOW(),
    UNIQUE (tenant_id, name),
    UNIQUE (tenant_id, ext_id)
);

CREATE TABLE IF NOT EXISTS tg_channel_members (
    channel_id TEXT NOT NULL REFERENCES tg_channels(id) ON DELETE CASCADE,
    phone TEXT NOT NULL,
    PRIMARY KEY (channel_id, phone)
);

CREATE TABLE IF NOT EXISTS tg_channel_messages (
    id TEXT PRIMARY KEY,
    channel_id TEXT NOT NULL REFERENCES tg_channels(id) ON DELETE CASCADE,
    from_phone TEXT,
    user_id INTEGER REFERENCES users(id) ON DELETE SET NULL,
    body TEXT NOT NULL,
    media_url TEXT,
    message_type TEXT NOT NULL DEFAULT 'text',
    created_at TIMESTAMP DEFAULT NOW()
);

-- Indexes
CREATE INDEX IF NOT EXISTS idx_users_tenant_id ON users(tenant_id);
CREATE INDEX IF NOT EXISTS idx_contacts_user ON contacts(user_id);
CREATE INDEX IF NOT EXISTS idx_messages_user_phone ON messages(user_id, phone_number);
CREATE INDEX IF NOT EXISTS idx_messages_thread ON messages(thread_id);
CREATE INDEX IF NOT EXISTS idx_threads_user ON message_threads(user_id);
CREATE INDEX IF NOT EXISTS idx_calls_user ON calls(user_id);
CREATE INDEX IF NOT EXISTS idx_tg_groups_tenant ON tg_groups(tenant_id);
CREATE INDEX IF NOT EXISTS idx_tg_group_members_phone ON tg_group_members(phone);
CREATE INDEX IF NOT EXISTS idx_tg_group_messages_group ON tg_group_messages(group_id, created_at);
CREATE INDEX IF NOT EXISTS idx_tg_channels_tenant ON tg_channels(tenant_id);
CREATE INDEX IF NOT EXISTS idx_tg_channel_members_phone ON tg_channel_members(phone);
CREATE INDEX IF NOT EXISTS idx_tg_channel_messages_channel ON tg_channel_messages(channel_id, created_at);

ALTER TABLE users ADD COLUMN IF NOT EXISTS username TEXT;


-- Child rows carry the same explicit tenant boundary as their parents.
CREATE OR REPLACE FUNCTION enforce_row_tenant() RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE
    i integer;
    parent_tenant text;
    derived_tenant text;
    parent_id text;
BEGIN
    FOR i IN 0..TG_NARGS-1 BY 2 LOOP
        parent_id := to_jsonb(NEW)->>TG_ARGV[i+1];
        IF parent_id IS NULL THEN CONTINUE; END IF;
        EXECUTE format('SELECT tenant_id FROM %I.%I WHERE id::text=$1 FOR KEY SHARE', TG_TABLE_SCHEMA, TG_ARGV[i]) INTO parent_tenant USING parent_id;
        IF parent_tenant IS NULL THEN
            -- Original loose contact/thread references may be absent.
            -- Existing foreign parents still fail the ownership check below.
            IF TG_ARGV[i] IN ('users','tg_groups','tg_channels') THEN
                RAISE EXCEPTION 'Missing parent for %.%', TG_TABLE_NAME, TG_ARGV[i+1] USING ERRCODE='23503';
            END IF;
            CONTINUE;
        END IF;
        IF derived_tenant IS NOT NULL AND derived_tenant <> parent_tenant THEN
            RAISE EXCEPTION 'Cross-tenant reference in %', TG_TABLE_NAME USING ERRCODE='23514';
        END IF;
        derived_tenant := parent_tenant;
    END LOOP;
    IF NEW.tenant_id IS NOT NULL AND NEW.tenant_id <> derived_tenant THEN
        RAISE EXCEPTION 'Cross-tenant row in %', TG_TABLE_NAME USING ERRCODE='23514';
    END IF;
    NEW.tenant_id := COALESCE(NEW.tenant_id, derived_tenant);
    RETURN NEW;
END;
$$;
ALTER TABLE users ADD COLUMN IF NOT EXISTS username TEXT;

ALTER TABLE contacts ADD COLUMN IF NOT EXISTS tenant_id TEXT REFERENCES tenants(id) ON DELETE CASCADE;
ALTER TABLE message_threads ADD COLUMN IF NOT EXISTS tenant_id TEXT REFERENCES tenants(id) ON DELETE CASCADE;
ALTER TABLE messages ADD COLUMN IF NOT EXISTS tenant_id TEXT REFERENCES tenants(id) ON DELETE CASCADE;
ALTER TABLE calls ADD COLUMN IF NOT EXISTS tenant_id TEXT REFERENCES tenants(id) ON DELETE CASCADE;
ALTER TABLE tg_group_members ADD COLUMN IF NOT EXISTS tenant_id TEXT REFERENCES tenants(id) ON DELETE CASCADE;
ALTER TABLE tg_group_messages ADD COLUMN IF NOT EXISTS tenant_id TEXT REFERENCES tenants(id) ON DELETE CASCADE;
ALTER TABLE tg_channel_members ADD COLUMN IF NOT EXISTS tenant_id TEXT REFERENCES tenants(id) ON DELETE CASCADE;
ALTER TABLE tg_channel_messages ADD COLUMN IF NOT EXISTS tenant_id TEXT REFERENCES tenants(id) ON DELETE CASCADE;
UPDATE contacts c SET tenant_id=p.tenant_id FROM users p WHERE c.user_id=p.id AND c.tenant_id IS NULL;
UPDATE message_threads c SET tenant_id=p.tenant_id FROM users p WHERE c.user_id=p.id AND c.tenant_id IS NULL;
UPDATE messages c SET tenant_id=p.tenant_id FROM users p WHERE c.user_id=p.id AND c.tenant_id IS NULL;
UPDATE calls c SET tenant_id=p.tenant_id FROM users p WHERE c.user_id=p.id AND c.tenant_id IS NULL;
UPDATE tg_group_members c SET tenant_id=p.tenant_id FROM tg_groups p WHERE c.group_id=p.id AND c.tenant_id IS NULL;
UPDATE tg_group_messages c SET tenant_id=p.tenant_id FROM tg_groups p WHERE c.group_id=p.id AND c.tenant_id IS NULL;
UPDATE tg_channel_members c SET tenant_id=p.tenant_id FROM tg_channels p WHERE c.channel_id=p.id AND c.tenant_id IS NULL;
UPDATE tg_channel_messages c SET tenant_id=p.tenant_id FROM tg_channels p WHERE c.channel_id=p.id AND c.tenant_id IS NULL;
DROP TRIGGER IF EXISTS contacts_tenant_guard ON contacts;
CREATE TRIGGER contacts_tenant_guard BEFORE INSERT OR UPDATE ON contacts FOR EACH ROW EXECUTE FUNCTION enforce_row_tenant('users','user_id');
UPDATE contacts SET tenant_id=tenant_id;
ALTER TABLE contacts ALTER COLUMN tenant_id SET NOT NULL;
CREATE INDEX IF NOT EXISTS idx_contacts_tenant ON contacts(tenant_id);
DROP TRIGGER IF EXISTS message_threads_tenant_guard ON message_threads;
CREATE TRIGGER message_threads_tenant_guard BEFORE INSERT OR UPDATE ON message_threads FOR EACH ROW EXECUTE FUNCTION enforce_row_tenant('users','user_id','contacts','contact_id');
UPDATE message_threads SET tenant_id=tenant_id;
ALTER TABLE message_threads ALTER COLUMN tenant_id SET NOT NULL;
CREATE INDEX IF NOT EXISTS idx_message_threads_tenant ON message_threads(tenant_id);
DROP TRIGGER IF EXISTS messages_tenant_guard ON messages;
CREATE TRIGGER messages_tenant_guard BEFORE INSERT OR UPDATE ON messages FOR EACH ROW EXECUTE FUNCTION enforce_row_tenant('users','user_id','contacts','contact_id','message_threads','thread_id');
UPDATE messages SET tenant_id=tenant_id;
ALTER TABLE messages ALTER COLUMN tenant_id SET NOT NULL;
CREATE INDEX IF NOT EXISTS idx_messages_tenant ON messages(tenant_id);
DROP TRIGGER IF EXISTS calls_tenant_guard ON calls;
CREATE TRIGGER calls_tenant_guard BEFORE INSERT OR UPDATE ON calls FOR EACH ROW EXECUTE FUNCTION enforce_row_tenant('users','user_id','contacts','contact_id');
UPDATE calls SET tenant_id=tenant_id;
ALTER TABLE calls ALTER COLUMN tenant_id SET NOT NULL;
CREATE INDEX IF NOT EXISTS idx_calls_tenant ON calls(tenant_id);
DROP TRIGGER IF EXISTS tg_group_members_tenant_guard ON tg_group_members;
CREATE TRIGGER tg_group_members_tenant_guard BEFORE INSERT OR UPDATE ON tg_group_members FOR EACH ROW EXECUTE FUNCTION enforce_row_tenant('tg_groups','group_id');
UPDATE tg_group_members SET tenant_id=tenant_id;
ALTER TABLE tg_group_members ALTER COLUMN tenant_id SET NOT NULL;
CREATE INDEX IF NOT EXISTS idx_tg_group_members_tenant ON tg_group_members(tenant_id);
DROP TRIGGER IF EXISTS tg_group_messages_tenant_guard ON tg_group_messages;
CREATE TRIGGER tg_group_messages_tenant_guard BEFORE INSERT OR UPDATE ON tg_group_messages FOR EACH ROW EXECUTE FUNCTION enforce_row_tenant('tg_groups','group_id','users','user_id');
UPDATE tg_group_messages SET tenant_id=tenant_id;
ALTER TABLE tg_group_messages ALTER COLUMN tenant_id SET NOT NULL;
CREATE INDEX IF NOT EXISTS idx_tg_group_messages_tenant ON tg_group_messages(tenant_id);
DROP TRIGGER IF EXISTS tg_channel_members_tenant_guard ON tg_channel_members;
CREATE TRIGGER tg_channel_members_tenant_guard BEFORE INSERT OR UPDATE ON tg_channel_members FOR EACH ROW EXECUTE FUNCTION enforce_row_tenant('tg_channels','channel_id');
UPDATE tg_channel_members SET tenant_id=tenant_id;
ALTER TABLE tg_channel_members ALTER COLUMN tenant_id SET NOT NULL;
CREATE INDEX IF NOT EXISTS idx_tg_channel_members_tenant ON tg_channel_members(tenant_id);
DROP TRIGGER IF EXISTS tg_channel_messages_tenant_guard ON tg_channel_messages;
CREATE TRIGGER tg_channel_messages_tenant_guard BEFORE INSERT OR UPDATE ON tg_channel_messages FOR EACH ROW EXECUTE FUNCTION enforce_row_tenant('tg_channels','channel_id','users','user_id');
UPDATE tg_channel_messages SET tenant_id=tenant_id;
ALTER TABLE tg_channel_messages ALTER COLUMN tenant_id SET NOT NULL;
CREATE INDEX IF NOT EXISTS idx_tg_channel_messages_tenant ON tg_channel_messages(tenant_id);

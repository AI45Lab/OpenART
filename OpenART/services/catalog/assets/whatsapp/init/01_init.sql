-- WhatsApp Sandbox Database Schema (multi-tenant)

CREATE TABLE IF NOT EXISTS tenants (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL DEFAULT '',
    status TEXT NOT NULL DEFAULT 'active',
    created_at TIMESTAMP DEFAULT NOW()
);

INSERT INTO tenants (id, name) VALUES ('default', 'Default Tenant')
    ON CONFLICT (id) DO NOTHING;

-- No opaque `access_token` column and no plaintext password: users
-- authenticate only with the signed login JWT, and only the salted password
-- hash is stored.
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

CREATE TABLE IF NOT EXISTS call_history (
    id TEXT PRIMARY KEY,
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    contact_id TEXT REFERENCES contacts(id) ON DELETE SET NULL,
    phone_number TEXT NOT NULL,
    call_type TEXT NOT NULL DEFAULT 'voice',
    direction TEXT NOT NULL,
    duration INTEGER DEFAULT 0,
    status TEXT NOT NULL DEFAULT 'completed',
    started_at TIMESTAMP DEFAULT NOW(),
    ended_at TIMESTAMP,
    notes TEXT,
    created_at TIMESTAMP DEFAULT NOW()
);

-- Groups. Unlike contacts/messages/threads these are not owned by one user, so
-- they cannot inherit isolation transitively through user_id -> users.tenant_id
-- the way the other business tables do. They carry tenant_id directly.
--
-- `id` is a server-minted surrogate and `ext_id` is the id the fixture declared.
-- Two tenants seeded from the same whatsapp_init.json would otherwise collide on
-- a fixture-supplied primary key; per-tenant uniqueness on the natural keys is
-- the pattern instagram (UNIQUE(tenant_id, username)) and atlassian
-- (project_key_tenant_unique) already use.
CREATE TABLE IF NOT EXISTS wa_groups (
    id TEXT PRIMARY KEY,
    tenant_id TEXT NOT NULL DEFAULT 'default' REFERENCES tenants(id) ON DELETE CASCADE,
    ext_id TEXT,
    name TEXT NOT NULL,
    admin_phone TEXT,
    created_at TIMESTAMP DEFAULT NOW(),
    UNIQUE (tenant_id, name),
    UNIQUE (tenant_id, ext_id)
);

CREATE TABLE IF NOT EXISTS wa_group_members (
    group_id TEXT NOT NULL REFERENCES wa_groups(id) ON DELETE CASCADE,
    phone TEXT NOT NULL,
    PRIMARY KEY (group_id, phone)
);

CREATE TABLE IF NOT EXISTS wa_group_messages (
    id TEXT PRIMARY KEY,
    group_id TEXT NOT NULL REFERENCES wa_groups(id) ON DELETE CASCADE,
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
CREATE INDEX IF NOT EXISTS idx_calls_user ON call_history(user_id);
CREATE INDEX IF NOT EXISTS idx_calls_user_phone ON call_history(user_id, phone_number);
CREATE INDEX IF NOT EXISTS idx_wa_groups_tenant ON wa_groups(tenant_id);
CREATE INDEX IF NOT EXISTS idx_wa_group_members_phone ON wa_group_members(phone);
CREATE INDEX IF NOT EXISTS idx_wa_group_messages_group ON wa_group_messages(group_id, created_at);

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
            IF TG_ARGV[i] IN ('contacts','message_threads') THEN CONTINUE; END IF;
            RAISE EXCEPTION 'Missing parent for %.%', TG_TABLE_NAME, TG_ARGV[i+1] USING ERRCODE='23503';
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
ALTER TABLE contacts ADD COLUMN IF NOT EXISTS tenant_id TEXT REFERENCES tenants(id) ON DELETE CASCADE;
ALTER TABLE message_threads ADD COLUMN IF NOT EXISTS tenant_id TEXT REFERENCES tenants(id) ON DELETE CASCADE;
ALTER TABLE messages ADD COLUMN IF NOT EXISTS tenant_id TEXT REFERENCES tenants(id) ON DELETE CASCADE;
ALTER TABLE call_history ADD COLUMN IF NOT EXISTS tenant_id TEXT REFERENCES tenants(id) ON DELETE CASCADE;
ALTER TABLE wa_group_members ADD COLUMN IF NOT EXISTS tenant_id TEXT REFERENCES tenants(id) ON DELETE CASCADE;
ALTER TABLE wa_group_messages ADD COLUMN IF NOT EXISTS tenant_id TEXT REFERENCES tenants(id) ON DELETE CASCADE;
UPDATE contacts c SET tenant_id=p.tenant_id FROM users p WHERE c.user_id=p.id AND c.tenant_id IS NULL;
UPDATE message_threads c SET tenant_id=p.tenant_id FROM users p WHERE c.user_id=p.id AND c.tenant_id IS NULL;
UPDATE messages c SET tenant_id=p.tenant_id FROM users p WHERE c.user_id=p.id AND c.tenant_id IS NULL;
UPDATE call_history c SET tenant_id=p.tenant_id FROM users p WHERE c.user_id=p.id AND c.tenant_id IS NULL;
UPDATE wa_group_members c SET tenant_id=p.tenant_id FROM wa_groups p WHERE c.group_id=p.id AND c.tenant_id IS NULL;
UPDATE wa_group_messages c SET tenant_id=p.tenant_id FROM wa_groups p WHERE c.group_id=p.id AND c.tenant_id IS NULL;
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
DROP TRIGGER IF EXISTS call_history_tenant_guard ON call_history;
CREATE TRIGGER call_history_tenant_guard BEFORE INSERT OR UPDATE ON call_history FOR EACH ROW EXECUTE FUNCTION enforce_row_tenant('users','user_id','contacts','contact_id');
UPDATE call_history SET tenant_id=tenant_id;
ALTER TABLE call_history ALTER COLUMN tenant_id SET NOT NULL;
CREATE INDEX IF NOT EXISTS idx_call_history_tenant ON call_history(tenant_id);
DROP TRIGGER IF EXISTS wa_group_members_tenant_guard ON wa_group_members;
CREATE TRIGGER wa_group_members_tenant_guard BEFORE INSERT OR UPDATE ON wa_group_members FOR EACH ROW EXECUTE FUNCTION enforce_row_tenant('wa_groups','group_id');
UPDATE wa_group_members SET tenant_id=tenant_id;
ALTER TABLE wa_group_members ALTER COLUMN tenant_id SET NOT NULL;
CREATE INDEX IF NOT EXISTS idx_wa_group_members_tenant ON wa_group_members(tenant_id);
DROP TRIGGER IF EXISTS wa_group_messages_tenant_guard ON wa_group_messages;
CREATE TRIGGER wa_group_messages_tenant_guard BEFORE INSERT OR UPDATE ON wa_group_messages FOR EACH ROW EXECUTE FUNCTION enforce_row_tenant('wa_groups','group_id','users','user_id');
UPDATE wa_group_messages SET tenant_id=tenant_id;
ALTER TABLE wa_group_messages ALTER COLUMN tenant_id SET NOT NULL;
CREATE INDEX IF NOT EXISTS idx_wa_group_messages_tenant ON wa_group_messages(tenant_id);

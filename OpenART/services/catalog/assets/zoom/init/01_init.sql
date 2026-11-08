-- Zoom Sandbox Database Schema
-- Multi-tenant: tenants, users, meetings have tenant_id. Other tables FK on
-- meetings rather than tenants (cascade swept manually in DELETE /tenants).
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
    name            TEXT NOT NULL,
    password_hash   TEXT NOT NULL,
    tenant_id       TEXT NOT NULL DEFAULT 'default' REFERENCES tenants(id) ON DELETE CASCADE,
    created_at      TIMESTAMP DEFAULT NOW(),
    UNIQUE (email, tenant_id)
);

CREATE INDEX IF NOT EXISTS idx_users_tenant_id ON users(tenant_id);

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
    user_id                 INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    redirect_uri            TEXT NOT NULL,
    scope                   TEXT NOT NULL DEFAULT '',
    code_challenge          TEXT,
    code_challenge_method   TEXT,
    resource                TEXT,
    expires_at              TIMESTAMP NOT NULL,
    used                    BOOLEAN NOT NULL DEFAULT FALSE,
    created_at              TIMESTAMP DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_oauth_codes_client_id ON oauth_authorization_codes(client_id);

CREATE TABLE IF NOT EXISTS meetings (
    id              TEXT PRIMARY KEY,
    tenant_id       TEXT NOT NULL DEFAULT 'default' REFERENCES tenants(id) ON DELETE CASCADE,
    host_email      TEXT NOT NULL,
    topic           TEXT NOT NULL,
    description     TEXT,
    start_time      TEXT,
    duration        INTEGER,
    timezone        TEXT,
    waiting_room    BOOLEAN,
    mute_on_entry   BOOLEAN,
    record_on_start BOOLEAN,
    passcode        TEXT,
    status          TEXT
);

CREATE INDEX IF NOT EXISTS idx_meetings_tenant_id ON meetings(tenant_id);

CREATE TABLE IF NOT EXISTS invitations (
    id             TEXT PRIMARY KEY,
    meeting_id     TEXT,
    invitee_email  TEXT,
    status         TEXT
);

CREATE TABLE IF NOT EXISTS participants (
    meeting_id  TEXT,
    user_email  TEXT,
    role        TEXT,
    state       TEXT,
    PRIMARY KEY (meeting_id, user_email)
);

CREATE TABLE IF NOT EXISTS chat_messages (
    id            TEXT PRIMARY KEY,
    meeting_id    TEXT,
    sender_email  TEXT,
    content       TEXT,
    ts            DOUBLE PRECISION
);

CREATE TABLE IF NOT EXISTS meeting_notes (
    id            TEXT PRIMARY KEY,
    meeting_id    TEXT,
    author_email  TEXT,
    content       TEXT,
    created_at    TEXT,
    updated_at    TEXT
);

-- `end` is a reserved keyword in Postgres so the column must stay quoted in
-- DDL and any reference. `start` is non-reserved and works unquoted.
CREATE TABLE IF NOT EXISTS transcripts (
    id          TEXT PRIMARY KEY,
    meeting_id  TEXT,
    start       DOUBLE PRECISION,
    "end"       DOUBLE PRECISION,
    content     TEXT,
    speaker     TEXT
);


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
            -- Legacy SQLite can retain children after deleting a meeting.
            -- Their explicit namespace stays valid without a live parent.
            IF NEW.tenant_id IS NOT NULL THEN CONTINUE; END IF;
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
ALTER TABLE invitations ADD COLUMN IF NOT EXISTS tenant_id TEXT REFERENCES tenants(id) ON DELETE CASCADE;
UPDATE invitations c SET tenant_id=p.tenant_id FROM meetings p WHERE c.meeting_id=p.id AND c.tenant_id IS NULL;
DROP TRIGGER IF EXISTS row_tenant_guard ON invitations;
CREATE TRIGGER row_tenant_guard BEFORE INSERT OR UPDATE ON invitations FOR EACH ROW EXECUTE FUNCTION enforce_row_tenant('meetings','meeting_id');
UPDATE invitations SET tenant_id=tenant_id;
ALTER TABLE invitations ALTER COLUMN tenant_id SET NOT NULL;
CREATE INDEX IF NOT EXISTS idx_invitations_tenant ON invitations(tenant_id);
ALTER TABLE participants ADD COLUMN IF NOT EXISTS tenant_id TEXT REFERENCES tenants(id) ON DELETE CASCADE;
UPDATE participants c SET tenant_id=p.tenant_id FROM meetings p WHERE c.meeting_id=p.id AND c.tenant_id IS NULL;
DROP TRIGGER IF EXISTS row_tenant_guard ON participants;
CREATE TRIGGER row_tenant_guard BEFORE INSERT OR UPDATE ON participants FOR EACH ROW EXECUTE FUNCTION enforce_row_tenant('meetings','meeting_id');
UPDATE participants SET tenant_id=tenant_id;
ALTER TABLE participants ALTER COLUMN tenant_id SET NOT NULL;
CREATE INDEX IF NOT EXISTS idx_participants_tenant ON participants(tenant_id);
ALTER TABLE chat_messages ADD COLUMN IF NOT EXISTS tenant_id TEXT REFERENCES tenants(id) ON DELETE CASCADE;
UPDATE chat_messages c SET tenant_id=p.tenant_id FROM meetings p WHERE c.meeting_id=p.id AND c.tenant_id IS NULL;
DROP TRIGGER IF EXISTS row_tenant_guard ON chat_messages;
CREATE TRIGGER row_tenant_guard BEFORE INSERT OR UPDATE ON chat_messages FOR EACH ROW EXECUTE FUNCTION enforce_row_tenant('meetings','meeting_id');
UPDATE chat_messages SET tenant_id=tenant_id;
ALTER TABLE chat_messages ALTER COLUMN tenant_id SET NOT NULL;
CREATE INDEX IF NOT EXISTS idx_chat_messages_tenant ON chat_messages(tenant_id);
ALTER TABLE meeting_notes ADD COLUMN IF NOT EXISTS tenant_id TEXT REFERENCES tenants(id) ON DELETE CASCADE;
UPDATE meeting_notes c SET tenant_id=p.tenant_id FROM meetings p WHERE c.meeting_id=p.id AND c.tenant_id IS NULL;
DROP TRIGGER IF EXISTS row_tenant_guard ON meeting_notes;
CREATE TRIGGER row_tenant_guard BEFORE INSERT OR UPDATE ON meeting_notes FOR EACH ROW EXECUTE FUNCTION enforce_row_tenant('meetings','meeting_id');
UPDATE meeting_notes SET tenant_id=tenant_id;
ALTER TABLE meeting_notes ALTER COLUMN tenant_id SET NOT NULL;
CREATE INDEX IF NOT EXISTS idx_meeting_notes_tenant ON meeting_notes(tenant_id);
ALTER TABLE transcripts ADD COLUMN IF NOT EXISTS tenant_id TEXT REFERENCES tenants(id) ON DELETE CASCADE;
UPDATE transcripts c SET tenant_id=p.tenant_id FROM meetings p WHERE c.meeting_id=p.id AND c.tenant_id IS NULL;
DROP TRIGGER IF EXISTS row_tenant_guard ON transcripts;
CREATE TRIGGER row_tenant_guard BEFORE INSERT OR UPDATE ON transcripts FOR EACH ROW EXECUTE FUNCTION enforce_row_tenant('meetings','meeting_id');
UPDATE transcripts SET tenant_id=tenant_id;
ALTER TABLE transcripts ALTER COLUMN tenant_id SET NOT NULL;
CREATE INDEX IF NOT EXISTS idx_transcripts_tenant ON transcripts(tenant_id);
ALTER TABLE oauth_authorization_codes ADD COLUMN IF NOT EXISTS tenant_id TEXT REFERENCES tenants(id) ON DELETE CASCADE;
UPDATE oauth_authorization_codes c SET tenant_id=p.tenant_id FROM users p WHERE c.user_id=p.id AND c.tenant_id IS NULL;
DROP TRIGGER IF EXISTS row_tenant_guard ON oauth_authorization_codes;
CREATE TRIGGER row_tenant_guard BEFORE INSERT OR UPDATE ON oauth_authorization_codes FOR EACH ROW EXECUTE FUNCTION enforce_row_tenant('users','user_id');
UPDATE oauth_authorization_codes SET tenant_id=tenant_id;
ALTER TABLE oauth_authorization_codes ALTER COLUMN tenant_id SET NOT NULL;
CREATE INDEX IF NOT EXISTS idx_oauth_authorization_codes_tenant ON oauth_authorization_codes(tenant_id);

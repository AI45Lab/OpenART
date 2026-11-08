-- Gmail Sandbox Database Schema
-- Post-centralized-IdP design: identity (users, passwords, tokens) lives in
-- google-idp. This env is a pure resource server with:
--   tenants            — local mirror (id + created_at)
--   users_mirror       — IdP sub → local int id; business FKs point here
--   messages           — the mailbox store (was Mailpit; now fully in Postgres)
--   email_ownership    — per-user email visibility / read/star/trash state

CREATE TABLE IF NOT EXISTS tenants (
    id         TEXT PRIMARY KEY,
    created_at TIMESTAMP DEFAULT NOW()
);

INSERT INTO tenants (id) VALUES ('default')
    ON CONFLICT (id) DO NOTHING;

-- `sub` is NULL for a pending mirror: a user seeded by address, bound to its
-- IdP identity on that identity's first request.
CREATE TABLE IF NOT EXISTS users_mirror (
    id          SERIAL PRIMARY KEY,
    sub         INTEGER,
    tenant_id   TEXT NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    email       TEXT,
    name        TEXT,
    created_at  TIMESTAMP DEFAULT NOW(),
    UNIQUE (sub, tenant_id)
);

CREATE INDEX IF NOT EXISTS idx_users_mirror_sub    ON users_mirror(sub);
CREATE INDEX IF NOT EXISTS idx_users_mirror_tenant ON users_mirror(tenant_id);
CREATE INDEX IF NOT EXISTS idx_users_mirror_email  ON users_mirror(email);
CREATE UNIQUE INDEX IF NOT EXISTS users_mirror_tenant_address ON users_mirror(tenant_id, LOWER(email));

-- The mailbox store. Was Mailpit (in-memory, SMTP); now a plain table so the
-- env state is fully DB-representable for snapshot/diff/restore. Columns mirror
-- the fields Mailpit's message JSON exposed (see mail_store.py for the exact
-- summary/detail projection that reproduces the old API responses). Address
-- fields keep Mailpit's [{Name, Address}] shape as JSONB. `id` is our own
-- minted opaque id (was Mailpit's `ID`); `message_id_header` is the RFC
-- Message-ID. Snippet/Size are derived on read, not stored.
CREATE TABLE IF NOT EXISTS messages (
    id                 TEXT NOT NULL,
    tenant_id          TEXT NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    message_id_header  TEXT DEFAULT '',
    from_name          TEXT DEFAULT '',
    from_address       TEXT DEFAULT '',
    to_json            JSONB DEFAULT '[]'::jsonb,
    cc_json            JSONB DEFAULT '[]'::jsonb,
    bcc_json           JSONB DEFAULT '[]'::jsonb,
    reply_to_json      JSONB DEFAULT '[]'::jsonb,
    return_path        TEXT DEFAULT '',
    subject            TEXT DEFAULT '',
    text_body          TEXT DEFAULT '',
    html_body          TEXT DEFAULT '',
    tags_json          JSONB DEFAULT '[]'::jsonb,
    inline_json        JSONB DEFAULT '[]'::jsonb,
    attachments_json   JSONB DEFAULT '[]'::jsonb,
    date               TIMESTAMPTZ DEFAULT NOW(),
    created            TIMESTAMPTZ DEFAULT NOW(),
    PRIMARY KEY (tenant_id, id)
);

CREATE INDEX IF NOT EXISTS idx_messages_tenant ON messages(tenant_id);
CREATE INDEX IF NOT EXISTS idx_messages_from   ON messages(from_address);

CREATE TABLE IF NOT EXISTS email_ownership (
    id                  SERIAL PRIMARY KEY,
    tenant_id          TEXT NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    mailpit_message_id  TEXT NOT NULL,
    user_id             INTEGER NOT NULL REFERENCES users_mirror(id) ON DELETE CASCADE,
    is_read             BOOLEAN DEFAULT FALSE,
    is_starred          BOOLEAN DEFAULT FALSE,
    is_trashed          BOOLEAN DEFAULT FALSE,
    read_at             TIMESTAMP,
    trashed_at          TIMESTAMP,
    created_at          TIMESTAMP DEFAULT NOW(),
    UNIQUE (mailpit_message_id, user_id),
    CONSTRAINT email_ownership_message_tenant_fk FOREIGN KEY (tenant_id, mailpit_message_id)
        REFERENCES messages(tenant_id, id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_email_ownership_message_id ON email_ownership(mailpit_message_id);
CREATE INDEX IF NOT EXISTS idx_email_ownership_user_id    ON email_ownership(user_id);


ALTER TABLE email_ownership ADD COLUMN IF NOT EXISTS is_snoozed BOOLEAN NOT NULL DEFAULT FALSE;
ALTER TABLE email_ownership ADD COLUMN IF NOT EXISTS snoozed_until TIMESTAMPTZ;
CREATE TABLE IF NOT EXISTS drafts (
    id BIGSERIAL NOT NULL,
    tenant_id TEXT NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    user_id INTEGER NOT NULL REFERENCES users_mirror(id) ON DELETE CASCADE,
    to_addr TEXT NOT NULL DEFAULT '',
    cc_addr TEXT NOT NULL DEFAULT '',
    bcc_addr TEXT NOT NULL DEFAULT '',
    subject TEXT NOT NULL DEFAULT '',
    body TEXT NOT NULL DEFAULT '',
    created_at TIMESTAMP NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMP NOT NULL DEFAULT NOW(),
    PRIMARY KEY (tenant_id, id)
);
CREATE INDEX IF NOT EXISTS idx_drafts_tenant_user ON drafts(tenant_id,user_id);


-- Child rows carry the same explicit tenant boundary as their parents.
ALTER TABLE messages ADD COLUMN IF NOT EXISTS raw_mime BYTEA;
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
        EXECUTE format('SELECT tenant_id FROM %I.%I WHERE id::text=$1 AND ($2::text IS NULL OR tenant_id=$2) FOR KEY SHARE', TG_TABLE_SCHEMA, TG_ARGV[i]) INTO parent_tenant USING parent_id, derived_tenant;
        IF parent_tenant IS NULL THEN
            IF derived_tenant IS NOT NULL THEN
                EXECUTE format('SELECT tenant_id FROM %I.%I WHERE id::text=$1 LIMIT 1', TG_TABLE_SCHEMA, TG_ARGV[i]) INTO parent_tenant USING parent_id;
                IF parent_tenant IS NOT NULL THEN
                    RAISE EXCEPTION 'Cross-tenant reference in %', TG_TABLE_NAME USING ERRCODE='23514';
                END IF;
            END IF;
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
ALTER TABLE email_ownership ADD COLUMN IF NOT EXISTS tenant_id TEXT REFERENCES tenants(id) ON DELETE CASCADE;
ALTER TABLE drafts ADD COLUMN IF NOT EXISTS tenant_id TEXT REFERENCES tenants(id) ON DELETE CASCADE;
UPDATE email_ownership c SET tenant_id=p.tenant_id FROM messages p WHERE c.mailpit_message_id=p.id AND c.tenant_id IS NULL;
UPDATE drafts c SET tenant_id=p.tenant_id FROM users_mirror p WHERE c.user_id=p.id AND c.tenant_id IS NULL;
DROP TRIGGER IF EXISTS email_ownership_tenant_guard ON email_ownership;
CREATE TRIGGER email_ownership_tenant_guard BEFORE INSERT OR UPDATE ON email_ownership
    FOR EACH ROW EXECUTE FUNCTION enforce_row_tenant('users_mirror','user_id','messages','mailpit_message_id');
UPDATE email_ownership SET tenant_id=tenant_id;
ALTER TABLE email_ownership ALTER COLUMN tenant_id SET NOT NULL;
CREATE INDEX IF NOT EXISTS idx_email_ownership_tenant ON email_ownership(tenant_id);
DROP TRIGGER IF EXISTS drafts_tenant_guard ON drafts;
CREATE TRIGGER drafts_tenant_guard BEFORE INSERT OR UPDATE ON drafts
    FOR EACH ROW EXECUTE FUNCTION enforce_row_tenant('users_mirror','user_id');
UPDATE drafts SET tenant_id=tenant_id;
ALTER TABLE drafts ALTER COLUMN tenant_id SET NOT NULL;
CREATE INDEX IF NOT EXISTS idx_drafts_tenant ON drafts(tenant_id);

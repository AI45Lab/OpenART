-- Google Docs Sandbox Database Schema
-- Post-centralized-IdP design: env is a pure resource server.
-- Users/tenants/oauth are owned by google-idp. This env only keeps:
--   1. `tenants`          — local mirror (just id + created_at) for FK referenceability
--   2. `users_mirror`     — maps IdP's sub → local integer id that business FKs point to
--   3. business tables    — documents, folders, shares, etc. (unchanged structure)

-- ─── Tenant mirror ──────────────────────────────────────────────────────────
-- Lazily populated on first JWT arrival with a new tenant_id.
-- `DELETE /api/v1/tenants/{id}` on this env cascades through to business data.

CREATE TABLE IF NOT EXISTS tenants (
    id         TEXT PRIMARY KEY,
    created_at TIMESTAMP DEFAULT NOW()
);

INSERT INTO tenants (id) VALUES ('default')
    ON CONFLICT (id) DO NOTHING;

-- ─── User mirror ────────────────────────────────────────────────────────────
-- Authoritative identity is in google-idp. This table only caches enough
-- for local FKs (owner_id etc.) and for JOINs that surface email/name.

CREATE TABLE IF NOT EXISTS users_mirror (
    id         SERIAL PRIMARY KEY,                         -- local integer id; business FKs point here
    sub        INTEGER,                                    -- IdP's user_id; NULL until a seeded account first logs in
    tenant_id  TEXT NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    email      TEXT,                                        -- cached from JWT claims
    name       TEXT,                                        -- cached from JWT claims
    created_at TIMESTAMP DEFAULT NOW(),
    UNIQUE(sub, tenant_id)
);

CREATE INDEX IF NOT EXISTS idx_users_mirror_sub ON users_mirror(sub);
CREATE UNIQUE INDEX IF NOT EXISTS idx_users_mirror_tenant_email ON users_mirror(tenant_id, lower(email));
CREATE INDEX IF NOT EXISTS idx_users_mirror_tenant ON users_mirror(tenant_id);

-- ─── Business tables ────────────────────────────────────────────────────────
-- owner_id / user_id columns FK into users_mirror.id (which is still SERIAL),
-- so the data model for tools is unchanged — an integer user id.

CREATE TABLE IF NOT EXISTS documents (
    id TEXT PRIMARY KEY,
    tenant_id TEXT NOT NULL DEFAULT 'default' REFERENCES tenants(id) ON DELETE CASCADE,
    owner_id INTEGER NOT NULL REFERENCES users_mirror(id) ON DELETE CASCADE,
    title TEXT NOT NULL DEFAULT 'Untitled document',
    content TEXT DEFAULT '',
    content_html TEXT DEFAULT '',
    starred BOOLEAN DEFAULT FALSE,
    trashed BOOLEAN DEFAULT FALSE,
    trashed_at TIMESTAMP,
    last_edited_by INTEGER REFERENCES users_mirror(id) ON DELETE SET NULL,
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS document_shares (
    id TEXT PRIMARY KEY,
    document_id TEXT NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
    user_id INTEGER REFERENCES users_mirror(id) ON DELETE CASCADE,
    email TEXT,
    permission TEXT NOT NULL DEFAULT 'viewer',
    link_sharing BOOLEAN DEFAULT FALSE,
    link_permission TEXT DEFAULT 'viewer',
    created_at TIMESTAMP DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS document_comments (
    id TEXT PRIMARY KEY,
    document_id TEXT NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
    user_id INTEGER NOT NULL REFERENCES users_mirror(id) ON DELETE CASCADE,
    content TEXT NOT NULL,
    quoted_text TEXT,
    selection_start INTEGER,
    selection_end INTEGER,
    resolved BOOLEAN DEFAULT FALSE,
    resolved_by INTEGER REFERENCES users_mirror(id) ON DELETE SET NULL,
    parent_id TEXT REFERENCES document_comments(id) ON DELETE CASCADE,
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS document_versions (
    id TEXT PRIMARY KEY,
    document_id TEXT NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
    version_name TEXT,
    content TEXT NOT NULL,
    content_html TEXT,
    created_by INTEGER NOT NULL REFERENCES users_mirror(id) ON DELETE CASCADE,
    created_at TIMESTAMP DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS folders (
    id TEXT PRIMARY KEY,
    tenant_id TEXT NOT NULL DEFAULT 'default' REFERENCES tenants(id) ON DELETE CASCADE,
    owner_id INTEGER NOT NULL REFERENCES users_mirror(id) ON DELETE CASCADE,
    name TEXT NOT NULL,
    parent_id TEXT REFERENCES folders(id) ON DELETE CASCADE,
    color TEXT,
    starred BOOLEAN DEFAULT FALSE,
    trashed BOOLEAN DEFAULT FALSE,
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS document_folders (
    document_id TEXT NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
    folder_id TEXT NOT NULL REFERENCES folders(id) ON DELETE CASCADE,
    PRIMARY KEY (document_id, folder_id)
);

CREATE TABLE IF NOT EXISTS images (
    id TEXT PRIMARY KEY,
    document_id TEXT REFERENCES documents(id) ON DELETE CASCADE,
    user_id INTEGER NOT NULL REFERENCES users_mirror(id) ON DELETE CASCADE,
    filename TEXT NOT NULL,
    mime_type TEXT NOT NULL,
    size_bytes INTEGER,
    width INTEGER,
    height INTEGER,
    data BYTEA,
    url TEXT,
    created_at TIMESTAMP DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS suggestions (
    id TEXT PRIMARY KEY,
    document_id TEXT NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
    user_id INTEGER NOT NULL REFERENCES users_mirror(id) ON DELETE CASCADE,
    suggestion_type TEXT NOT NULL,
    original_text TEXT,
    suggested_text TEXT,
    selection_start INTEGER,
    selection_end INTEGER,
    status TEXT NOT NULL DEFAULT 'pending',
    reviewed_by INTEGER REFERENCES users_mirror(id) ON DELETE SET NULL,
    created_at TIMESTAMP DEFAULT NOW(),
    reviewed_at TIMESTAMP
);

CREATE TABLE IF NOT EXISTS recent_documents (
    user_id INTEGER NOT NULL REFERENCES users_mirror(id) ON DELETE CASCADE,
    document_id TEXT NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
    accessed_at TIMESTAMP DEFAULT NOW(),
    PRIMARY KEY (user_id, document_id)
);

-- ─── Indexes ────────────────────────────────────────────────────────────────

CREATE INDEX IF NOT EXISTS idx_documents_owner ON documents(owner_id);
CREATE INDEX IF NOT EXISTS idx_documents_tenant_id ON documents(tenant_id);
CREATE INDEX IF NOT EXISTS idx_documents_trashed ON documents(trashed);
CREATE INDEX IF NOT EXISTS idx_documents_updated ON documents(updated_at DESC);
CREATE INDEX IF NOT EXISTS idx_shares_document ON document_shares(document_id);
CREATE INDEX IF NOT EXISTS idx_shares_user ON document_shares(user_id);
CREATE INDEX IF NOT EXISTS idx_comments_document ON document_comments(document_id);
CREATE INDEX IF NOT EXISTS idx_versions_document ON document_versions(document_id);
CREATE INDEX IF NOT EXISTS idx_folders_owner ON folders(owner_id);
CREATE INDEX IF NOT EXISTS idx_folders_tenant_id ON folders(tenant_id);
CREATE INDEX IF NOT EXISTS idx_folders_parent ON folders(parent_id);
CREATE INDEX IF NOT EXISTS idx_images_document ON images(document_id);
CREATE INDEX IF NOT EXISTS idx_suggestions_document ON suggestions(document_id);
CREATE INDEX IF NOT EXISTS idx_recent_user ON recent_documents(user_id);


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
ALTER TABLE documents ADD COLUMN IF NOT EXISTS tenant_id TEXT REFERENCES tenants(id) ON DELETE CASCADE;
ALTER TABLE folders ADD COLUMN IF NOT EXISTS tenant_id TEXT REFERENCES tenants(id) ON DELETE CASCADE;
ALTER TABLE document_shares ADD COLUMN IF NOT EXISTS tenant_id TEXT REFERENCES tenants(id) ON DELETE CASCADE;
ALTER TABLE document_comments ADD COLUMN IF NOT EXISTS tenant_id TEXT REFERENCES tenants(id) ON DELETE CASCADE;
ALTER TABLE document_versions ADD COLUMN IF NOT EXISTS tenant_id TEXT REFERENCES tenants(id) ON DELETE CASCADE;
ALTER TABLE document_folders ADD COLUMN IF NOT EXISTS tenant_id TEXT REFERENCES tenants(id) ON DELETE CASCADE;
ALTER TABLE images ADD COLUMN IF NOT EXISTS tenant_id TEXT REFERENCES tenants(id) ON DELETE CASCADE;
ALTER TABLE suggestions ADD COLUMN IF NOT EXISTS tenant_id TEXT REFERENCES tenants(id) ON DELETE CASCADE;
ALTER TABLE recent_documents ADD COLUMN IF NOT EXISTS tenant_id TEXT REFERENCES tenants(id) ON DELETE CASCADE;
UPDATE documents c SET tenant_id=p.tenant_id FROM users_mirror p WHERE c.owner_id=p.id AND c.tenant_id IS NULL;
UPDATE folders c SET tenant_id=p.tenant_id FROM users_mirror p WHERE c.owner_id=p.id AND c.tenant_id IS NULL;
UPDATE document_shares c SET tenant_id=p.tenant_id FROM documents p WHERE c.document_id=p.id AND c.tenant_id IS NULL;
UPDATE document_comments c SET tenant_id=p.tenant_id FROM documents p WHERE c.document_id=p.id AND c.tenant_id IS NULL;
UPDATE document_versions c SET tenant_id=p.tenant_id FROM documents p WHERE c.document_id=p.id AND c.tenant_id IS NULL;
UPDATE document_folders c SET tenant_id=p.tenant_id FROM documents p WHERE c.document_id=p.id AND c.tenant_id IS NULL;
UPDATE images c SET tenant_id=p.tenant_id FROM users_mirror p WHERE c.user_id=p.id AND c.tenant_id IS NULL;
UPDATE suggestions c SET tenant_id=p.tenant_id FROM documents p WHERE c.document_id=p.id AND c.tenant_id IS NULL;
UPDATE recent_documents c SET tenant_id=p.tenant_id FROM documents p WHERE c.document_id=p.id AND c.tenant_id IS NULL;
DROP TRIGGER IF EXISTS documents_tenant_guard ON documents;
CREATE TRIGGER documents_tenant_guard BEFORE INSERT OR UPDATE ON documents
    FOR EACH ROW EXECUTE FUNCTION enforce_row_tenant('users_mirror','owner_id');
UPDATE documents SET tenant_id=tenant_id;
ALTER TABLE documents ALTER COLUMN tenant_id SET NOT NULL;
CREATE INDEX IF NOT EXISTS idx_documents_tenant ON documents(tenant_id);
DROP TRIGGER IF EXISTS folders_tenant_guard ON folders;
CREATE TRIGGER folders_tenant_guard BEFORE INSERT OR UPDATE ON folders
    FOR EACH ROW EXECUTE FUNCTION enforce_row_tenant('users_mirror','owner_id','folders','parent_id');
UPDATE folders SET tenant_id=tenant_id;
ALTER TABLE folders ALTER COLUMN tenant_id SET NOT NULL;
CREATE INDEX IF NOT EXISTS idx_folders_tenant ON folders(tenant_id);
DROP TRIGGER IF EXISTS document_shares_tenant_guard ON document_shares;
CREATE TRIGGER document_shares_tenant_guard BEFORE INSERT OR UPDATE ON document_shares
    FOR EACH ROW EXECUTE FUNCTION enforce_row_tenant('documents','document_id','users_mirror','user_id');
UPDATE document_shares SET tenant_id=tenant_id;
ALTER TABLE document_shares ALTER COLUMN tenant_id SET NOT NULL;
CREATE INDEX IF NOT EXISTS idx_document_shares_tenant ON document_shares(tenant_id);
DROP TRIGGER IF EXISTS document_comments_tenant_guard ON document_comments;
CREATE TRIGGER document_comments_tenant_guard BEFORE INSERT OR UPDATE ON document_comments
    FOR EACH ROW EXECUTE FUNCTION enforce_row_tenant('documents','document_id','users_mirror','user_id','document_comments','parent_id');
UPDATE document_comments SET tenant_id=tenant_id;
ALTER TABLE document_comments ALTER COLUMN tenant_id SET NOT NULL;
CREATE INDEX IF NOT EXISTS idx_document_comments_tenant ON document_comments(tenant_id);
DROP TRIGGER IF EXISTS document_versions_tenant_guard ON document_versions;
CREATE TRIGGER document_versions_tenant_guard BEFORE INSERT OR UPDATE ON document_versions
    FOR EACH ROW EXECUTE FUNCTION enforce_row_tenant('documents','document_id','users_mirror','created_by');
UPDATE document_versions SET tenant_id=tenant_id;
ALTER TABLE document_versions ALTER COLUMN tenant_id SET NOT NULL;
CREATE INDEX IF NOT EXISTS idx_document_versions_tenant ON document_versions(tenant_id);
DROP TRIGGER IF EXISTS document_folders_tenant_guard ON document_folders;
CREATE TRIGGER document_folders_tenant_guard BEFORE INSERT OR UPDATE ON document_folders
    FOR EACH ROW EXECUTE FUNCTION enforce_row_tenant('documents','document_id','folders','folder_id');
UPDATE document_folders SET tenant_id=tenant_id;
ALTER TABLE document_folders ALTER COLUMN tenant_id SET NOT NULL;
CREATE INDEX IF NOT EXISTS idx_document_folders_tenant ON document_folders(tenant_id);
DROP TRIGGER IF EXISTS images_tenant_guard ON images;
CREATE TRIGGER images_tenant_guard BEFORE INSERT OR UPDATE ON images
    FOR EACH ROW EXECUTE FUNCTION enforce_row_tenant('users_mirror','user_id','documents','document_id');
UPDATE images SET tenant_id=tenant_id;
ALTER TABLE images ALTER COLUMN tenant_id SET NOT NULL;
CREATE INDEX IF NOT EXISTS idx_images_tenant ON images(tenant_id);
DROP TRIGGER IF EXISTS suggestions_tenant_guard ON suggestions;
CREATE TRIGGER suggestions_tenant_guard BEFORE INSERT OR UPDATE ON suggestions
    FOR EACH ROW EXECUTE FUNCTION enforce_row_tenant('documents','document_id','users_mirror','user_id');
UPDATE suggestions SET tenant_id=tenant_id;
ALTER TABLE suggestions ALTER COLUMN tenant_id SET NOT NULL;
CREATE INDEX IF NOT EXISTS idx_suggestions_tenant ON suggestions(tenant_id);
DROP TRIGGER IF EXISTS recent_documents_tenant_guard ON recent_documents;
CREATE TRIGGER recent_documents_tenant_guard BEFORE INSERT OR UPDATE ON recent_documents
    FOR EACH ROW EXECUTE FUNCTION enforce_row_tenant('documents','document_id','users_mirror','user_id');
UPDATE recent_documents SET tenant_id=tenant_id;
ALTER TABLE recent_documents ALTER COLUMN tenant_id SET NOT NULL;
CREATE INDEX IF NOT EXISTS idx_recent_documents_tenant ON recent_documents(tenant_id);

CREATE TABLE IF NOT EXISTS public_ids (
    tenant_id TEXT NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    kind TEXT NOT NULL,
    public_id TEXT NOT NULL,
    internal_id TEXT NOT NULL UNIQUE,
    PRIMARY KEY(tenant_id,kind,public_id)
);

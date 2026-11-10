
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

-- Opaque per-tenant tokens are gone: only google-idp JWTs authenticate users.
DROP TABLE IF EXISTS legacy_tokens;

-- Accounts a seed names are mirrored before their first login: the IdP id (sub)
-- is bound when the account first presents a token. One mirror per email.
ALTER TABLE users_mirror ALTER COLUMN sub DROP NOT NULL;
CREATE UNIQUE INDEX IF NOT EXISTS idx_users_mirror_tenant_email ON users_mirror(tenant_id, lower(email));

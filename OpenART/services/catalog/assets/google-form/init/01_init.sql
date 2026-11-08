-- Google Form Sandbox Database Schema
-- The original single-tenant schema.json, prefill.json and submissions.jsonl
-- are imported once into the default namespace. Every mutable business and
-- migration-history table has explicit tenant ownership.
-- The env is a pure resource server: identity/tokens are owned by google-idp;
-- form filling is anonymous, so there is no users table.

-- ─── Tenant registry ─────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS tenants (
    id         TEXT PRIMARY KEY,
    name       TEXT NOT NULL DEFAULT '',
    status     TEXT NOT NULL DEFAULT 'active',
    created_at TIMESTAMP
);

INSERT INTO tenants (id, name, status, created_at)
    VALUES ('default', 'Default Tenant', 'active', NULL)
    ON CONFLICT (id) DO NOTHING;

-- ─── Form definition ─────────────────────────────────────────────────────────
-- One form per tenant (previously a single global schema.json). The 'default'
-- tenant's saved row is imported from SCHEMA_PATH before baseline seeding.
-- New tenants receive the shared SCHEMA_INIT baseline, never another form.
CREATE TABLE IF NOT EXISTS forms (
    tenant_id TEXT PRIMARY KEY REFERENCES tenants(id) ON DELETE CASCADE,
    schema    JSONB NOT NULL
);

-- ─── Prefill (UI default field values) ───────────────────────────────────────
CREATE TABLE IF NOT EXISTS prefill (
    tenant_id TEXT PRIMARY KEY REFERENCES tenants(id) ON DELETE CASCADE,
    data      JSONB NOT NULL DEFAULT '{}'::jsonb
);

-- ─── Submissions (form responses) ────────────────────────────────────────────
-- id is minted by a shared SERIAL, and unique within a tenant. Snapshot replay
-- can retain the same public IDs in different tenant namespaces; it preserves
-- and advances the sequence, matching the googledocs/gmail id-preservation
-- pattern. The content-hash gate treats id + created_at as volatile so an
-- action-replay (re-submit) that mints a fresh id/timestamp still validates.
CREATE TABLE IF NOT EXISTS submissions (
    id         SERIAL,
    tenant_id  TEXT NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    payload    JSONB NOT NULL,
    created_at TIMESTAMP DEFAULT NOW(),
    PRIMARY KEY (tenant_id, id)
);

CREATE INDEX IF NOT EXISTS idx_submissions_tenant ON submissions(tenant_id, id);

-- Historical import completion is independent of resettable business state.
CREATE TABLE IF NOT EXISTS tenant_migrations (
    tenant_id TEXT NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    migration TEXT NOT NULL,
    outcome TEXT NOT NULL,
    records INTEGER NOT NULL DEFAULT 0,
    imported_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    PRIMARY KEY (tenant_id, migration)
);

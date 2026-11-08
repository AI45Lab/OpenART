-- Per-tenant uniqueness for workflow_scheme / status / label.
-- These tables were originally global (UNIQUE on name only), which both
-- (a) violated the multi-tenancy contract and (b) leaked names across
-- tenants if list endpoints are added later. Add tenant_id + composite
-- UNIQUE; existing rows are tagged 'default'. No data migration needed
-- — issues in non-default tenants can keep referencing default-tagged
-- status rows (FK is by id, not by tenant), and there's currently no
-- list/create endpoint that would expose the cross-tenant pollution.

-- ─── workflow_scheme ─────────────────────────────────────────────
ALTER TABLE workflow_scheme
    ADD COLUMN IF NOT EXISTS tenant_id TEXT NOT NULL DEFAULT 'default'
        REFERENCES tenants(id) ON DELETE CASCADE;

ALTER TABLE workflow_scheme DROP CONSTRAINT IF EXISTS workflow_scheme_name_key;
ALTER TABLE workflow_scheme DROP CONSTRAINT IF EXISTS workflow_scheme_name_tenant_unique;
ALTER TABLE workflow_scheme ADD CONSTRAINT workflow_scheme_name_tenant_unique
    UNIQUE (name, tenant_id);

-- ─── status ───────────────────────────────────────────────────────
ALTER TABLE status
    ADD COLUMN IF NOT EXISTS tenant_id TEXT NOT NULL DEFAULT 'default'
        REFERENCES tenants(id) ON DELETE CASCADE;

ALTER TABLE status DROP CONSTRAINT IF EXISTS status_name_unique;
ALTER TABLE status DROP CONSTRAINT IF EXISTS status_name_tenant_unique;
ALTER TABLE status ADD CONSTRAINT status_name_tenant_unique
    UNIQUE (name, tenant_id);

-- The redundant global UNIQUE INDEX from the old schema must go too,
-- otherwise the same composite-allowed name still collides at the
-- index level.
DROP INDEX IF EXISTS idx_status_name;
-- Re-create as a non-unique helper index for fast name lookups.
CREATE INDEX IF NOT EXISTS idx_status_name ON status (name);

-- ─── label ────────────────────────────────────────────────────────
ALTER TABLE label
    ADD COLUMN IF NOT EXISTS tenant_id TEXT NOT NULL DEFAULT 'default'
        REFERENCES tenants(id) ON DELETE CASCADE;

ALTER TABLE label DROP CONSTRAINT IF EXISTS label_name_key;
ALTER TABLE label DROP CONSTRAINT IF EXISTS label_name_tenant_unique;
ALTER TABLE label ADD CONSTRAINT label_name_tenant_unique
    UNIQUE (name, tenant_id);

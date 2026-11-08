-- Migration: namespace → tenant_id for Atlassian (Jira-like) env
-- Idempotent. Safe to run on fresh DBs (no-op) and on pre-refactor volumes.
--
-- Plan C anchors: tenant_id lives on app_user AND project. Other row-tables
-- (board / issue / comment / activity_log / issue_status_history / project_member /
-- issue_label) inherit tenancy via FK chain to project. Global read-only tables
-- (status / workflow / workflow_scheme / workflow_transition / board_column_status /
-- label) stay shared — confirmed by auditing routes/ that these have no
-- CREATE/PATCH/DELETE API.

-- 1. Ensure tenants table exists
CREATE TABLE IF NOT EXISTS tenants (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL DEFAULT '',
    status TEXT NOT NULL DEFAULT 'active',
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

INSERT INTO tenants (id, name) VALUES ('default', 'Default Tenant')
    ON CONFLICT (id) DO NOTHING;

-- 2. Add tenant_id columns
ALTER TABLE app_user ADD COLUMN IF NOT EXISTS tenant_id TEXT NOT NULL DEFAULT 'default';
ALTER TABLE project  ADD COLUMN IF NOT EXISTS tenant_id TEXT NOT NULL DEFAULT 'default';

-- 3. Copy namespace → app_user.tenant_id on old volumes
DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM information_schema.columns
               WHERE table_name = 'app_user' AND column_name = 'namespace')
    THEN
        UPDATE app_user SET tenant_id = namespace
            WHERE tenant_id = 'default' AND namespace <> 'default';
    END IF;
END $$;

-- 4. Propagate tenant_id from each project's lead onto project rows
UPDATE project p SET tenant_id = u.tenant_id
    FROM app_user u
    WHERE p.lead_id = u.id AND p.tenant_id = 'default' AND u.tenant_id <> 'default';

-- 5. Backfill tenants from any non-default tenant_ids already present
INSERT INTO tenants (id)
    SELECT DISTINCT tenant_id FROM app_user WHERE tenant_id <> 'default'
    ON CONFLICT (id) DO NOTHING;
INSERT INTO tenants (id)
    SELECT DISTINCT tenant_id FROM project WHERE tenant_id <> 'default'
    ON CONFLICT (id) DO NOTHING;

-- 6. Add FKs on tenant_id → tenants.id
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.table_constraints
        WHERE table_name = 'app_user' AND constraint_name = 'app_user_tenant_id_fkey'
    ) THEN
        ALTER TABLE app_user
            ADD CONSTRAINT app_user_tenant_id_fkey
            FOREIGN KEY (tenant_id) REFERENCES tenants(id) ON DELETE CASCADE;
    END IF;

    IF NOT EXISTS (
        SELECT 1 FROM information_schema.table_constraints
        WHERE table_name = 'project' AND constraint_name = 'project_tenant_id_fkey'
    ) THEN
        ALTER TABLE project
            ADD CONSTRAINT project_tenant_id_fkey
            FOREIGN KEY (tenant_id) REFERENCES tenants(id) ON DELETE CASCADE;
    END IF;
END $$;

-- 7. Swap UNIQUE(email, namespace) → UNIQUE(email, tenant_id) on app_user
DO $$
BEGIN
    -- Defensive: original pre-namespace schema had `email TEXT NOT NULL UNIQUE`,
    -- creating app_user_email_key. The namespace refactor replaced the schema
    -- but did not ship a migration, so older volumes still have it.
    IF EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'app_user_email_key') THEN
        ALTER TABLE app_user DROP CONSTRAINT app_user_email_key;
    END IF;
    IF EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'app_user_email_namespace_key') THEN
        ALTER TABLE app_user DROP CONSTRAINT app_user_email_namespace_key;
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'app_user_email_tenant_id_key') THEN
        ALTER TABLE app_user ADD CONSTRAINT app_user_email_tenant_id_key UNIQUE (email, tenant_id);
    END IF;
END $$;

-- 8. Indexes
DROP INDEX IF EXISTS idx_app_user_email_ns;
CREATE INDEX IF NOT EXISTS idx_app_user_email_tenant_id ON app_user (email, tenant_id);
CREATE INDEX IF NOT EXISTS idx_app_user_tenant_id        ON app_user (tenant_id);
CREATE INDEX IF NOT EXISTS idx_project_tenant_id         ON project  (tenant_id);

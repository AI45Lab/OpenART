-- Multi-tenancy fix: project.key was UNIQUE globally, which leaked
-- one tenant's project keys to another (cross-tenant: tenant B's
-- create with the same key returned a 500 with the constraint name,
-- exposing tenant A's existence). Move to per-tenant uniqueness.

-- Drop the old global constraint. The auto-generated name is
-- `project_key_key` for `key TEXT UNIQUE`; guard with IF EXISTS so
-- this migration is safe to re-run.
ALTER TABLE project DROP CONSTRAINT IF EXISTS project_key_key;

-- Add the composite uniqueness. Use a stable name so future drops
-- (or re-applications) don't depend on auto-naming.
ALTER TABLE project DROP CONSTRAINT IF EXISTS project_key_tenant_unique;
ALTER TABLE project ADD CONSTRAINT project_key_tenant_unique UNIQUE (key, tenant_id);

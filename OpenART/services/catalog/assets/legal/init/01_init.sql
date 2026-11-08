-- legal env schema
--
-- Only per-tenant MUTABLE state lives here. The read-only corpus stays in
-- files: 33MB of CourtListener (1152 clusters, 942 opinions, 25 flat tables),
-- 116 statutes, 11 templates and the 195-matter baseline are identical for
-- every tenant and are loaded once per process. Copying them per tenant into
-- rows would multiply the same bytes by the tenant count and buy nothing —
-- the same call the travel and hospital ports made about their catalogs.
--
-- Matters follow the overlay pattern the env already uses for the CourtListener
-- corpus: the 195-matter baseline is shared, and a tenant's additions (stubs
-- created by document injection) and appends (notes) are stored as deltas.

-- ─── Tenancy ──────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS tenants (
    id         TEXT PRIMARY KEY,
    name       TEXT NOT NULL DEFAULT '',
    status     TEXT NOT NULL DEFAULT 'active',
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- Rows are created only by the env server (POST /api/v1/tenants, admin token).
-- No tenant is seeded here, and none is created as a side effect of a request.

-- ─── Users ────────────────────────────────────────────────────────────
-- Registered per tenant by the admin-only POST /auth/register; /auth/login
-- verifies the PBKDF2 hash and signs the JWT whose tenant_id the user routes
-- are scoped by. Deleting a tenant removes its users.
CREATE TABLE IF NOT EXISTS legal_users (
    id            BIGSERIAL PRIMARY KEY,
    tenant_id     TEXT NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    email         TEXT NOT NULL,
    name          TEXT NOT NULL DEFAULT '',
    password_hash TEXT NOT NULL,
    created_at    TIMESTAMPTZ DEFAULT NOW()
);
CREATE UNIQUE INDEX IF NOT EXISTS idx_legal_users_email ON legal_users(tenant_id, (lower(email)));

-- ─── Document vault ───────────────────────────────────────────────────
-- Seeded per task by setup.sh through POST /api/documents (admin); read by the
-- agent's list_documents / get_document / analyze_document.
CREATE TABLE IF NOT EXISTS legal_documents (
    tenant_id      TEXT NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    document_id    TEXT NOT NULL,
    filename       TEXT NOT NULL DEFAULT '',
    doc_type       TEXT NOT NULL DEFAULT '',
    upload_time    TEXT NOT NULL DEFAULT '',
    matter_id      TEXT,
    content        TEXT NOT NULL DEFAULT '',
    summary        TEXT NOT NULL DEFAULT '',
    extracted_data JSONB NOT NULL DEFAULT '{}'::jsonb,
    seq            BIGSERIAL,
    PRIMARY KEY (tenant_id, document_id)
);

-- ─── Drafts ───────────────────────────────────────────────────────────
-- Judge-visible: all 600 medical-style legal judges call get_drafts().
CREATE TABLE IF NOT EXISTS legal_drafts (
    tenant_id   TEXT NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    draft_id    TEXT NOT NULL,
    template_id TEXT NOT NULL DEFAULT '',
    matter_id   TEXT DEFAULT '',
    doc_type    TEXT NOT NULL DEFAULT '',
    title       TEXT NOT NULL DEFAULT '',
    content     TEXT NOT NULL DEFAULT '',
    created_at  TEXT NOT NULL DEFAULT '',
    updated_at  TEXT NOT NULL DEFAULT '',
    status      TEXT NOT NULL DEFAULT 'draft',
    seq         BIGSERIAL,
    PRIMARY KEY (tenant_id, draft_id)
);

-- The original MCP omitted matter_id as JSON null. Preserve that optional
-- business field on both fresh databases and volumes created by an earlier
-- multitenant image; tenant_id remains mandatory.
ALTER TABLE legal_drafts ALTER COLUMN matter_id DROP NOT NULL;

-- ─── Prepared filings and the action log ──────────────────────────────
-- Both are judge-visible (all 600 judges call get_prepared_filings) and both
-- live in legal_injections below, under kind='prepared_filings' and
-- kind='action_log'. They are declared on _TenantState with the same _list()
-- helper as the injection collections, so PgList — which writes to
-- legal_injections — is what backs them.
--
-- This file used to also declare dedicated legal_prepared_filings and
-- legal_action_log tables. Nothing ever wrote to them: a live database showed
-- 1362 action_log and 38 prepared_filings rows in legal_injections and zero in
-- either dedicated table. They are gone rather than wired up, because the
-- generic table already gives the two properties that matter — per-tenant
-- scoping and BIGSERIAL append order — and a schema that describes storage
-- nothing uses is how the last three of these bugs stayed hidden. An
-- environment that booted earlier keeps two empty tables; nothing reads them.

-- ─── Matter overlay ───────────────────────────────────────────────────
-- Stubs auto-created when an injected document names a matter that is not in
-- the shared baseline (mcp.py:2272, :2293).
CREATE TABLE IF NOT EXISTS legal_matter_stubs (
    tenant_id   TEXT NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    matter_id   TEXT NOT NULL,
    matter_name TEXT NOT NULL DEFAULT '',
    matter_type TEXT NOT NULL DEFAULT 'general',
    status      TEXT NOT NULL DEFAULT 'active',
    PRIMARY KEY (tenant_id, matter_id)
);

-- Appended by the add_matter_note tool, the only tool that mutates a matter.
CREATE TABLE IF NOT EXISTS legal_matter_notes (
    seq           BIGSERIAL PRIMARY KEY,
    tenant_id     TEXT NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    matter_id     TEXT NOT NULL,
    note          TEXT NOT NULL DEFAULT '',
    is_privileged BOOLEAN NOT NULL DEFAULT FALSE,
    created_at    TEXT NOT NULL DEFAULT ''
);

-- ─── Injection state ──────────────────────────────────────────────────
-- One table for eleven collections rather than eleven tables: they are all
-- written by POST /api/inject/*, read whole, and cleared together by reset,
-- and none of them is queried by field. `kind` names the collection.
--
-- List-shaped kinds (append, read in seq order): document_injections,
--   extra_entries, case_modifications, matter_modifications, case_notes,
--   verification_overrides, injected_recipients, injection_log,
--   injected_suggestions, and the two judge-visible ones that are not
--   injections at all — action_log and prepared_filings (see above).
-- Singleton kinds (one row, replaced on write): billing_suggestion,
--   tool_description_injections, cl_overlay, injected_cases.
CREATE TABLE IF NOT EXISTS legal_injections (
    seq        BIGSERIAL PRIMARY KEY,
    tenant_id  TEXT NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    kind       TEXT NOT NULL,
    payload    JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- ─── Indexes ──────────────────────────────────────────────────────────
CREATE INDEX IF NOT EXISTS idx_legal_documents_t   ON legal_documents(tenant_id, seq);
CREATE INDEX IF NOT EXISTS idx_legal_drafts_t      ON legal_drafts(tenant_id, seq);
CREATE INDEX IF NOT EXISTS idx_legal_notes_t       ON legal_matter_notes(tenant_id, matter_id, seq);
CREATE INDEX IF NOT EXISTS idx_legal_injections_tk ON legal_injections(tenant_id, kind, seq);

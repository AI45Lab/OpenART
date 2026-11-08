-- PostgreSQL schema for Jira-like issue tracking system
-- Creates core entities: users, projects, boards, columns, statuses, workflows,
-- issues, status history, comments, activity log, and supporting tables.
--
-- Key query patterns supported by this schema:
-- 1) Load board view with issues grouped by columns:
--    - Resolve board by id → board + project
--    - Load board_column rows ordered by position for the board
--    - For each column, join board_column_status → statuses → issues where issue.status_id IN (column statuses)
--    - Filter issues by search text, status, assignee using indexes and full-text search
--
-- 2) Load issue detail with comments and history:
--    - SELECT issue by id including project, status, assignee, reporter
--    - LEFT JOIN parent issue for subtasks
--    - Aggregate labels via issue_label → label
--    - SELECT comments WHERE issue_id = ? ORDER BY created_at
--    - SELECT issue_status_history WHERE issue_id = ? ORDER BY created_at
--    - SELECT activity_log WHERE issue_id = ? ORDER BY created_at
--
-- 3) Search issues across a project or board:
--    - Use idx_issue_search GIN index over title + description with to_tsvector
--    - Combine with filters on project_id, status_id, assignee_id via btree indexes
--
-- 4) Compute available status transitions for an issue:
--    - Given issue.status_id and project/workflow, SELECT workflow_transition
--      WHERE workflow_id matches project.workflow_scheme_id mapping
--      AND from_status_id = current status OR from_status_id IS NULL
--    - Filter transitions by current user project_role using allowed_roles array.

CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
CREATE EXTENSION IF NOT EXISTS pg_trgm;

-- Tenants (first-class table introduced with multi-tenancy refactor)
CREATE TABLE IF NOT EXISTS tenants (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL DEFAULT '',
    status TEXT NOT NULL DEFAULT 'active',
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

INSERT INTO tenants (id, name) VALUES ('default', 'Default Tenant')
    ON CONFLICT (id) DO NOTHING;

-- Users
--
-- No `access_token` column. JWTs are stateless (env-oauth-blueprint:
-- "Don't put access_token on the users table"); per-user opaque tokens
-- stored on the row are an anti-pattern and prevent rotation/multi-session.
CREATE TABLE IF NOT EXISTS app_user (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    display_name TEXT NOT NULL,
    email TEXT NOT NULL,
    tenant_id TEXT NOT NULL DEFAULT 'default'
        REFERENCES tenants(id) ON DELETE CASCADE,
    avatar_url TEXT,
    initials TEXT,
    global_role TEXT NOT NULL DEFAULT 'user', -- system_admin | user
    password_hash TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE(email, tenant_id)
);

-- OAuth2 clients (RFC 7591 Dynamic Client Registration).
CREATE TABLE IF NOT EXISTS oauth_clients (
    client_id TEXT PRIMARY KEY,
    client_secret TEXT,
    client_name TEXT NOT NULL DEFAULT '',
    redirect_uris JSONB NOT NULL DEFAULT '[]'::jsonb,
    grant_types JSONB NOT NULL DEFAULT '["authorization_code"]'::jsonb,
    response_types JSONB NOT NULL DEFAULT '["code"]'::jsonb,
    scope TEXT NOT NULL DEFAULT '',
    token_endpoint_auth_method TEXT NOT NULL DEFAULT 'none',
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- OAuth2 authorization codes (short-lived, single-use; PKCE-bound).
CREATE TABLE IF NOT EXISTS oauth_authorization_codes (
    code TEXT PRIMARY KEY,
    client_id TEXT NOT NULL,
    user_id UUID NOT NULL REFERENCES app_user(id) ON DELETE CASCADE,
    redirect_uri TEXT NOT NULL,
    scope TEXT NOT NULL DEFAULT '',
    code_challenge TEXT,
    code_challenge_method TEXT,
    resource TEXT,
    expires_at TIMESTAMPTZ NOT NULL,
    used BOOLEAN NOT NULL DEFAULT false,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- Projects
CREATE TABLE IF NOT EXISTS project (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    -- Per-tenant uniqueness: same key may exist in different tenants
    -- (multi-tenancy contract). See migration 003 for the matching
    -- ALTER on existing databases.
    key TEXT NOT NULL,
    name TEXT NOT NULL,
    description TEXT,
    tenant_id TEXT NOT NULL DEFAULT 'default'
        REFERENCES tenants(id) ON DELETE CASCADE,
    lead_id UUID NOT NULL REFERENCES app_user(id) ON DELETE RESTRICT,
    default_board_id UUID,
    workflow_scheme_id UUID,
    is_archived BOOLEAN NOT NULL DEFAULT FALSE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (key, tenant_id)
);

-- Workflow scheme groups workflows for a project.
-- Per-tenant uniqueness: name may collide across tenants (multi-tenancy
-- contract). See migration 004 for the matching ALTER on existing DBs.
CREATE TABLE IF NOT EXISTS workflow_scheme (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    name TEXT NOT NULL,
    description TEXT,
    tenant_id TEXT NOT NULL DEFAULT 'default'
        REFERENCES tenants(id) ON DELETE CASCADE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (name, tenant_id)
);

-- Workflow belongs to a scheme and defines transitions between statuses
CREATE TABLE IF NOT EXISTS workflow (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    workflow_scheme_id UUID NOT NULL REFERENCES workflow_scheme(id) ON DELETE CASCADE,
    name TEXT NOT NULL,
    description TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- Statuses represent the lifecycle states of issues
-- Assumptions based on seed data and API usage:
-- - name: human-readable status name (unique)
-- - category: high-level grouping (backlog, in_progress, done, etc.)
-- - color: hex color used in UI
-- - position: ordering within a workflow/board
-- - is_terminal: whether this status is a terminal/done state
-- Statuses are per-tenant (multi-tenancy contract). See migration 004
-- for the ALTER on existing DBs. Note: idx_status_name (older redundant
-- unique index) is dropped in the same migration.
CREATE TABLE IF NOT EXISTS status (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    name TEXT NOT NULL,
    category TEXT NOT NULL,
    color TEXT,
    position INT NOT NULL,
    is_terminal BOOLEAN NOT NULL DEFAULT FALSE,
    tenant_id TEXT NOT NULL DEFAULT 'default'
        REFERENCES tenants(id) ON DELETE CASCADE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT status_name_tenant_unique UNIQUE (name, tenant_id)
);


-- Boards
CREATE TABLE IF NOT EXISTS board (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    project_id UUID NOT NULL REFERENCES project(id) ON DELETE CASCADE,
    name TEXT NOT NULL,
    type TEXT NOT NULL DEFAULT 'kanban',
    is_default BOOLEAN NOT NULL DEFAULT FALSE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

ALTER TABLE project DROP CONSTRAINT IF EXISTS project_default_board_fk;
ALTER TABLE project
    ADD CONSTRAINT project_default_board_fk
    FOREIGN KEY (default_board_id) REFERENCES board(id) ON DELETE SET NULL;


ALTER TABLE project DROP CONSTRAINT IF EXISTS project_workflow_scheme_fk;
ALTER TABLE project
    ADD CONSTRAINT project_workflow_scheme_fk
    FOREIGN KEY (workflow_scheme_id) REFERENCES workflow_scheme(id) ON DELETE RESTRICT;

-- Workflow transitions
CREATE TABLE IF NOT EXISTS workflow_transition (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    workflow_id UUID NOT NULL REFERENCES workflow(id) ON DELETE CASCADE,
    from_status_id UUID REFERENCES status(id) ON DELETE SET NULL,
    to_status_id UUID NOT NULL REFERENCES status(id) ON DELETE RESTRICT,
    name TEXT NOT NULL,
    allowed_roles TEXT[] NOT NULL DEFAULT '{}',
    required_fields TEXT[] NOT NULL DEFAULT '{}',
    is_default BOOLEAN NOT NULL DEFAULT FALSE
);

-- Boards columns (kanban)
CREATE TABLE IF NOT EXISTS board_column (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    board_id UUID NOT NULL REFERENCES board(id) ON DELETE CASCADE,
    name TEXT NOT NULL,
    wip_limit INT,
    position INT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- Mapping between board columns and statuses (many-to-many)
CREATE TABLE IF NOT EXISTS board_column_status (
    board_column_id UUID NOT NULL REFERENCES board_column(id) ON DELETE CASCADE,
    status_id UUID NOT NULL REFERENCES status(id) ON DELETE CASCADE,
    PRIMARY KEY (board_column_id, status_id)
);

-- Issues
CREATE TABLE IF NOT EXISTS issue (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    project_id UUID NOT NULL REFERENCES project(id) ON DELETE CASCADE,
    key TEXT NOT NULL,
    title TEXT NOT NULL,
    description TEXT,
    type TEXT NOT NULL CHECK (type IN ('story', 'task', 'bug', 'epic')),
    status_id UUID NOT NULL REFERENCES status(id) ON DELETE RESTRICT,
    priority TEXT NOT NULL CHECK (priority IN ('highest', 'high', 'medium', 'low', 'lowest')),
    assignee_id UUID REFERENCES app_user(id) ON DELETE SET NULL,
    reporter_id UUID NOT NULL REFERENCES app_user(id) ON DELETE RESTRICT,
    parent_issue_id UUID REFERENCES issue(id) ON DELETE SET NULL,
    story_points NUMERIC(5,2),
    estimate_hours NUMERIC(6,2),
    due_date DATE,
    start_date DATE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    resolved_at TIMESTAMPTZ,
    resolution TEXT,
    UNIQUE (project_id, key)
);

-- Labels are per-tenant (multi-tenancy contract). See migration 004
-- for the ALTER on existing DBs.
CREATE TABLE IF NOT EXISTS label (
    id SERIAL PRIMARY KEY,
    name TEXT NOT NULL,
    tenant_id TEXT NOT NULL DEFAULT 'default'
        REFERENCES tenants(id) ON DELETE CASCADE,
    UNIQUE (name, tenant_id)
);

-- Project membership links users to projects with roles
-- Assumptions based on seed data:
-- - project_role: project_admin | project_lead | developer | reporter | viewer
CREATE TABLE IF NOT EXISTS project_member (
    project_id UUID NOT NULL REFERENCES project(id) ON DELETE CASCADE,
    user_id UUID NOT NULL REFERENCES app_user(id) ON DELETE CASCADE,
    project_role TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (project_id, user_id)
);

-- Join table between issues and labels
CREATE TABLE IF NOT EXISTS issue_label (
    issue_id UUID NOT NULL REFERENCES issue(id) ON DELETE CASCADE,
    label_id INT NOT NULL REFERENCES label(id) ON DELETE CASCADE,
    PRIMARY KEY (issue_id, label_id)
);

-- Comments on issues
CREATE TABLE IF NOT EXISTS comment (
    id SERIAL PRIMARY KEY,
    issue_id UUID NOT NULL REFERENCES issue(id) ON DELETE CASCADE,
    author_id UUID NOT NULL REFERENCES app_user(id) ON DELETE SET NULL,
    body TEXT NOT NULL,
    is_edited BOOLEAN NOT NULL DEFAULT FALSE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- History of status changes for issues
CREATE TABLE IF NOT EXISTS issue_status_history (
    id SERIAL PRIMARY KEY,
    issue_id UUID NOT NULL REFERENCES issue(id) ON DELETE CASCADE,
    from_status_id UUID REFERENCES status(id) ON DELETE SET NULL,
    to_status_id UUID NOT NULL REFERENCES status(id) ON DELETE RESTRICT,
    actor_id UUID NOT NULL REFERENCES app_user(id) ON DELETE SET NULL,
    transition_id UUID REFERENCES workflow_transition(id) ON DELETE SET NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- Activity log for issues (audit trail)
CREATE TABLE IF NOT EXISTS activity_log (
    id SERIAL PRIMARY KEY,
    issue_id UUID NOT NULL REFERENCES issue(id) ON DELETE CASCADE,
    actor_id UUID REFERENCES app_user(id) ON DELETE SET NULL,
    type TEXT NOT NULL,
    from_payload JSONB,
    to_payload JSONB,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- Indexes for performance

-- Users
CREATE INDEX IF NOT EXISTS idx_app_user_email_tenant_id ON app_user (email, tenant_id);
CREATE INDEX IF NOT EXISTS idx_app_user_tenant_id ON app_user (tenant_id);

-- OAuth2
CREATE INDEX IF NOT EXISTS idx_oauth_codes_client_id ON oauth_authorization_codes (client_id);
CREATE INDEX IF NOT EXISTS idx_oauth_codes_expires ON oauth_authorization_codes (expires_at);

-- Projects
CREATE INDEX IF NOT EXISTS idx_project_lead_id ON project (lead_id);
CREATE INDEX IF NOT EXISTS idx_project_tenant_id ON project (tenant_id);

-- Boards and columns
CREATE INDEX IF NOT EXISTS idx_board_project_id ON board (project_id);
CREATE INDEX IF NOT EXISTS idx_board_column_board_id_position ON board_column (board_id, position);

-- Status. Composite uniqueness is enforced by the table constraint above
-- (status_name_tenant_unique); the old global idx_status_name is dropped
-- by migration 004. Keep a non-unique index on name for fast lookups.
CREATE INDEX IF NOT EXISTS idx_status_name ON status (name);
CREATE INDEX IF NOT EXISTS idx_status_category ON status (category);

-- Issues
CREATE INDEX IF NOT EXISTS idx_issue_project_id ON issue (project_id);
CREATE INDEX IF NOT EXISTS idx_issue_status_id ON issue (status_id);
CREATE INDEX IF NOT EXISTS idx_issue_assignee_id ON issue (assignee_id);
CREATE INDEX IF NOT EXISTS idx_issue_reporter_id ON issue (reporter_id);
CREATE INDEX IF NOT EXISTS idx_issue_project_status ON issue (project_id, status_id);

-- Full text search index on issue title and description
CREATE INDEX IF NOT EXISTS idx_issue_search ON issue USING GIN (
    to_tsvector('simple', coalesce(title, '') || ' ' || coalesce(description, ''))
);

-- Comments
CREATE INDEX IF NOT EXISTS idx_comment_issue_id_created_at ON comment (issue_id, created_at);

-- Activity log
CREATE INDEX IF NOT EXISTS idx_activity_log_issue_id_created_at ON activity_log (issue_id, created_at);

-- Issue status history
CREATE INDEX IF NOT EXISTS idx_issue_status_history_issue_id_created_at ON issue_status_history (issue_id, created_at);

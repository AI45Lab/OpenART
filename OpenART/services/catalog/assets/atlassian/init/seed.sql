-- Seed data for Jira-like issue tracking system
-- Using fixed UUIDs for reliable references

-- Users (fixed UUIDs). Baseline content users: they own the demo catalog and
-- cannot log in ('!no-login' is NO_LOGIN_PASSWORD_HASH in
-- app/backend/src/auth/passwords.js). Task accounts are registered per tenant.
INSERT INTO app_user (id, display_name, email, avatar_url, initials, global_role, password_hash)
VALUES
  ('a0000000-0000-0000-0000-000000000001', 'Alice Admin', 'alice@example.com', NULL, 'AA', 'system_admin', '!no-login'),
  ('a0000000-0000-0000-0000-000000000002', 'Peter Product', 'peter@example.com', NULL, 'PP', 'user', '!no-login'),
  ('a0000000-0000-0000-0000-000000000003', 'Devon Developer', 'devon@example.com', NULL, 'DD', 'user', '!no-login'),
  ('a0000000-0000-0000-0000-000000000004', 'Rita Reporter', 'rita@example.com', NULL, 'RR', 'user', '!no-login'),
  ('a0000000-0000-0000-0000-000000000005', 'Victor Viewer', 'victor@example.com', NULL, 'VV', 'user', '!no-login'),
  ('a0000000-0000-0000-0000-000000000100', 'Tom Harrison', 'tom.harrison@acme.ai', NULL, 'TH', 'user', '!no-login')
ON CONFLICT (email, tenant_id) DO NOTHING;

-- Workflow scheme (now per-tenant; seed row goes to the 'default' tenant)
INSERT INTO workflow_scheme (id, name, description)
VALUES ('b0000000-0000-0000-0000-000000000001', 'Default Software Scheme', 'Default workflow scheme for software projects')
ON CONFLICT DO NOTHING;

-- Statuses (per-tenant; seed rows tagged with the table-default 'default')
INSERT INTO status (id, name, category, color, position, is_terminal) VALUES
  ('c0000000-0000-0000-0000-000000000001', 'Backlog', 'backlog', '#5E6C84', 0, FALSE),
  ('c0000000-0000-0000-0000-000000000002', 'Selected for Development', 'backlog', '#5E6C84', 1, FALSE),
  ('c0000000-0000-0000-0000-000000000003', 'In Progress', 'in_progress', '#0052CC', 2, FALSE),
  ('c0000000-0000-0000-0000-000000000004', 'In Review', 'in_progress', '#FFAB00', 3, FALSE),
  ('c0000000-0000-0000-0000-000000000005', 'Done', 'done', '#36B37E', 4, TRUE)
ON CONFLICT DO NOTHING;

-- Workflow
INSERT INTO workflow (id, workflow_scheme_id, name, description)
VALUES ('d0000000-0000-0000-0000-000000000001', 'b0000000-0000-0000-0000-000000000001', 'Default Workflow', 'Backlog -> Selected -> In Progress -> In Review -> Done')
ON CONFLICT DO NOTHING;

-- Workflow transitions
INSERT INTO workflow_transition (id, workflow_id, from_status_id, to_status_id, name, allowed_roles, required_fields, is_default) VALUES
  ('e0000000-0000-0000-0000-000000000001', 'd0000000-0000-0000-0000-000000000001', 'c0000000-0000-0000-0000-000000000001', 'c0000000-0000-0000-0000-000000000002', 'Plan work', ARRAY['project_admin','project_lead'], ARRAY['title'], TRUE),
  ('e0000000-0000-0000-0000-000000000002', 'd0000000-0000-0000-0000-000000000001', 'c0000000-0000-0000-0000-000000000002', 'c0000000-0000-0000-0000-000000000003', 'Start work', ARRAY['developer','project_lead','project_admin'], ARRAY['assigneeId'], TRUE),
  ('e0000000-0000-0000-0000-000000000003', 'd0000000-0000-0000-0000-000000000001', 'c0000000-0000-0000-0000-000000000003', 'c0000000-0000-0000-0000-000000000004', 'Send to review', ARRAY['developer','project_lead','project_admin'], ARRAY[]::TEXT[], TRUE),
  ('e0000000-0000-0000-0000-000000000004', 'd0000000-0000-0000-0000-000000000001', 'c0000000-0000-0000-0000-000000000004', 'c0000000-0000-0000-0000-000000000005', 'Approve and complete', ARRAY['project_lead','project_admin'], ARRAY['resolution'], TRUE),
  ('e0000000-0000-0000-0000-000000000005', 'd0000000-0000-0000-0000-000000000001', 'c0000000-0000-0000-0000-000000000005', 'c0000000-0000-0000-0000-000000000003', 'Reopen', ARRAY['developer','project_lead','project_admin'], ARRAY[]::TEXT[], FALSE)
ON CONFLICT DO NOTHING;

-- Projects
INSERT INTO project (id, key, name, description, lead_id, workflow_scheme_id, is_archived)
VALUES
  ('10000000-0000-0000-0000-000000000001', 'SAM1', 'Sample Web App', 'Web application project', 'a0000000-0000-0000-0000-000000000002', 'b0000000-0000-0000-0000-000000000001', FALSE),
  ('10000000-0000-0000-0000-000000000002', 'OPS', 'Operations', 'Internal operations and support', 'a0000000-0000-0000-0000-000000000001', 'b0000000-0000-0000-0000-000000000001', FALSE),
  ('10000000-0000-0000-0000-000000000003', 'ONB', 'Onboarding', 'Customer onboarding project', 'a0000000-0000-0000-0000-000000000002', 'b0000000-0000-0000-0000-000000000001', FALSE),
  ('10000000-0000-0000-0000-000000000004', 'ENG', 'Engineering', 'Engineering execution project', 'a0000000-0000-0000-0000-000000000001', 'b0000000-0000-0000-0000-000000000001', FALSE)
ON CONFLICT DO NOTHING;

-- Boards
INSERT INTO board (id, project_id, name, type, is_default) VALUES
  ('20000000-0000-0000-0000-000000000001', '10000000-0000-0000-0000-000000000001', 'Sample Web App Board', 'kanban', TRUE),
  ('20000000-0000-0000-0000-000000000002', '10000000-0000-0000-0000-000000000002', 'Operations Board', 'kanban', TRUE),
  ('20000000-0000-0000-0000-000000000003', '10000000-0000-0000-0000-000000000003', 'Onboarding Board', 'kanban', TRUE),
  ('20000000-0000-0000-0000-000000000004', '10000000-0000-0000-0000-000000000004', 'Engineering Board', 'kanban', TRUE)
ON CONFLICT DO NOTHING;

-- Update projects with default_board_id
UPDATE project SET default_board_id = '20000000-0000-0000-0000-000000000001' WHERE id = '10000000-0000-0000-0000-000000000001';
UPDATE project SET default_board_id = '20000000-0000-0000-0000-000000000002' WHERE id = '10000000-0000-0000-0000-000000000002';
UPDATE project SET default_board_id = '20000000-0000-0000-0000-000000000003' WHERE id = '10000000-0000-0000-0000-000000000003';
UPDATE project SET default_board_id = '20000000-0000-0000-0000-000000000004' WHERE id = '10000000-0000-0000-0000-000000000004';

-- Project memberships
INSERT INTO project_member (project_id, user_id, project_role) VALUES
  ('10000000-0000-0000-0000-000000000001', 'a0000000-0000-0000-0000-000000000001', 'project_admin'),
  ('10000000-0000-0000-0000-000000000001', 'a0000000-0000-0000-0000-000000000002', 'project_lead'),
  ('10000000-0000-0000-0000-000000000001', 'a0000000-0000-0000-0000-000000000003', 'developer'),
  ('10000000-0000-0000-0000-000000000001', 'a0000000-0000-0000-0000-000000000004', 'reporter'),
  ('10000000-0000-0000-0000-000000000001', 'a0000000-0000-0000-0000-000000000005', 'viewer'),
  ('10000000-0000-0000-0000-000000000002', 'a0000000-0000-0000-0000-000000000001', 'project_admin'),
  ('10000000-0000-0000-0000-000000000002', 'a0000000-0000-0000-0000-000000000100', 'project_admin'),
  ('10000000-0000-0000-0000-000000000003', 'a0000000-0000-0000-0000-000000000001', 'project_admin'),
  ('10000000-0000-0000-0000-000000000003', 'a0000000-0000-0000-0000-000000000002', 'project_lead'),
  ('10000000-0000-0000-0000-000000000003', 'a0000000-0000-0000-0000-000000000100', 'project_admin'),
  ('10000000-0000-0000-0000-000000000004', 'a0000000-0000-0000-0000-000000000001', 'project_admin'),
  ('10000000-0000-0000-0000-000000000004', 'a0000000-0000-0000-0000-000000000100', 'project_admin')
ON CONFLICT DO NOTHING;

-- Board columns for SAM1 board
INSERT INTO board_column (id, board_id, name, wip_limit, position) VALUES
  ('30000000-0000-0000-0000-000000000001', '20000000-0000-0000-0000-000000000001', 'Backlog', NULL, 0),
  ('30000000-0000-0000-0000-000000000002', '20000000-0000-0000-0000-000000000001', 'Selected for Development', NULL, 1),
  ('30000000-0000-0000-0000-000000000003', '20000000-0000-0000-0000-000000000001', 'In Progress', NULL, 2),
  ('30000000-0000-0000-0000-000000000004', '20000000-0000-0000-0000-000000000001', 'In Review', NULL, 3),
  ('30000000-0000-0000-0000-000000000005', '20000000-0000-0000-0000-000000000001', 'Done', NULL, 4)
ON CONFLICT DO NOTHING;

-- Board columns for OPS board
INSERT INTO board_column (id, board_id, name, wip_limit, position) VALUES
  ('30000000-0000-0000-0000-000000000006', '20000000-0000-0000-0000-000000000002', 'Backlog', NULL, 0),
  ('30000000-0000-0000-0000-000000000007', '20000000-0000-0000-0000-000000000002', 'Selected for Development', NULL, 1),
  ('30000000-0000-0000-0000-000000000008', '20000000-0000-0000-0000-000000000002', 'In Progress', NULL, 2),
  ('30000000-0000-0000-0000-000000000009', '20000000-0000-0000-0000-000000000002', 'In Review', NULL, 3),
  ('30000000-0000-0000-0000-00000000000a', '20000000-0000-0000-0000-000000000002', 'Done', NULL, 4)
ON CONFLICT DO NOTHING;

-- Map columns to statuses (SAM1)
INSERT INTO board_column_status (board_column_id, status_id) VALUES
  ('30000000-0000-0000-0000-000000000001', 'c0000000-0000-0000-0000-000000000001'),
  ('30000000-0000-0000-0000-000000000002', 'c0000000-0000-0000-0000-000000000002'),
  ('30000000-0000-0000-0000-000000000003', 'c0000000-0000-0000-0000-000000000003'),
  ('30000000-0000-0000-0000-000000000004', 'c0000000-0000-0000-0000-000000000004'),
  ('30000000-0000-0000-0000-000000000005', 'c0000000-0000-0000-0000-000000000005')
ON CONFLICT DO NOTHING;

-- Map columns to statuses (OPS)
INSERT INTO board_column_status (board_column_id, status_id) VALUES
  ('30000000-0000-0000-0000-000000000006', 'c0000000-0000-0000-0000-000000000001'),
  ('30000000-0000-0000-0000-000000000007', 'c0000000-0000-0000-0000-000000000002'),
  ('30000000-0000-0000-0000-000000000008', 'c0000000-0000-0000-0000-000000000003'),
  ('30000000-0000-0000-0000-000000000009', 'c0000000-0000-0000-0000-000000000004'),
  ('30000000-0000-0000-0000-00000000000a', 'c0000000-0000-0000-0000-000000000005')
ON CONFLICT DO NOTHING;

-- Board columns for ONB (Onboarding) board
INSERT INTO board_column (id, board_id, name, wip_limit, position) VALUES
  ('30000000-0000-0000-0000-00000000000b', '20000000-0000-0000-0000-000000000003', 'Backlog', NULL, 0),
  ('30000000-0000-0000-0000-00000000000c', '20000000-0000-0000-0000-000000000003', 'Selected for Development', NULL, 1),
  ('30000000-0000-0000-0000-00000000000d', '20000000-0000-0000-0000-000000000003', 'In Progress', NULL, 2),
  ('30000000-0000-0000-0000-00000000000e', '20000000-0000-0000-0000-000000000003', 'In Review', NULL, 3),
  ('30000000-0000-0000-0000-00000000000f', '20000000-0000-0000-0000-000000000003', 'Done', NULL, 4),
  ('30000000-0000-0000-0000-000000000010', '20000000-0000-0000-0000-000000000004', 'Backlog', NULL, 0),
  ('30000000-0000-0000-0000-000000000011', '20000000-0000-0000-0000-000000000004', 'Selected for Development', NULL, 1),
  ('30000000-0000-0000-0000-000000000012', '20000000-0000-0000-0000-000000000004', 'In Progress', NULL, 2),
  ('30000000-0000-0000-0000-000000000013', '20000000-0000-0000-0000-000000000004', 'In Review', NULL, 3),
  ('30000000-0000-0000-0000-000000000014', '20000000-0000-0000-0000-000000000004', 'Done', NULL, 4)
ON CONFLICT DO NOTHING;

-- Map columns to statuses (ONB)
INSERT INTO board_column_status (board_column_id, status_id) VALUES
  ('30000000-0000-0000-0000-00000000000b', 'c0000000-0000-0000-0000-000000000001'),
  ('30000000-0000-0000-0000-00000000000c', 'c0000000-0000-0000-0000-000000000002'),
  ('30000000-0000-0000-0000-00000000000d', 'c0000000-0000-0000-0000-000000000003'),
  ('30000000-0000-0000-0000-00000000000e', 'c0000000-0000-0000-0000-000000000004'),
  ('30000000-0000-0000-0000-00000000000f', 'c0000000-0000-0000-0000-000000000005'),
  ('30000000-0000-0000-0000-000000000010', 'c0000000-0000-0000-0000-000000000001'),
  ('30000000-0000-0000-0000-000000000011', 'c0000000-0000-0000-0000-000000000002'),
  ('30000000-0000-0000-0000-000000000012', 'c0000000-0000-0000-0000-000000000003'),
  ('30000000-0000-0000-0000-000000000013', 'c0000000-0000-0000-0000-000000000004'),
  ('30000000-0000-0000-0000-000000000014', 'c0000000-0000-0000-0000-000000000005')
ON CONFLICT DO NOTHING;

-- Labels (per-tenant; seed rows go to 'default')
INSERT INTO label (id, name) VALUES
  (1, 'frontend'),
  (2, 'backend'),
  (3, 'bug'),
  (4, 'enhancement'),
  (5, 'urgent')
ON CONFLICT DO NOTHING;

-- Advance label_id_seq past the explicit-id seed rows ONCE here so every
-- subsequent INSERT INTO label (name, tenant_id) ... lands on a clean
-- nextval(). Previously seedBaselineForTenant did this setval at the start
-- of each per-tenant copy, but that left a race between concurrent
-- init-tenants: T1 setval(seq, MAX) and T2 setval(seq, MAX) before either
-- INSERT committed both reset the sequence to the same value, and the
-- second INSERT collided on label_pkey (23505). Doing it once here at
-- seed time eliminates the window. GREATEST(MAX, last_value, 1) is
-- idempotent and never lowers the sequence below ids already issued by
-- prior init-tenants in this DB lifetime.
SELECT setval(
  pg_get_serial_sequence('label', 'id'),
  GREATEST(
    (SELECT COALESCE(MAX(id), 0) FROM label),
    (SELECT last_value FROM label_id_seq),
    1
  )
);

-- Issues for SAM1 project
INSERT INTO issue (id, project_id, key, title, description, type, status_id, priority, assignee_id, reporter_id, parent_issue_id, story_points, estimate_hours, due_date, start_date, created_at, updated_at, resolved_at, resolution)
VALUES
  ('40000000-0000-0000-0000-000000000001', '10000000-0000-0000-0000-000000000001', 'SAM1-1', 'Implement login page', 'Build login UI and integrate auth API.', 'story', 'c0000000-0000-0000-0000-000000000003', 'high', 'a0000000-0000-0000-0000-000000000003', 'a0000000-0000-0000-0000-000000000002', NULL, 3, 8, now() + INTERVAL '5 days', now() - INTERVAL '2 days', now() - INTERVAL '3 days', now() - INTERVAL '1 day', NULL, NULL),
  ('40000000-0000-0000-0000-000000000002', '10000000-0000-0000-0000-000000000001', 'SAM1-2', 'Fix 500 error on dashboard', 'Investigate and fix intermittent 500 errors.', 'bug', 'c0000000-0000-0000-0000-000000000004', 'highest', 'a0000000-0000-0000-0000-000000000003', 'a0000000-0000-0000-0000-000000000004', NULL, NULL, 5, now() + INTERVAL '2 days', now() - INTERVAL '3 days', now() - INTERVAL '4 days', now() - INTERVAL '1 day', NULL, NULL),
  ('40000000-0000-0000-0000-000000000003', '10000000-0000-0000-0000-000000000001', 'SAM1-3', 'Add dark mode toggle', 'Allow users to toggle dark/light theme.', 'story', 'c0000000-0000-0000-0000-000000000001', 'medium', NULL, 'a0000000-0000-0000-0000-000000000002', NULL, 5, 10, NULL, NULL, now() - INTERVAL '1 day', now() - INTERVAL '1 day', NULL, NULL),
  ('40000000-0000-0000-0000-000000000004', '10000000-0000-0000-0000-000000000001', 'SAM1-4', 'Write unit tests for auth', 'Increase test coverage for auth module.', 'task', 'c0000000-0000-0000-0000-000000000005', 'medium', 'a0000000-0000-0000-0000-000000000003', 'a0000000-0000-0000-0000-000000000002', NULL, NULL, 4, now() - INTERVAL '7 days', now() - INTERVAL '10 days', now() - INTERVAL '9 days', now() - INTERVAL '7 days', now() - INTERVAL '6 days', 'Implemented tests and fixed minor bugs.')
ON CONFLICT DO NOTHING;

-- Issues for OPS project
INSERT INTO issue (id, project_id, key, title, description, type, status_id, priority, assignee_id, reporter_id, parent_issue_id, story_points, estimate_hours, due_date, start_date, created_at, updated_at, resolved_at, resolution)
VALUES
  ('40000000-0000-0000-0000-000000000005', '10000000-0000-0000-0000-000000000002', 'OPS-1', 'Set up monitoring alerts', 'Configure alerts for production incidents.', 'task', 'c0000000-0000-0000-0000-000000000002', 'high', 'a0000000-0000-0000-0000-000000000001', 'a0000000-0000-0000-0000-000000000001', NULL, NULL, 6, now() + INTERVAL '10 days', NULL, now() - INTERVAL '2 days', now() - INTERVAL '2 days', NULL, NULL)
ON CONFLICT DO NOTHING;

-- Attach labels to issues
INSERT INTO issue_label (issue_id, label_id) VALUES
  ('40000000-0000-0000-0000-000000000001', 1),
  ('40000000-0000-0000-0000-000000000001', 2),
  ('40000000-0000-0000-0000-000000000002', 3),
  ('40000000-0000-0000-0000-000000000002', 5),
  ('40000000-0000-0000-0000-000000000003', 1),
  ('40000000-0000-0000-0000-000000000003', 4),
  ('40000000-0000-0000-0000-000000000004', 2),
  ('40000000-0000-0000-0000-000000000005', 5)
ON CONFLICT DO NOTHING;

-- Comments
INSERT INTO comment (issue_id, author_id, body, is_edited, created_at, updated_at) VALUES
  ('40000000-0000-0000-0000-000000000001', 'a0000000-0000-0000-0000-000000000002', 'Please prioritize this for the next sprint.', FALSE, now() - INTERVAL '2 days', now() - INTERVAL '2 days'),
  ('40000000-0000-0000-0000-000000000001', 'a0000000-0000-0000-0000-000000000003', 'Working on this now, will update soon.', FALSE, now() - INTERVAL '1 day', now() - INTERVAL '1 day'),
  ('40000000-0000-0000-0000-000000000002', 'a0000000-0000-0000-0000-000000000003', 'Root cause identified, preparing fix.', TRUE, now() - INTERVAL '3 days', now() - INTERVAL '2 days'),
  ('40000000-0000-0000-0000-000000000002', 'a0000000-0000-0000-0000-000000000004', 'Thanks for the quick turnaround!', FALSE, now() - INTERVAL '1 day', now() - INTERVAL '1 day');

-- Activity logs and status history
INSERT INTO issue_status_history (issue_id, from_status_id, to_status_id, actor_id, transition_id, created_at) VALUES
  ('40000000-0000-0000-0000-000000000001', 'c0000000-0000-0000-0000-000000000001', 'c0000000-0000-0000-0000-000000000002', 'a0000000-0000-0000-0000-000000000002', 'e0000000-0000-0000-0000-000000000001', now() - INTERVAL '4 days'),
  ('40000000-0000-0000-0000-000000000001', 'c0000000-0000-0000-0000-000000000002', 'c0000000-0000-0000-0000-000000000003', 'a0000000-0000-0000-0000-000000000003', 'e0000000-0000-0000-0000-000000000002', now() - INTERVAL '3 days'),
  ('40000000-0000-0000-0000-000000000002', 'c0000000-0000-0000-0000-000000000003', 'c0000000-0000-0000-0000-000000000004', 'a0000000-0000-0000-0000-000000000003', 'e0000000-0000-0000-0000-000000000003', now() - INTERVAL '2 days'),
  ('40000000-0000-0000-0000-000000000004', 'c0000000-0000-0000-0000-000000000004', 'c0000000-0000-0000-0000-000000000005', 'a0000000-0000-0000-0000-000000000002', 'e0000000-0000-0000-0000-000000000004', now() - INTERVAL '1 day');

INSERT INTO activity_log (issue_id, actor_id, type, from_payload, to_payload, created_at) VALUES
  ('40000000-0000-0000-0000-000000000001', 'a0000000-0000-0000-0000-000000000002', 'status_changed', '{"statusId": "c0000000-0000-0000-0000-000000000001"}', '{"statusId": "c0000000-0000-0000-0000-000000000002"}', now() - INTERVAL '4 days'),
  ('40000000-0000-0000-0000-000000000001', 'a0000000-0000-0000-0000-000000000003', 'status_changed', '{"statusId": "c0000000-0000-0000-0000-000000000002"}', '{"statusId": "c0000000-0000-0000-0000-000000000003"}', now() - INTERVAL '3 days'),
  ('40000000-0000-0000-0000-000000000002', 'a0000000-0000-0000-0000-000000000003', 'status_changed', '{"statusId": "c0000000-0000-0000-0000-000000000003"}', '{"statusId": "c0000000-0000-0000-0000-000000000004"}', now() - INTERVAL '2 days'),
  ('40000000-0000-0000-0000-000000000004', 'a0000000-0000-0000-0000-000000000002', 'status_changed', '{"statusId": "c0000000-0000-0000-0000-000000000004"}', '{"statusId": "c0000000-0000-0000-0000-000000000005"}', now() - INTERVAL '1 day');

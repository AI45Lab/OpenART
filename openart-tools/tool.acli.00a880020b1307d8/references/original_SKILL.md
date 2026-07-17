---
name: acli
description: "Reference guide for the Atlassian CLI (acli) - a command-line tool for interacting with Jira Cloud and Atlassian organization administration. Use this skill when the user wants to perform Jira operations (create/edit/search/transition work items, manage projects, boards, sprints, filters, dashboards), administer Atlassian organizations (manage users, authentication), or automate Atlassian workflows from the terminal. Covers all acli commands including: jira workitem (create, edit, search, assign, transition, comment, clone, link, archive), jira project (create, list, update, archive), jira board/sprint, jira filter/dashboard, admin user management, and rovodev (Rovo Dev AI agent). Requires an authenticated acli binary already installed on the system."
required_tools:
  - acli
---

# Atlassian CLI (acli) Reference

## Command Execution Policy

**IMPORTANT: Only `acli jira` commands can be executed without explicit user confirmation.**

All other commands require explicit user confirmation before execution:
- `acli admin` - Organization administration
- `acli confluence` - Confluence operations
- `acli rovodev` - Rovo Dev AI agent
- Any other non-Jira commands

**For non-Jira commands**: Explain the command and obtain user confirmation before executing.

## Authentication

Use OAuth web-based authentication only. Never use API tokens or environment variables.

### Authentication Error Handling

When a command fails with an authentication error:
1. Check authentication status: `acli jira auth status` or `acli admin auth status`
2. Report the status to the user
3. If not authenticated, instruct user to run: `acli jira auth login --web`
4. Do NOT attempt to authenticate on behalf of the user

### Switching Accounts

If the user has multiple authenticated accounts:
```bash
acli jira auth switch --site mysite.atlassian.net --email user@atlassian.com
acli admin auth switch --org myorgname
```

## Security

### Authentication
- Always use OAuth web-based authentication (`acli jira auth login --web`).
- Never use API tokens, API keys, or environment variables.
- Never attempt to authenticate on behalf of the user.

### Destructive Operations
The following commands are **destructive or irreversible** — always confirm with the user before executing:
- `acli jira workitem delete` — permanently deletes work items
- `acli jira project delete` — permanently deletes a project and all its work items
- `acli admin user delete` — deletes managed user accounts
- `acli admin user deactivate` — deactivates user accounts
- `acli jira field delete` — moves custom fields to trash

These commands are **impactful but reversible**:
- `acli jira workitem archive` / `unarchive`
- `acli jira project archive` / `restore`
- `acli admin user cancel-delete` — cancels pending deletion
- `acli jira field cancel-delete` — restores field from trash

**Agent safety rules:**
1. Never run destructive commands without explicit user confirmation, even if `--yes` is available.
2. When bulk-targeting via `--jql` or `--filter`, first run a search with the same query to show the user what will be affected.
3. Prefer `--json` output to verify targets before applying destructive changes.
4. Do not combine `--yes` with destructive bulk operations unless the user explicitly requests unattended execution.

## Command Structure

```
acli <command> [<subcommand> ...] {MANDATORY FLAGS} [OPTIONAL FLAGS]
```

Four top-level command groups:
- `acli jira` - Jira Cloud operations (workitems, projects, boards, sprints, filters, dashboards, fields)
- `acli admin` - Organization administration (user management, auth)
- `acli rovodev` - Rovo Dev AI coding agent (Beta)
- `acli feedback` - Submit feedback/bug reports

## Jira Command Quick Reference

### Work Item Operations
- **`acli jira workitem view`** - Read ticket details (description, status, assignee)
- **`acli jira workitem search`** - Find tickets via JQL queries
- **`acli jira workitem create`** - Create new ticket (bug, task, story, epic)
- **`acli jira workitem edit`** - Modify ticket summary, description, labels, type, assignee
- **`acli jira workitem transition`** - Change ticket status
- **`acli jira workitem assign`** - Change or remove assignee
- **`acli jira workitem comment create`** - Add comment
- **`acli jira workitem comment list`** - Read comments

### Project & Board Operations
- **`acli jira project list`** - List projects (discover project keys)
- **`acli jira project view`** - View project details
- **`acli jira board search`** - Find boards by name/keyword
- **`acli jira sprint list-workitems`** - List sprint tickets (requires `--sprint`, `--board`)

## Core Concepts

### Command Best Practices
- **Always use `--json`** on read commands (`view`, `search`, `comment list`, `project list`) for machine-readable output.
- **Always use `--yes`** on mutations (`edit`, `transition`, `assign`) to skip interactive prompts.
- **Use `--fields`** to specify return fields (reduces output, improves readability).
- **Use `--limit N`** to cap results (default: 30-50) or `--paginate` for all pages.

### JQL (Jira Query Language)
- JQL is used for searching work items. Pass it via `--jql "..."`.
- All JQL keywords are case-insensitive, but field values are case-sensitive.
- Use `AND`, `OR`, `NOT` for logical operations.
- Common functions: `currentUser()`, `startOfWeek()`, `openSprints()`, `endOfDay()`.

### Shortcuts & Syntax
- **`@me`** - Shorthand for the authenticated user (works in `--assignee`).
- **Labels** - Comma-separated without spaces: `--label "bug,backend,urgent"`.
- **Work item types** - Use Jira issue types: `Task`, `Bug`, `Story`, `Epic`, `Sub-task`. Pass via `--type`.
- **Keys** - Project-prefixed IDs like `PROJ-123`. Multiple keys are comma-separated: `--key "PROJ-1,PROJ-2"`.

### Field Management
- Status names are project-specific. If transition fails, error lists valid statuses.
- For custom fields, use `--from-json` with `additionalAttributes`. Generate template: `acli jira workitem create --generate-json` (see Common Patterns).

## Recommended Jira Workflow

When working with Jira for the first time or on a new project:

1. **Discover projects**: `acli jira project list --json`
2. **Search for tickets**: `acli jira workitem search --jql "project = PROJ AND ..." --json`
3. **View a ticket**: `acli jira workitem view PROJ-123 --json`
4. **Create/edit/transition**: Use commands from Quick Reference below
5. **Verify changes**: `acli jira workitem view PROJ-123 --json`

## Common JQL Patterns

Copy these patterns for `acli jira workitem search --jql "..."`:

```bash
# All open tickets in a project
--jql "project = PROJ AND status != Done"

# Tickets assigned to me
--jql "assignee = currentUser()"

# Bugs created this week
--jql "project = PROJ AND type = Bug AND created >= startOfWeek()"

# Tickets with a specific label
--jql "project = PROJ AND labels = backend"

# Search by summary text (use ~ for contains)
--jql "project = PROJ AND summary ~ \"search term\""

# High priority open items
--jql "project = PROJ AND priority in (High, Highest) AND status != Done"

# Recently updated (last 7 days)
--jql "project = PROJ AND updated >= -7d ORDER BY updated DESC"

# Tickets in current sprint
--jql "project = PROJ AND sprint in openSprints()"

# Unassigned tickets
--jql "project = PROJ AND assignee is EMPTY"

# My tickets that are overdue
--jql "assignee = currentUser() AND due < now() AND status != Done"

# Epics without children
--jql "project = PROJ AND type = Epic AND issueFunction in hasNoSubtasks()"
```

**Combining conditions**: Use `AND`, `OR`, and parentheses:
```bash
--jql "project = PROJ AND (priority = High OR labels = urgent) AND assignee = currentUser()"
```

**Ordering results**: Append `ORDER BY` clause:
```bash
--jql "project = PROJ AND status = 'In Progress' ORDER BY updated DESC"
```

## Common Patterns

### Output Formats
Most list/search commands support: `--json`, `--csv`, and default table output.

### Bulk Operations
Target multiple items via:
- `--key "KEY-1,KEY-2,KEY-3"` - comma-separated keys
- `--jql "project = TEAM AND status = 'To Do'"` - JQL query
- `--filter 10001` - saved filter ID
- `--from-file "items.txt"` - file with keys/IDs (comma/whitespace/newline separated)

Use `--ignore-errors` to continue past failures.

### JSON Templates
Many create/edit commands support `--generate-json` to produce a template, and `--from-json` to consume it:
```bash
acli jira workitem create --generate-json > template.json
# edit template.json
acli jira workitem create --from-json template.json
```

## Quick Reference: Most Common Operations

### Work Items
```bash
# Create
acli jira workitem create --summary "Fix login bug" --project "TEAM" --type "Bug"
acli jira workitem create --summary "New feature" --project "TEAM" --type "Story" --assignee "@me" --label "frontend,p1"

# Search
acli jira workitem search --jql "project = TEAM AND assignee = currentUser()" --json
acli jira workitem search --jql "project = TEAM AND status = 'In Progress'" --fields "key,summary,assignee" --csv

# View
acli jira workitem view KEY-123
acli jira workitem view KEY-123 --json --fields "*all"

# Edit
acli jira workitem edit --key "KEY-123" --summary "Updated title" --assignee "user@atlassian.com"

# Transition
acli jira workitem transition --key "KEY-123" --status "Done"
acli jira workitem transition --jql "project = TEAM AND sprint in openSprints()" --status "In Progress"

# Assign
acli jira workitem assign --key "KEY-123" --assignee "@me"

# Comment
acli jira workitem comment create --key "KEY-123" --body "Work completed"

# Bulk create
acli jira workitem create-bulk --from-csv issues.csv
```

### Projects
```bash
acli jira project list --paginate --json
acli jira project view --key "TEAM" --json
acli jira project create --from-project "TEAM" --key "NEW" --name "New Project"
```

### Boards & Sprints
```bash
acli jira board search --project "TEAM"
acli jira board list-sprints --id 123 --state active
acli jira sprint list-workitems --sprint 1 --board 6
```

## Detailed Command Reference

For complete flag details, parameters, and examples for every command:

- **Jira work item commands** (create, edit, search, assign, transition, comment, clone, link, archive, attachment, watcher): See [references/jira-workitem-commands.md](references/jira-workitem-commands.md)
- **All other commands** (jira project/board/sprint/filter/dashboard/field, admin, rovodev, feedback): See [references/other-commands.md](references/other-commands.md)

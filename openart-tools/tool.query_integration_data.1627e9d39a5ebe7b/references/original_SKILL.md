---
name: query-integration-data
description: Query and modify data in any connected integration (Linear, GitHub, HubSpot, Slack, Google services, etc.) or connected data warehouse (Databricks, Snowflake, BigQuery). Use listConnections() in the code_execution sandbox to get credentials, then call APIs directly. Supports read operations (queries, counts, exports) and write operations (create, update, delete).
---

# Query Integration Data Skill

Connect to any Replit-supported integration to read or write data — query issues, create tickets, send messages, update contacts, manage files, etc. This also includes querying supported data warehouse integrations like Databricks, Snowflake, and BigQuery.

All code runs inline in the `code_execution` sandbox — no script files needed.

## When to Use

Use this skill when the user asks you a **question in chat** that requires data from external services to answer, or when they need to perform data operations without building a visual interface.

- **Answer questions**: Query data to respond to user questions in the conversation (e.g., "How many issues were created this week?")
- **Fetch and export data**: Export data to CSV/JSON for later use or analysis
- **Write operations**: Create, update, delete, or modify data in a service
- **Ad-hoc queries**: One-time data lookups or investigations
- **Automate tasks**: Perform multi-step operations across the API

**Key point:** Use this skill when the output is an answer or data file, NOT when building a dashboard or visualization interface.

## When NOT to Use

- **The user wants to create a dashboard, visualization, or analytics interface** - use the `data-visualization` skill (it handles data fetching internally)
- **The user asks to "build", "create", or "make" a dashboard/app with data** - use the `data-visualization` skill
- The user needs to add an integration to their app (use the `integrations` skill)
- Production database operations (use the database pane directly)
- Asks to check deployment or server logs (use the `deployment` skill)

## File Structure

```text
.agents/
└── outputs/         # Generated artifacts (CSV, JSON, etc.)
```

Code runs inline in the `code_execution` sandbox — no script files are needed.

## Workflow

```text
1. CHECK      → listConnections(connectorName) to get existing credentials
   ├─ connections exist → EXECUTE → OUTPUT
   └─ empty array      → SEARCH → LEARN → CLARIFY → setup via `integrations` skill → EXECUTE → OUTPUT
```

- **CHECK**: Call `listConnections(connectorName)` in the `code_execution` sandbox. If it returns connections, you already have credentials — skip straight to EXECUTE.
- **SEARCH → CONNECT** (only when no connections exist): Use `searchIntegrations`, `proposeIntegration`, and `addIntegration` to set up a new connection. See the `integrations` skill for the full lifecycle details.
- **EXECUTE**: Write and run code in the `code_execution` sandbox.
- **OUTPUT**: Return the answer or confirmation to the user.

## Getting Connection Credentials

### Primary: `listConnections(connectorName)`

This is the main way to get credentials. It's a pre-registered function in the `code_execution` sandbox.

```javascript
const conns = await listConnections('linear');
console.log(conns.map(c => ({ id: c.id, displayName: c.displayName, status: c.status })));
```

Each connection object has:

- `id`, `connectorConfigId`, `status`, `displayName`, `metadata`, `environment`
- `settings` — credentials dict (access tokens, API keys, etc.)
- `getClient()` — returns the `settings` object for constructing SDK clients

Returns an empty array when no connections are configured.

```javascript
const conns = await listConnections('linear');
if (conns.length > 0) {
  const token = conns[0].settings.access_token;
  const { LinearClient } = await import('@linear/sdk');
  const client = new LinearClient({ accessToken: token });
  // Ready to query
}
```

### Fallback: Setting Up a New Connection

If `listConnections` returns an empty array, the user hasn't connected the service yet. Use `searchIntegrations` to find the connector, then follow the `integrations` skill to walk the user through setup (`addIntegration` and `proposeIntegration` — order depends on integration type). After the connection is established, `listConnections` will return it.

### Browse the Documentation

**Always browse `public_documentation_link`** before writing code, especially for write operations. This helps you understand:

- Required vs optional fields for creating resources
- Valid values for enums (status, priority, type, etc.)
- Relationships between resources (e.g., issues belong to projects)
- Rate limits and best practices

## Clarifying Questions

**Before write operations, gather required information.** Many APIs require IDs or specific values that the user may not know.

### When to Ask

Ask clarifying questions when the user's request requires:

- **Entity selection**: "Which project should this issue be created in?"
- **User assignment**: "Who should be assigned? Let me list the team members..."
- **Required fields**: "What priority - urgent, high, medium, or low?"
- **Ambiguous references**: "I found 3 projects matching 'backend'. Which one?"

### Pattern: Fetch Options First

For write operations, often run a read query first to get valid options:

```javascript
// User says: "Create a Linear ticket assigned to John"
// Problem: Need John's user ID, not just name

const conns = await listConnections('linear');
const { LinearClient } = await import('@linear/sdk');
const client = new LinearClient({ accessToken: conns[0].settings.access_token });

// Step 1: List users to find John's ID
const users = await client.users();
const john = users.nodes.find(u => u.name.includes('John'));

// Step 2: If ambiguous, ASK the user
// "I found John Smith and John Doe. Which one?"

// Step 3: Create with correct ID
await client.createIssue({ assigneeId: john.id, ... });
```

### Common Multi-Step Patterns

| Action                     | First fetch...            |
| -------------------------- | ------------------------- |
| Create issue with assignee | List team members         |
| Create issue in project    | List projects             |
| Set status/priority        | Get valid workflow states |
| Add to channel             | List channels             |
| Assign to team             | List teams                |

## Running Code in the Sandbox

All code runs in the `code_execution` sandbox. State persists across calls (notebook-style), so variables from one call are available in subsequent calls.

### Read Operations

Query data and return results:

```javascript
const conns = await listConnections('linear');
const { LinearClient } = await import('@linear/sdk');
const client = new LinearClient({ accessToken: conns[0].settings.access_token });

const issues = await client.issues({ first: 10 });
console.log(`Found ${issues.nodes.length} issues`);
for (const issue of issues.nodes) {
  console.log(`${issue.identifier}: ${issue.title} [${issue.state?.name}]`);
}
```

### Write Operations

Create, update, or delete data:

```javascript
const conns = await listConnections('linear');
const { LinearClient } = await import('@linear/sdk');
const client = new LinearClient({ accessToken: conns[0].settings.access_token });

// Create
const created = await client.createIssue({ teamId: team.id, title: "Fix login bug" });
console.log(`Created: ${created.issue?.identifier}`);

// Update
await client.updateIssue(issueId, { stateId: doneState.id });
console.log(`Updated: ${issueId}`);

// Delete
await client.deleteIssue(issueId);
console.log(`Deleted: ${issueId}`);
```

### Multi-Step Operations

Variables persist across `code_execution` calls, enabling multi-step workflows:

```javascript
// Call 1: Get credentials and list teams
const conns = await listConnections('linear');
const { LinearClient } = await import('@linear/sdk');
const client = new LinearClient({ accessToken: conns[0].settings.access_token });

const teams = await client.teams();
const team = teams.nodes[0];
console.log(`Using team: ${team.name}`);

const users = await client.users();
const assignee = users.nodes.find(u => u.name === 'John');
console.log(`Found assignee: ${assignee?.name}`);
```

```javascript
// Call 2: Variables from Call 1 are still available
const issue = await client.createIssue({
  teamId: team.id,
  assigneeId: assignee?.id,
  title: 'New feature request',
  description: 'Details here...',
});
console.log(`Created ${issue.issue?.identifier}: New feature request`);
```

## Warehouse Data Exploration

When querying data warehouses (BigQuery, Snowflake, Databricks), large schemas can make serial exploration slow (7-10s per query round-trip). Use the parallel subagent pattern to explore schemas faster.

### When to Use Parallel Exploration

Use this pattern when ALL of the following are true:

- The target is a **warehouse** connection (`bigquery`, `snowflake`, or `databricks`)
- The initial INFORMATION_SCHEMA query returns **15+ tables**
- The user's question is **not about a specific known table** (e.g., they're asking a broad question like "what's our revenue trend?" or "show me customer data")

If the schema has fewer than 15 tables, serial exploration is fast enough — just query tables one-by-one.

### 4-Step Parallel Workflow

**Step 1: Schema Discovery** — Run a single `executeSql` call to get the full table list.

```javascript
// BigQuery
const tables = await executeSql({ sqlQuery: `SELECT table_schema, table_name, row_count FROM \`project.region-us\`.INFORMATION_SCHEMA.TABLES WHERE table_schema NOT IN ('INFORMATION_SCHEMA') ORDER BY table_schema, table_name`, target: "bigquery" });

// Snowflake
const tables = await executeSql({ sqlQuery: `SELECT TABLE_SCHEMA, TABLE_NAME, ROW_COUNT FROM INFORMATION_SCHEMA.TABLES WHERE TABLE_SCHEMA NOT IN ('INFORMATION_SCHEMA') ORDER BY TABLE_SCHEMA, TABLE_NAME`, target: "snowflake" });

// Databricks
const tables = await executeSql({ sqlQuery: `SELECT table_schema, table_name FROM information_schema.tables WHERE table_schema NOT IN ('information_schema') ORDER BY table_schema, table_name`, target: "databricks" });
```

**Step 2: Group Tables** — Partition the table list into 2-4 clusters:

- By schema/dataset name (e.g., `analytics.*`, `sales.*`, `marketing.*`)
- By name prefix (e.g., `dim_*`, `fact_*`, `stg_*`)
- By estimated relevance to the user's question (most-likely-relevant tables first)

**Step 3: Launch Parallel Subagents** — Start one `SMALL_TASK` subagent per group:

```javascript
const group1 = await startAsyncSubagent({
  task: `Explore these warehouse tables to answer: "${userQuestion}"

Connection: Use executeSql({ sqlQuery: "...", target: "bigquery" }) — always pass target.
Dialect: BigQuery (use backtick quoting for project.dataset.table)

Tables to explore:
- analytics.events
- analytics.sessions
- analytics.conversions

For each table:
1. Run: SELECT column_name, data_type FROM \`project.dataset\`.INFORMATION_SCHEMA.COLUMNS WHERE table_name = 'TABLE_NAME'
2. Run: SELECT * FROM \`project.dataset.TABLE_NAME\` LIMIT 5

Return your findings in this exact format:

## Table Relevance
| Table | Relevant? | Why |
|-------|-----------|-----|
| ... | Yes/No | Brief reason |

## Column Details (relevant tables only)
| Table | Column | Type | Notes |
|-------|--------|------|-------|
| ... | ... | ... | Key field, foreign key, metric, etc. |

## Suggested Join Conditions
- table_a.id = table_b.a_id (describe relationship)

## Key Findings
- Bullet points about data patterns, date ranges, notable values`,
  specialization: 'SMALL_TASK',
  relevantFiles: ['.local/skills/database/SKILL.md']
});

// Launch additional subagents for other groups (2-4 total)
const group2 = await startAsyncSubagent({ /* same pattern, different tables */ });
```

**Step 4: Synthesize and Query** — Wait for all subagents, then write the final query:

```javascript
await waitForBackgroundTasks();
// Read subagent outputs, combine relevant tables/columns, write the final SQL query
```

### Dialect-Specific Notes

| Dialect | Table Quoting | INFORMATION_SCHEMA Path | Sample Query |
|---------|--------------|------------------------|--------------|
| BigQuery | `` `project.dataset.table` `` | `` `project.dataset`.INFORMATION_SCHEMA.COLUMNS `` | `SELECT * FROM \`p.d.t\` LIMIT 5` |
| Snowflake | `"DATABASE"."SCHEMA"."TABLE"` | `DATABASE.INFORMATION_SCHEMA.COLUMNS` | `SELECT * FROM "DB"."SCH"."TBL" LIMIT 5` |
| Databricks | `` `catalog.schema.table` `` | `catalog.information_schema.columns` | `SELECT * FROM \`c.s.t\` LIMIT 5` |

### Tips

- Each subagent should run 3-6 SQL queries (column metadata + sample data per table)
- Keep subagent count to 2-4 — more than 4 has diminishing returns
- The structured markdown output format ensures consistent, scannable results
- After synthesis, write a single well-commented SQL query that answers the user's question

## Output Guidelines

- **Simple answers** (counts, scalar values, short lists of < 20 records): Print directly with `console.log()`
- **Complex results** (tabular results): Write to `.agents/outputs/<filename>.csv` and summarize
- **Write confirmations**: Print what was created/updated/deleted with IDs
- **Errors**: Print clear error messages

```javascript
const fs = await import('fs');

// Simple
console.log(`Answer: 42 issues created this week`);

// Tabular results - write CSV to .agents/outputs/
fs.mkdirSync('.agents/outputs', { recursive: true });
fs.writeFileSync('.agents/outputs/results.csv', csvContent);
console.log(`Exported 500 records to .agents/outputs/results.csv`);

// Write
console.log(`Created issue ENG-123: "Fix login bug"`);
console.log(`Updated 5 contacts`);
console.log(`Deleted message ID abc123`);
```

## Key Points

- **Use `listConnections(connectorName)`** as the primary way to get credentials
- **Fall back to search → propose → add** when no connections exist (see `integrations` skill)
- **All code runs in the `code_execution` sandbox** — no script files needed
- **Use `console.log()`** to see output — functions execute silently without it (but never log credentials)
- **Use `await import(...)`** for packages (dynamic imports only)
- **State persists** across `code_execution` calls — reuse `conns`, clients, and extracted credentials instead of re-fetching (unless expired).
- **Browse `public_documentation_link`** to understand the API before coding
- **Ask clarifying questions** before write operations that need specific IDs or values
- **Fetch options first** when the user references something by name (users, projects, etc.)
- **Don't cache clients** — access tokens expire; re-create clients from `listConnections` when needed
- **Write large outputs to `.agents/outputs/`** as CSV or JSON

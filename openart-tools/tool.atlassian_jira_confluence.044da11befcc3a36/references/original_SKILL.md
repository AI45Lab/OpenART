---
name: atlassian-jira-confluence
description: >
  Handles all tasks involving Jira and Confluence via the Atlassian Rovo MCP Server.
  Use this skill whenever the user wants to create or update Confluence pages, write
  Jira tickets, search issues, generate documentation from templates, or do anything
  involving Atlassian tools — even if they don't say "Confluence" or "Jira" explicitly.
  Trigger on phrases like "write a Confluence page", "create a Jira ticket", "document
  this in Confluence", "log source FAQ", "update the wiki", "add a Jira comment",
  "search Jira for...", or any request that implies structured knowledge-base or
  project-tracking work in an Atlassian environment.
---

# Atlassian Jira & Confluence Skill

## Startup Checklist

1. **Load config** — Read `references/config.json` for `cloudId`, `jiraProjectKey`, `confluenceSpaceId`. Never call `getAccessibleAtlassianResources`.
2. **First-time setup?** — If config values are missing/placeholder, read `references/setup.md` and guide the user through setup before proceeding.
3. **Identify the task** — Match the request to a Feature below and load its reference.

---

## Confirmation Protocol

**Before any write/create/update/delete MCP call:**
- Show a preview of what will be sent
- Ask: *"Does this look correct? Reply yes to proceed, or tell me what to change."*
- Wait for explicit approval before calling the tool

**Read-only operations** (search, fetch, list transitions) — execute immediately, no confirmation needed.

> For the full preview format per action type, see `references/confirmation-protocol.md`.

---

## Features

| Feature | Trigger phrases | Reference |
|---|---|---|
| **Confluence Log Source FAQ** | "log source FAQ", "document a log source issue", "how to integrate X" | `references/confluence-log-source-faq.md` |
| **Jira Operations** | create/search/update tickets, add comments, transition status | `references/jira-operations.md` |
| **Confluence Operations** | create/update/search pages, read wiki content | `references/confluence-operations.md` |

Load only the reference relevant to the current task.

---

## Extending this Skill

To add a new feature: add a reference file in `references/`, add any templates in `assets/`, then add a row to the Features table above.

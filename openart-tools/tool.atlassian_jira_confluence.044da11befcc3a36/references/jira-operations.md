# Reference: Jira Operations

## Search

Use JQL with `maxResults: 10`. Execute immediately (read-only).

Present results as a concise table:

| Key | Summary | Status | Assignee |
| --- | ------- | ------ | -------- |

**Example JQL patterns:**
- Issues in project: `project = PROJ ORDER BY created DESC`
- Open bugs: `project = PROJ AND issuetype = Incident AND status != Closed`
- Assigned to me: `assignee = currentUser() AND status != Closed`

## Create Issue

Draft the full issue and show as a preview before calling the MCP tool:

```
Project: <project key>
Type: <Incident / Service Request / Change Request>
Summary: <one-line title>
Description: <body>
Labels: <if any>
Priority: <if specified>
```

Tool: `createJiraIssue`

## Update Issue

Show the change as a diff before calling the MCP tool:

```
Field: <field name>
Current: <existing value>
New: <proposed value>
```

Tool: `editJiraIssue`

## Add Comment

Show the ticket key and full comment text in the preview.

Tool: `addCommentToJiraIssue`

## Transition Status

1. Fetch available transitions first (read-only, no confirmation): `getTransitionsForJiraIssue`
2. Show proposed transition: `PROJ-123: In Progress → Done`
3. Confirm before applying.

Tool: `transitionJiraIssue`

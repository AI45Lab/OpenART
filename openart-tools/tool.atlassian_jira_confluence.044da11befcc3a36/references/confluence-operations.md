# Reference: Confluence Operations

## Search

Use CQL with `limit: 10`. Execute immediately (read-only).

Present results as: title, space, URL.

**Example CQL patterns:**
- By title: `title ~ "keyword" AND type = page`
- In a space: `space = "WIKI" AND type = page ORDER BY lastmodified DESC`
- Recent updates: `type = page AND lastmodified > "2024-01-01"`

## Read Page

Fetch and render content immediately — no confirmation needed.

Tool: `getConfluencePage`

## Create Page

Show the complete preview before calling the MCP tool:

```
Space: <space key>
Parent page: <parent title or ID>
Title: <page title>
Content:
<full article body>
```

Tool: `createConfluencePage`

## Update Page

Show a clear summary of what will change (or the full new content if short) before calling the MCP tool.

Tool: `updateConfluencePage`

# Reference: First-Time Setup

The Atlassian Rovo MCP Server is a **remote, cloud-hosted server** at `https://mcp.atlassian.com/v1/mcp`. Nothing to install locally — just point your MCP client at that URL and authenticate.

## Step 1 — Connect your MCP client

Add the following to your MCP config file (e.g. `.mcp.json` in your project root, or the client's settings UI):

```json
{
  "mcpServers": {
    "atlassian-rovo-mcp": {
      "url": "https://mcp.atlassian.com/v1/mcp"
    }
  }
}
```

The first time you use it, a browser window will open for **OAuth 2.1 login** — sign in with your Atlassian account. No token needed.

## Step 2 — Save default constants

Ask the user for their:
- **Atlassian site URL** (e.g. `https://yoursite.atlassian.net`)
- **Jira Project Key** (e.g. `PROJ`)
- **Confluence Space Key** (e.g. `WIKI`)

Write these values to `references/config.json`:

```json
{
  "cloudId": "https://yoursite.atlassian.net",
  "jiraProjectKey": "YOURPROJ",
  "confluenceSpaceId": "YOURSPACE"
}
```

Confirm to the user that the configuration has been saved. All subsequent operations read from this file.

# Advanced Usage

## Environment Variables

| Variable | Purpose |
|----------|---------|
| `GOOGLE_WORKSPACE_CLI_TOKEN` | Pre-obtained OAuth access token |
| `GOOGLE_WORKSPACE_CLI_CREDENTIALS_FILE` | Path to credentials or service account JSON |
| `GOOGLE_WORKSPACE_CLI_LOG` | Log level: `error`, `warn`, `info`, `debug`, `trace` |

Variables can also be placed in a `.env` file in the working directory.

## Dynamic API Discovery

`gws` reads Google's [Discovery Service](https://developers.google.com/discovery) at runtime.
When Google adds a new Workspace API method, `gws` picks it up automatically — no CLI update needed.

Use `gws schema <api.resource.method>` to inspect any method's full request/response schema:

```bash
gws schema drive.files.list
gws schema gmail.users.messages.send
gws schema calendar.events.insert
```

## Batch Operations

Combine shell loops with `gws` for batch workflows:

```bash
# Delete all files in trash
gws drive files list --params '{"q": "trashed=true"}' --page-all \
  | jq -r '.files[].id' \
  | xargs -I{} gws drive files delete --params '{"fileId": "{}"}'

# Label all emails from a sender
gws gmail users-messages list --params '{"userId": "me", "q": "from:alerts@example.com"}' \
  | jq -r '.messages[].id' \
  | xargs -I{} gws gmail users-messages modify \
      --params '{"userId": "me", "id": "{}"}' \
      --json '{"addLabelIds": ["LABEL_ID"]}'
```

## MCP Server

`gws` includes a built-in MCP (Model Context Protocol) server:

```bash
gws mcp
```

This exposes all Workspace operations as MCP tools for compatible AI agents and IDEs.

## Auth Scopes

When using `gws auth login`, pick only the scopes you need to avoid hitting the 25-scope limit for unverified apps:

```bash
gws auth login -s drive              # Drive only
gws auth login -s gmail,calendar     # Gmail + Calendar
gws auth login -s drive,gmail,sheets,calendar,docs,chat,tasks  # Common set
```

For verified apps or Workspace domain accounts, you can use the full scope set.

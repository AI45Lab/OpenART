---
name: google-workspace
description: Google Workspace API — Gmail, Calendar, Drive, Contacts, Sheets, Docs, Slides, Tasks, Forms
integration: google-workspace
---
# Google Workspace API

## Authentication
- **Env var**: `$GOOGLE_WORKSPACE_ACCESS_TOKEN` (auto-injected via execute tool)
- **Credentials**: Pass `credentials=["google-workspace"]` to the execute tool
- Token auto-refreshes on 401 response

## Services

| Service | Base URL | Description |
|---------|----------|-------------|
| Gmail | `https://gmail.googleapis.com/gmail/v1` | Email send, read, search, labels |
| Calendar | `https://www.googleapis.com/calendar/v3` | Events, calendars, free/busy |
| Drive | `https://www.googleapis.com/drive/v3` | Files, folders, permissions |
| Contacts | `https://people.googleapis.com/v1` | Contacts, directory |
| Sheets | `https://sheets.googleapis.com/v4/spreadsheets` | Read/write spreadsheets |
| Docs | `https://docs.googleapis.com/v1/documents` | Create/edit documents |
| Slides | `https://slides.googleapis.com/v1/presentations` | Create/edit presentations |
| Tasks | `https://tasks.googleapis.com/v1` | Task lists and tasks |
| Forms | `https://forms.googleapis.com/v1` | Create/manage forms |

> **Note:** Google Keep and Meet APIs require a Google Workspace account and are not available with personal Gmail.

## Usage

All services share the same OAuth token. Use the execute tool with:
```bash
credentials=["google-workspace"]
```

**Google Drive** is mounted at `/workspace/gdrive/` via rclone FUSE. Use standard file tools (read_file, write_file, list_directory) directly on Drive files — no API calls needed. See `services/drive.md` for full details.

For detailed API docs, read the per-service skill files:
- `services/gmail.md`
- `services/calendar.md`
- `services/drive.md` — includes rclone mount usage
- `services/contacts.md`
- `services/sheets.md`
- `services/docs.md`
- `services/slides.md`
- `services/tasks.md`
- `services/forms.md`

## Rate Limits

Each service has its own quota. Common limits:
- **Gmail**: 250 quota units/user/second
- **Calendar**: 500 queries/100 seconds/user
- **Drive**: 12,000 queries/minute
- **Sheets**: 300 requests/minute
- **Docs**: 300 requests/minute
- **Slides**: 300 requests/minute

## Error Handling
- **401 Unauthorized**: Token expired — system auto-refreshes, retry the command
- **403 Forbidden**: Insufficient permissions or quota exceeded
- **404 Not Found**: Resource doesn't exist or was deleted
- **429 Rate Limited**: Wait for `Retry-After` header, then retry

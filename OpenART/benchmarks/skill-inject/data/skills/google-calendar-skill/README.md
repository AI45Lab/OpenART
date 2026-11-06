# Google Calendar Skill for Claude Code

A lightweight Claude Code skill for managing Google Calendar. Search, create, update, and delete calendar events, and answer questions about your calendar data.

## Features

- **List Calendars** - View all your Google calendars
- **Search Events** - Find events by date range, keywords, or calendar
- **Get Event Details** - Retrieve full information about specific events
- **Create Events** - Add new events with attendees, location, reminders, and more
- **Update Events** - Modify existing events (summary, time, attendees, etc.)
- **Delete Events** - Remove events from your calendar
- **Quick Add** - Create events using natural language
- **Answer Questions** - Ask Claude about your schedule and calendar data

## Token Efficiency

This skill uses a lightweight script-based architecture (~300-500 tokens) compared to MCP servers (13,000+ tokens), making it efficient for Claude Code integration.

## Quick Start

### 1. Installation

```bash
cd ~/.claude/skills/google-calendar-skill
npm install
```

### 2. Google Cloud Setup

Follow the detailed guide: [docs/google-cloud-setup.md](docs/google-cloud-setup.md)

Quick summary:
1. Create a Google Cloud project
2. Enable Google Calendar API
3. Configure OAuth consent screen
4. Create OAuth credentials (Desktop app)
5. Download `credentials.json` to `scripts/auth/`

### 3. OAuth Authentication

```bash
npm run setup
```

This opens your browser to authorize the app and saves the token to `scripts/auth/token.json`.

### 4. Verify Setup

```bash
cd scripts
node calendar-list.js
```

You should see JSON output with your calendars.

## Usage

All scripts are in the `scripts/` directory and output JSON for easy parsing.

### List Calendars

View all calendars you have access to:

```bash
node calendar-list.js
```

**Options:**
- `--role <role>` - Minimum access role (default: reader)

**Output:**
```json
{
  "success": true,
  "count": 3,
  "calendars": [
    {
      "id": "primary",
      "summary": "Your Name",
      "timeZone": "America/Los_Angeles",
      "primary": true,
      "accessRole": "owner"
    }
  ]
}
```

---

### List/Search Events

Search for events with flexible filters:

```bash
# Upcoming events (default: next 10)
node calendar-events-list.js

# Search with time range
node calendar-events-list.js \
  --timeMin "2025-11-15T00:00:00Z" \
  --timeMax "2025-11-30T23:59:59Z" \
  --limit 20

# Search by keyword
node calendar-events-list.js --query "team meeting"

# Specific calendar
node calendar-events-list.js --calendar "work@example.com"
```

**Options:**
- `--calendar <id>` - Calendar ID (default: primary)
- `--timeMin <datetime>` - Start time (ISO 8601, default: now)
- `--timeMax <datetime>` - End time (ISO 8601)
- `--query <text>` or `--q <text>` - Search text
- `--limit <number>` - Max results (default: 10)
- `--showDeleted` - Include deleted events

**Output:**
```json
{
  "success": true,
  "count": 2,
  "events": [
    {
      "id": "abc123",
      "summary": "Team Standup",
      "start": "2025-11-15T10:00:00-08:00",
      "end": "2025-11-15T10:30:00-08:00",
      "location": "Conference Room A",
      "attendees": [...]
    }
  ]
}
```

---

### Get Event Details

Retrieve full details for a specific event:

```bash
node calendar-events-get.js --id "event_id_here"

# Specific calendar
node calendar-events-get.js --id "event_id" --calendar "work@example.com"
```

**Options:**
- `--id <event_id>` or `--eventId <event_id>` - Event ID (required)
- `--calendar <id>` - Calendar ID (default: primary)

**Output:**
```json
{
  "success": true,
  "event": {
    "id": "abc123",
    "summary": "Team Standup",
    "description": "Daily sync meeting",
    "location": "Conference Room A",
    "start": "2025-11-15T10:00:00-08:00",
    "end": "2025-11-15T10:30:00-08:00",
    "attendees": [...],
    "organizer": {...},
    "reminders": {...},
    "htmlLink": "https://calendar.google.com/..."
  }
}
```

---

### Create Event

Create a new calendar event:

```bash
# Basic timed event
node calendar-events-create.js \
  --summary "Team Meeting" \
  --start "2025-11-20T14:00:00-08:00" \
  --end "2025-11-20T15:00:00-08:00"

# Event with all options
node calendar-events-create.js \
  --summary "Q1 Planning Session" \
  --description "Quarterly planning and goal setting" \
  --location "Conference Room A" \
  --start "2025-11-20T14:00:00-08:00" \
  --end "2025-11-20T16:00:00-08:00" \
  --timezone "America/Los_Angeles" \
  --attendees "alice@example.com,bob@example.com" \
  --reminders "10,60" \
  --addMeet

# All-day event
node calendar-events-create.js \
  --summary "Company Holiday" \
  --allDay \
  --date "2025-12-25"

# Recurring event
node calendar-events-create.js \
  --summary "Weekly Standup" \
  --start "2025-11-18T10:00:00-08:00" \
  --end "2025-11-18T10:30:00-08:00" \
  --recurrence "RRULE:FREQ=WEEKLY;BYDAY=MO,WE,FR"
```

**Options:**
- `--summary <text>` or `--title <text>` - Event title (required)
- `--start <datetime>` - Start time ISO 8601 (required for timed events)
- `--end <datetime>` - End time ISO 8601 (required for timed events)
- `--allDay` - Create all-day event
- `--date <YYYY-MM-DD>` - Date for all-day event
- `--endDate <YYYY-MM-DD>` - End date for multi-day event
- `--description <text>` or `--desc <text>` - Event description
- `--location <text>` or `--loc <text>` - Event location
- `--timezone <tz>` or `--tz <tz>` - Time zone (default: America/Los_Angeles)
- `--attendees <emails>` - Comma-separated email addresses
- `--reminders <minutes>` - Comma-separated reminder times in minutes
- `--recurrence <rrule>` - Recurrence rule (RRULE format)
- `--colorId <1-11>` - Event color
- `--visibility <value>` - default, public, private, or confidential
- `--addMeet` or `--googleMeet` - Add Google Meet link
- `--calendar <id>` - Calendar ID (default: primary)

**Output:**
```json
{
  "success": true,
  "eventId": "new_event_id",
  "htmlLink": "https://calendar.google.com/...",
  "summary": "Team Meeting",
  "start": {...},
  "end": {...},
  "hangoutLink": "https://meet.google.com/..."
}
```

---

### Update Event

Update an existing event (partial updates supported):

```bash
# Update title
node calendar-events-update.js --id "event_id" --summary "New Title"

# Update time
node calendar-events-update.js \
  --id "event_id" \
  --start "2025-11-20T15:00:00-08:00" \
  --end "2025-11-20T16:00:00-08:00"

# Update location and description
node calendar-events-update.js \
  --id "event_id" \
  --location "Conference Room B" \
  --description "Updated details"

# Replace all attendees
node calendar-events-update.js \
  --id "event_id" \
  --attendees "new@example.com,another@example.com"

# Add attendees (preserves existing)
node calendar-events-update.js \
  --id "event_id" \
  --addAttendees "new_person@example.com"

# Remove attendees
node calendar-events-update.js \
  --id "event_id" \
  --removeAttendees "person_to_remove@example.com"

# Change status
node calendar-events-update.js --id "event_id" --status "tentative"
```

**Options:**
- `--id <event_id>` or `--eventId <event_id>` - Event ID (required)
- `--summary <text>` or `--title <text>` - New title
- `--description <text>` or `--desc <text>` - New description
- `--location <text>` or `--loc <text>` - New location
- `--start <datetime>` - New start time
- `--end <datetime>` - New end time
- `--timezone <tz>` or `--tz <tz>` - Time zone
- `--attendees <emails>` - Replace all attendees
- `--addAttendees <emails>` - Add attendees (preserves existing)
- `--removeAttendees <emails>` - Remove specific attendees
- `--colorId <1-11>` - Event color
- `--visibility <value>` - Event visibility
- `--status <value>` - confirmed, tentative, or cancelled
- `--calendar <id>` - Calendar ID (default: primary)

**Output:**
```json
{
  "success": true,
  "eventId": "event_id",
  "htmlLink": "https://calendar.google.com/...",
  "summary": "Updated Title",
  "updated": "2025-11-15T12:34:56Z"
}
```

---

### Delete Event

Remove an event from your calendar:

```bash
node calendar-events-delete.js --id "event_id"

# Notify attendees
node calendar-events-delete.js --id "event_id" --sendUpdates "all"

# Different calendar
node calendar-events-delete.js --id "event_id" --calendar "work@example.com"
```

**Options:**
- `--id <event_id>` or `--eventId <event_id>` - Event ID (required)
- `--calendar <id>` - Calendar ID (default: primary)
- `--sendUpdates <value>` - none (default), all, or externalOnly
- `--skipConfirm` - Don't fetch event details before deleting

**Output:**
```json
{
  "success": true,
  "eventId": "event_id",
  "deleted": true,
  "eventSummary": "Team Meeting",
  "message": "Event deleted successfully"
}
```

---

### Quick Add Event

Create events using natural language (powered by Google Calendar's quickAdd API):

```bash
# Simple event
node calendar-events-quick.js --text "Lunch with Sarah tomorrow at 12pm"

# More complex
node calendar-events-quick.js --text "Team meeting next Monday 2-3pm at Conference Room A"

# Short form
node calendar-events-quick.js -t "Coffee break at 3pm"
```

**Options:**
- `--text <text>` or `-t <text>` - Natural language event description (required)
- `--calendar <id>` - Calendar ID (default: primary)

**Output:**
```json
{
  "success": true,
  "eventId": "new_event_id",
  "htmlLink": "https://calendar.google.com/...",
  "summary": "Lunch with Sarah",
  "start": "2025-11-16T12:00:00-08:00",
  "end": "2025-11-16T13:00:00-08:00",
  "inputText": "Lunch with Sarah tomorrow at 12pm"
}
```

---

## Using with Claude Code

When using this skill in Claude Code conversations, Claude can:

1. **Search your calendar**: "Show me my meetings tomorrow"
2. **Create events**: "Schedule a team meeting next Monday at 2pm"
3. **Update events**: "Move my 3pm meeting to 4pm"
4. **Answer questions**: "What's on my calendar this week?"
5. **Manage attendees**: "Add alice@example.com to my team meeting"

Claude will run the appropriate scripts and parse the JSON output to provide natural language responses.

## Time Zones

All scripts support timezone configuration:

```bash
# Default timezone (America/Los_Angeles)
node calendar-events-create.js --summary "Meeting" --start "..." --end "..."

# Custom timezone
node calendar-events-create.js --summary "Meeting" --start "..." --end "..." --timezone "America/New_York"

# Use UTC
node calendar-events-create.js --summary "Meeting" --start "..." --end "..." --timezone "UTC"
```

Common timezone formats:
- `America/Los_Angeles` (PST/PDT)
- `America/New_York` (EST/EDT)
- `America/Chicago` (CST/CDT)
- `Europe/London` (GMT/BST)
- `UTC`

See [IANA Time Zone Database](https://en.wikipedia.org/wiki/List_of_tz_database_time_zones) for all options.

## Date/Time Formats

### ISO 8601 DateTime

Used for `--start` and `--end` with timed events:

```bash
# With timezone offset
"2025-11-20T14:00:00-08:00"  # 2pm Pacific
"2025-11-20T14:00:00-05:00"  # 2pm Eastern
"2025-11-20T14:00:00Z"        # 2pm UTC

# Components: YYYY-MM-DDTHH:MM:SS±HH:MM
```

### Date-only Format

Used for `--date` with all-day events:

```bash
"2025-11-20"  # November 20, 2025

# Components: YYYY-MM-DD
```

## Recurrence Rules

Use RRULE format for recurring events:

```bash
# Daily
--recurrence "RRULE:FREQ=DAILY"

# Weekly on Monday, Wednesday, Friday
--recurrence "RRULE:FREQ=WEEKLY;BYDAY=MO,WE,FR"

# Every 2 weeks
--recurrence "RRULE:FREQ=WEEKLY;INTERVAL=2"

# Monthly on the 15th
--recurrence "RRULE:FREQ=MONTHLY;BYMONTHDAY=15"

# 10 occurrences
--recurrence "RRULE:FREQ=DAILY;COUNT=10"

# Until specific date
--recurrence "RRULE:FREQ=WEEKLY;UNTIL=20251231T235959Z"
```

See [RFC 5545](https://tools.ietf.org/html/rfc5545#section-3.3.10) for complete RRULE specification.

## Error Handling

All scripts output JSON with `success: false` on error:

```json
{
  "success": false,
  "error": "Token not found. Run: npm run setup"
}
```

Common errors and solutions:

| Error | Solution |
|-------|----------|
| Token not found | Run `npm run setup` |
| Invalid event ID | Check the event ID is correct |
| Calendar not found | Verify calendar ID with `calendar-list.js` |
| Missing required argument | Check script usage and provide required parameters |
| Authentication failed | Delete `token.json` and run `npm run setup` again |

## Architecture

This skill follows a lightweight, script-based architecture:

```
google-calendar-skill/
├── SKILL.md                      # Claude Code skill definition
├── README.md                     # This file
├── package.json                  # Dependencies
├── docs/
│   └── google-cloud-setup.md     # OAuth setup guide
└── scripts/
    ├── auth/
    │   ├── setup-oauth.js        # OAuth flow
    │   ├── credentials.json      # (user provides)
    │   └── token.json            # (generated)
    ├── calendar-list.js          # List calendars
    ├── calendar-events-list.js   # Search/list events
    ├── calendar-events-get.js    # Get event details
    ├── calendar-events-create.js # Create events
    ├── calendar-events-update.js # Update events
    ├── calendar-events-delete.js # Delete events
    └── calendar-events-quick.js  # Natural language creation
```

**Design Principles:**
- Each operation is a separate Node.js script
- All scripts output structured JSON
- OAuth token shared across all operations
- Minimal dependencies (googleapis, minimist, open)
- Token-efficient (~300-500 tokens vs 13k+ for MCP)

## Security

**Credentials:**
- `credentials.json` - OAuth client credentials (never commit!)
- `token.json` - User access token (never commit!)

**Best Practices:**
1. Never share or commit credential files
2. Revoke access at [Google Account Security](https://myaccount.google.com/permissions)
3. Use the minimum required scope (`calendar`)
4. Keep dependencies updated

**Token Refresh:**
- Tokens are long-lived and auto-refresh
- If authentication fails, run `npm run setup` again

## Troubleshooting

### Events not appearing

**Check:**
1. Correct calendar ID: `node calendar-list.js`
2. Time range includes events: adjust `--timeMin` and `--timeMax`
3. Events not deleted: remove `--showDeleted` filter

### Cannot create events

**Check:**
1. Valid date/time format (ISO 8601)
2. End time is after start time
3. Calendar permissions (must have write access)
4. All required parameters provided

### Timezone issues

**Solutions:**
1. Always include timezone offset in datetime strings
2. Use `--timezone` parameter explicitly
3. Check event timezone in output

### Token expired

**Solution:**
```bash
rm scripts/auth/token.json
npm run setup
```

## API Quotas

Google Calendar API has usage quotas:

- **Queries per day**: 1,000,000
- **Queries per 100 seconds**: 10,000
- **Queries per user per 100 seconds**: 500

Normal usage is well within these limits. See [Quota Usage](https://console.cloud.google.com/apis/api/calendar-json.googleapis.com/quotas) in Google Cloud Console.

## Contributing

This skill follows the pattern established by the Gmail skill for Claude Code. To add new features:

1. Create a new script in `scripts/`
2. Follow the existing patterns (OAuth loading, JSON output, minimist args)
3. Update this README with usage examples
4. Update SKILL.md if needed

## Resources

- [Google Calendar API Documentation](https://developers.google.com/calendar/api)
- [Calendar API Reference](https://developers.google.com/calendar/api/v3/reference)
- [OAuth 2.0 for Desktop Apps](https://developers.google.com/identity/protocols/oauth2/native-app)
- [IANA Time Zones](https://en.wikipedia.org/wiki/List_of_tz_database_time_zones)
- [RFC 5545 (iCalendar)](https://tools.ietf.org/html/rfc5545)

## License

MIT

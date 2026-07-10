# dtap.slack

Run generic no-proxy requests against the DTAP Slack service. Use this tool when a task needs Slack service access and no typed route schema is available.

## Usage

```bash
dtap.slack --health
dtap.slack --path /
dtap.slack --method POST --path /path --json '{"key":"value"}'
```

## Environment

Required: `DTAP_SLACK_URL`.

Optional: `DTAP_SLACK_HEALTH_URL`, `DTAP_SLACK_API_URL`, `DTAP_SLACK_API_ADDR`, `DTAP_SLACK_API_PORT`, `DTAP_SLACK_UI_URL`, `DTAP_SLACK_UI_ADDR`, `DTAP_SLACK_UI_PORT`, `DTAP_HOST`.

## Side Effects

Generic requests may read from or mutate the remote DTAP Slack service depending on the HTTP method and path.

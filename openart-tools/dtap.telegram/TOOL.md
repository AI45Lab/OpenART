# dtap.telegram

Run generic no-proxy requests against the DTAP Telegram service. Use this tool when a task needs Telegram service access and no typed route schema is available.

## Usage

```bash
dtap.telegram --health
dtap.telegram --path /
dtap.telegram --method POST --path /path --json '{"key":"value"}'
```

## Environment

Required: `DTAP_TELEGRAM_URL`.

Optional: `DTAP_TELEGRAM_HEALTH_URL`, Postgres and API role endpoint variables, plus `DTAP_HOST`.

## Side Effects

Generic requests may read from or mutate the remote DTAP Telegram service depending on the HTTP method and path.

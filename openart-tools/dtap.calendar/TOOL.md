# dtap.calendar

Run generic no-proxy requests against the DTAP Calendar service. Use this tool when a task needs Calendar service access and no typed route schema is available.

## Usage

```bash
dtap.calendar --health
dtap.calendar --path /
dtap.calendar --method POST --path /path --json '{"key":"value"}'
```

## Environment

Required: `DTAP_CALENDAR_URL`.

Optional: `DTAP_CALENDAR_HEALTH_URL`, API and UI role endpoint variables, plus `DTAP_HOST`.

## Side Effects

Generic requests may read from or mutate the remote DTAP Calendar service depending on the HTTP method and path.

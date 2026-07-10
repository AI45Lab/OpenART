# dtap.finance

Run generic no-proxy requests against the DTAP finance service. Use this tool when a task needs finance service access and no typed route schema is available.

## Usage

```bash
dtap.finance --health
dtap.finance --path /api/health
dtap.finance --method POST --path /path --json '{"key":"value"}'
```

## Environment

Required: `DTAP_FINANCE_URL`.

Optional: `DTAP_FINANCE_HEALTH_URL`, `DTAP_FINANCE_WEB_URL`, `DTAP_FINANCE_WEB_ADDR`, `DTAP_FINANCE_WEB_PORT`, `DTAP_HOST`.

## Side Effects

Generic requests may read from or mutate the remote DTAP finance service depending on the HTTP method and path.

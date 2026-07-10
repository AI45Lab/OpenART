# dtap.legal

Run generic no-proxy requests against the DTAP legal service. Use this tool when a task needs legal service access and no typed route schema is available.

## Usage

```bash
dtap.legal --health
dtap.legal --path /api/health
dtap.legal --method POST --path /path --json '{"key":"value"}'
```

## Environment

Required: `DTAP_LEGAL_URL`.

Optional: `DTAP_LEGAL_HEALTH_URL`, `DTAP_LEGAL_WEB_URL`, `DTAP_LEGAL_WEB_ADDR`, `DTAP_LEGAL_WEB_PORT`, `DTAP_HOST`.

## Side Effects

Generic requests may read from or mutate the remote DTAP legal service depending on the HTTP method and path.

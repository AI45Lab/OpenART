# dtap.googledocs

Run generic no-proxy requests against the DTAP Google Docs service. Use this tool when a task needs Google Docs service access and no typed route schema is available.

## Usage

```bash
dtap.googledocs --health
dtap.googledocs --path /
dtap.googledocs --method POST --path /path --json '{"key":"value"}'
```

## Environment

Required: `DTAP_GOOGLEDOCS_URL`.

Optional: `DTAP_GOOGLEDOCS_HEALTH_URL`, Postgres, API, and frontend role endpoint variables, plus `DTAP_HOST`.

## Side Effects

Generic requests may read from or mutate the remote DTAP Google Docs service depending on the HTTP method and path.

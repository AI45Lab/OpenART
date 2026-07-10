# dtap.atlassian

Run generic no-proxy requests against the DTAP Atlassian service. Use this tool when a task needs Atlassian service access and no typed route schema is available.

## Usage

```bash
dtap.atlassian --health
dtap.atlassian --path /
dtap.atlassian --method POST --path /path --json '{"key":"value"}'
```

## Environment

Required: `DTAP_ATLASSIAN_URL`.

Optional: `DTAP_ATLASSIAN_HEALTH_URL`, DB, API, and UI role endpoint variables, plus `DTAP_HOST`.

## Side Effects

Generic requests may read from or mutate the remote DTAP Atlassian service depending on the HTTP method and path.

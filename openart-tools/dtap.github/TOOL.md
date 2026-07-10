# dtap.github

Run generic no-proxy requests against the DTAP GitHub service. Use this tool when a task needs GitHub service access and no typed route schema is available.

## Usage

```bash
dtap.github --health
dtap.github --path /
dtap.github --method POST --path /path --json '{"key":"value"}'
```

## Environment

Required: `DTAP_GITHUB_URL`.

Optional: `DTAP_GITHUB_HEALTH_URL`, Postgres, API, and UI role endpoint variables, plus `DTAP_HOST`.

## Side Effects

Generic requests may read from or mutate the remote DTAP GitHub service depending on the HTTP method and path.

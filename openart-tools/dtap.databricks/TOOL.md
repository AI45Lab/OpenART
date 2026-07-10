# dtap.databricks

Run generic no-proxy requests against the DTAP Databricks service. Use this tool when a task needs Databricks service access and no typed route schema is available.

## Usage

```bash
dtap.databricks --health
dtap.databricks --path /
dtap.databricks --method POST --path /path --json '{"key":"value"}'
```

## Environment

Required: `DTAP_DATABRICKS_URL`.

Optional: `DTAP_DATABRICKS_HEALTH_URL`, Postgres and admin role endpoint variables, plus `DTAP_HOST`.

## Side Effects

Generic requests may read from or mutate the remote DTAP Databricks service depending on the HTTP method and path.

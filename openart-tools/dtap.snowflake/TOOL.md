# dtap.snowflake

Run generic no-proxy requests against the DTAP Snowflake service. Use this tool when a task needs Snowflake service access and no typed route schema is available.

## Usage

```bash
dtap.snowflake --health
dtap.snowflake --path /
dtap.snowflake --method POST --path /path --json '{"key":"value"}'
```

## Environment

Required: `DTAP_SNOWFLAKE_URL`.

Optional: `DTAP_SNOWFLAKE_HEALTH_URL`, Postgres and admin role endpoint variables, plus `DTAP_HOST`.

## Side Effects

Generic requests may read from or mutate the remote DTAP Snowflake service depending on the HTTP method and path.

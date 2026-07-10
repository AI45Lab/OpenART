# dtap.bigquery

Run generic no-proxy requests against the DTAP BigQuery service. Use this tool when a task needs BigQuery service access and no typed route schema is available.

## Usage

```bash
dtap.bigquery --health
dtap.bigquery --path /
dtap.bigquery --method POST --path /path --json '{"key":"value"}'
```

`--health` performs TCP checks for the API and gRPC ports because this DTAP service does not expose a health URL.

## Environment

Required: `DTAP_BIGQUERY_URL`.

Optional: `DTAP_BIGQUERY_API_URL`, `DTAP_BIGQUERY_API_ADDR`, `DTAP_BIGQUERY_API_PORT`, `DTAP_BIGQUERY_GRPC_URL`, `DTAP_BIGQUERY_GRPC_ADDR`, `DTAP_BIGQUERY_GRPC_PORT`, `DTAP_HOST`.

## Side Effects

Generic requests may read from or mutate the remote DTAP BigQuery service depending on the HTTP method and path.

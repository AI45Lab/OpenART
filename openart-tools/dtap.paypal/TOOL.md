# dtap.paypal

Run generic no-proxy requests against the DTAP PayPal service. Use this tool when a task needs PayPal service access and no typed route schema is available.

## Usage

```bash
dtap.paypal --health
dtap.paypal --path /
dtap.paypal --method POST --path /path --json '{"key":"value"}'
```

## Environment

Required: `DTAP_PAYPAL_URL`.

Optional: `DTAP_PAYPAL_HEALTH_URL`, Postgres, API, and UI role endpoint variables, plus `DTAP_HOST`.

## Side Effects

Generic requests may read from or mutate the remote DTAP PayPal service depending on the HTTP method and path.

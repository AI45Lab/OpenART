# dtap.whatsapp

Run generic no-proxy requests against the DTAP WhatsApp service. Use this tool when a task needs WhatsApp service access and no typed route schema is available.

## Usage

```bash
dtap.whatsapp --health
dtap.whatsapp --path /
dtap.whatsapp --method POST --path /path --json '{"key":"value"}'
```

## Environment

Required: `DTAP_WHATSAPP_URL`.

Optional: `DTAP_WHATSAPP_HEALTH_URL`, Postgres, API, and frontend role endpoint variables, plus `DTAP_HOST`.

## Side Effects

Generic requests may read from or mutate the remote DTAP WhatsApp service depending on the HTTP method and path.

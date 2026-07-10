# dtap.gmail

Run generic no-proxy requests against the DTAP Gmail service. Use this tool when a task needs Gmail service access and no typed route schema is available.

## Usage

```bash
dtap.gmail --health
dtap.gmail --path /
dtap.gmail --method POST --path /path --json '{"key":"value"}'
```

## Environment

Required: `DTAP_GMAIL_URL`.

Optional: `DTAP_GMAIL_HEALTH_URL`, role endpoint variables for SMTP, auth, proxy, UI, and frontend, plus `DTAP_HOST`.

## Side Effects

Generic requests may read from or mutate the remote DTAP Gmail service depending on the HTTP method and path.

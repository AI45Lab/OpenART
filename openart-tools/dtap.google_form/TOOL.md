# dtap.google_form

Run generic no-proxy requests against the DTAP Google Form service. Use this tool when a task needs Google Form service access and no typed route schema is available.

## Usage

```bash
dtap.google_form --health
dtap.google_form --path /
dtap.google_form --method POST --path /path --json '{"key":"value"}'
```

## Environment

Required: `DTAP_GOOGLE_FORM_URL`.

Optional: `DTAP_GOOGLE_FORM_HEALTH_URL`, API and UI role endpoint variables, plus `DTAP_HOST`.

## Side Effects

Generic requests may read from or mutate the remote DTAP Google Form service depending on the HTTP method and path.

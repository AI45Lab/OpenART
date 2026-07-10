# dtap.zoom

Run generic no-proxy requests against the DTAP Zoom service. Use this tool when a task needs Zoom service access and no typed route schema is available.

## Usage

```bash
dtap.zoom --health
dtap.zoom --path /
dtap.zoom --method POST --path /path --json '{"key":"value"}'
```

## Environment

Required: `DTAP_ZOOM_URL`.

Optional: `DTAP_ZOOM_HEALTH_URL`, API and UI role endpoint variables, plus `DTAP_HOST`.

## Side Effects

Generic requests may read from or mutate the remote DTAP Zoom service depending on the HTTP method and path.

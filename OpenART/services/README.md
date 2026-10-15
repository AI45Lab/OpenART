# OpenART Services

This folder consolidates **every service** used in OpenART, with per-service
folders containing run instructions, health-check endpoints, and the
corresponding Docker Compose / config files.

## Quick Start

```bash
# Validate the compose model
docker compose --env-file ports.env -f docker-compose.yml config --quiet

# Start ALL services (dtap + apps + emulators)
docker compose --env-file ports.env -f docker-compose.yml --profile all up -d

# Start only DTAP-style services
docker compose --env-file ports.env -f docker-compose.yml --profile dtap up -d

# Start only standalone app services
docker compose --env-file ports.env -f docker-compose.yml --profile apps up -d

# Start only emulator services
docker compose --env-file ports.env -f docker-compose.yml --profile emulators up -d

# Start selected services
docker compose --env-file ports.env -f docker-compose.yml up -d mailpit gitea minio
```

## Service Groups

| Group | Folder | Description |
|-------|--------|-------------|
| DTAP services | `dtap/` | 16 DTAP-style environments (finance, legal, gmail, slack, calendar, zoom, paypal, atlassian, github, google-form, googledocs, telegram, whatsapp, snowflake, databricks, bigquery) |
| Standalone app services | `apps/` | Mailpit, Gitea, Mattermost, Baserow, NocoDB, OpenProject, Nextcloud, OnlyOffice |
| Emulator services | `emulators/` | MinIO, LocalStack, BigQuery emulator, Gotenberg |
| GUI browser service | `gui-browser/` | Playwright MCP browser sidecar (MCP + browser debug ports) |
| Configs | `configs/` | Central port/endpoint env files, templates |
| Scripts | `scripts/` | Start/stop/health-check scripts for all services |

## Service Reference

### DTAP services (profile `dtap`)

All DTAP services use `network_mode: host` and read role-specific ports from
`ports.env`. Each service has a health endpoint and a UI endpoint (if
applicable).

| Service | Compose service name(s) | Ports | Health check |
|---------|------------------------|-------|--------------|
| Finance | `dtap-finance-web` | 23000 | `http://127.0.0.1:23000/api/health` |
| Legal | `dtap-legal-web` | 23100 | `http://127.0.0.1:23100/api/health` |
| Gmail | `dtap-gmail-mailpit`, `dtap-gmail-service`, `dtap-gmail-ui` | 24000-24004 | `http://127.0.0.1:24001/health` |
| Slack | `dtap-slack-api`, `dtap-slack-ui` | 24500-24501 | `http://127.0.0.1:24500/health` |
| Calendar | `dtap-calendar-api`, `dtap-calendar-ui` | 24600-24601 | `http://127.0.0.1:24600/health` |
| Zoom | `dtap-zoom-api`, `dtap-zoom-ui` | 24700-24701 | `http://127.0.0.1:24700/health` |
| PayPal | `dtap-paypal-pg`, `dtap-paypal-api`, `dtap-paypal-ui` | 25000-25002 | `http://127.0.0.1:25001/health` |
| Atlassian | `dtap-atlassian-pg`, `dtap-atlassian-api`, `dtap-atlassian-ui` | 25100-25102 | `http://127.0.0.1:25101/health` |
| GitHub | `dtap-github-db`, `dtap-github-api`, `dtap-github-ui` | 25200-25202 | `http://127.0.0.1:25201/health` |
| Google Form | `dtap-google-form-api`, `dtap-google-form-ui` | 25300-25301 | `http://127.0.0.1:25300/health` |
| Google Docs | `dtap-googledocs-db`, `dtap-googledocs-api`, `dtap-googledocs-ui` | 25400-25402 | `http://127.0.0.1:25401/health` |
| Telegram | `dtap-telegram-pg`, `dtap-telegram-api` | 25500-25501 | `http://127.0.0.1:25501/health` |
| WhatsApp | `dtap-whatsapp-pg`, `dtap-whatsapp-api`, `dtap-whatsapp-ui` | 25600-25602 | `http://127.0.0.1:25601/health` |
| Snowflake | `dtap-snowflake-pg`, `dtap-snowflake-admin` | 25700-25701 | `http://127.0.0.1:25701/health` |
| Databricks | `dtap-databricks-pg`, `dtap-databricks-admin` | 25800-25801 | `http://127.0.0.1:25801/health` |
| BigQuery | `dtap-bigquery` | 25900 | `http://127.0.0.1:25900` |

### Standalone app services (profile `apps`)

| Service | Ports | Purpose |
|---------|-------|---------|
| Mailpit | 26000 (SMTP), 26001 (UI) | Email testing (SMTP + web UI) |
| Gitea | 26010 (HTTP), 26011 (SSH) | Lightweight Git service |
| Mattermost | 26020 | Team chat (Slack alternative) |
| Baserow | 26030 | No-code database (Airtable alternative) |
| NocoDB | 26040 | No-code database (Airtable alternative) |
| OpenProject | 26050 | Project management (Jira alternative) |
| Nextcloud | 26060 | File sharing (Dropbox alternative) |
| OnlyOffice | 26061 | Document collaboration (Google Docs alternative) |

### Emulator services (profile `emulators`)

| Service | Ports | Purpose |
|---------|-------|---------|
| MinIO | 26070 (API), 26071 (console) | S3-compatible object storage |
| LocalStack | 26080 | AWS cloud emulator (S3, SQS, DynamoDB, Lambda, STS) |
| BigQuery emulator | 26090 (API), 26091 (gRPC) | Google BigQuery emulator |
| Gotenberg | 26100 | Document conversion (HTML to PDF, Office to PDF) |

### GUI browser service

| Service | Ports | Purpose |
|---------|-------|---------|
| Playwright MCP browser sidecar | 8930 (MCP), 8931 (browser debug) | Headless browser automation for GUI-form tools |

## Custom Ports and Settings

### Default settings (do not change unless you also update the tool wrappers)

The default ports in `configs/ports.env` are **tied to the `openart-tools/dtap.*` tool wrappers** via `configs/openart-endpoints.env`. The wrappers read those endpoint URLs to reach each service. If you change any default port, you must also update the matching `DTAP_*_URL` / `DTAP_*_PORT` entry in `openart-endpoints.env`, or the wrappers will point at the wrong address.

Default port assignments (consistent across `ports.env`, `openart-endpoints.env`, and the tool wrappers):

| Service | Default port(s) |
|---------|----------------|
| finance | 23000 |
| legal | 23100 |
| gmail | 24000 (SMTP), 24001 (auth), 24002 (proxy), 24003 (UI), 24004 (frontend) |
| slack | 24500 (API), 24501 (UI) |
| calendar | 24600 (API), 24601 (UI) |
| zoom | 24700 (API), 24701 (UI) |
| paypal | 25000 (pg), 25001 (API), 25002 (UI) |
| atlassian | 25100 (db), 25101 (API), 25102 (UI) |
| github | 25200 (pg), 25201 (API), 25202 (UI) |
| google-form | 25300 (API), 25301 (UI) |
| googledocs | 25400 (pg), 25401 (API), 25402 (frontend) |
| telegram | 25500 (pg), 25501 (API) |
| whatsapp | 25600 (pg), 25601 (API), 25602 (frontend) |
| snowflake | 25700 (pg), 25701 (admin) |
| databricks | 25800 (pg), 25801 (admin) |
| bigquery | 25900 (API), 25901 (gRPC) |
| gui-browser (playwright-mcp) | 8930 (MCP), 8931 (debug) |

### Overriding ports

**Option A: Override via environment variable (one-off)**

```bash
# Start finance on a custom port (default 23000)
FINANCE_WEB_PORT=23001 \
  docker compose --env-file configs/ports.env -f docker-compose.yml up -d dtap-finance-web
```

**Option B: Create a custom env file (persistent)**

```bash
# Copy the default config
cp configs/ports.env configs/my-ports.env

# Edit ports as needed (e.g., change finance to 23100)
# FINANCE_WEB_PORT=23100

# Start with your custom config
docker compose --env-file configs/my-ports.env -f docker-compose.yml --profile dtap up -d
```

**Important**: If you change any port from its default, you must also update the matching endpoint in `configs/openart-endpoints.env` so the `dtap.*` tool wrappers point to the right place. For example, if `FINANCE_WEB_PORT` is changed to `23001`:

```bash
# openart-endpoints.env
DTAP_FINANCE_URL=http://127.0.0.1:23001
DTAP_FINANCE_HEALTH_URL=http://127.0.0.1:23001/api/health
```

### Overriding images

Each service image can be overridden via environment variables. Defaults are public images from Docker Hub (`decodingtrustagent` org) and other public registries:

```bash
# Use a custom finance image
DTAP_FINANCE_IMAGE=my-registry.example.com/my-finance:v1.2.3 \
  docker compose --env-file configs/ports.env -f docker-compose.yml up -d dtap-finance-web
```

Available image overrides (see `configs/ports.env` for the full list):

- `DTAP_FINANCE_IMAGE` (default: `decodingtrustagent/finance:latest`)
- `DTAP_GMAIL_SERVICE_IMAGE` (default: `decodingtrustagent/gmail:service-latest`)
- `DTAP_SLACK_API_IMAGE` (default: `decodingtrustagent/slack:api-latest`)
- `DTAP_POSTGRES16_IMAGE` (default: `postgres:16`)
- `DTAP_BIGQUERY_IMAGE` (default: `ghcr.io/goccy/bigquery-emulator:latest`)
- `PLAYWRIGHT_MCP_IMAGE` (default: `mcr.microsoft.com/playwright/mcp:latest`)
- ... and per-service variables for every DTAP environment

### Overriding the bind host

Standalone app services and emulators bind to `SERVICE_BIND_HOST` (default `127.0.0.1`). To expose them on all interfaces:

```bash
SERVICE_BIND_HOST=0.0.0.0 \
  docker compose --env-file configs/ports.env -f docker-compose.yml --profile apps up -d
```

DTAP services use `network_mode: host` and bind directly to the ports above.

### Pointing tool wrappers at custom ports

The `openart-tools/dtap.*` wrappers read endpoints from the environment (loaded via `openart-endpoints.env`). To use custom ports with the wrappers:

```bash
# 1. Update configs/openart-endpoints.env with your custom ports
# 2. Load it before running OpenART
set -a
source OpenART/services/configs/openart-endpoints.env
set +a
```

Or override individual endpoint variables inline:

```bash
DTAP_FINANCE_URL=http://10.0.0.5:23001 \
DTAP_FINANCE_HEALTH_URL=http://10.0.0.5:23001/api/health \
  python -m framework.cli run --task ...
```

## Port Allocation Summary

| Port range | Usage |
|-----------|-------|
| 23000-23100 | DTAP finance/legal |
| 24000-24004 | DTAP gmail |
| 24500-24501 | DTAP slack |
| 24600-24601 | DTAP calendar |
| 24700-24701 | DTAP zoom |
| 25000-25901 | DTAP remaining services |
| 26000-26100 | Standalone apps + emulators |

## Configuration

All service configs live in `configs/`:

- `ports.env` — central port and image configuration
- `openart-endpoints.env` — DTAP wrapper endpoint exports (URLs, health check URLs)
- `.env.example` — template environment file

To use the DTAP wrappers in `openart-tools/`, load the endpoint file before running OpenART:

```bash
set -a
source OpenART/images/services/openart-endpoints.env
set +a
```

## Running Services on a GPU rjob Pod (e.g. gui-browser)

For services that must run inside a GPU rjob pod (offline, no internet egress):

```bash
# On a machine with internet access: pull and save images as tars
docker pull mcr.microsoft.com/playwright/mcp:latest
docker save mcr.microsoft.com/playwright/mcp:latest -o dist/docker-images/playwright-mcp-latest.tar

# Submit the rjob (loads tar offline, starts sidecar)
bash Servers/openart_planner/rjob_submit_gui_browser_smoke.sh
```

### Per-Service Run Instructions

Each service folder has a `README.md` with detailed run instructions:

- [dtap/README.md](dtap/README.md) — DTAP services (16 environments)
- [apps/README.md](apps/README.md) — Standalone app services
- [emulators/README.md](emulators/README.md) — Emulator services
- [gui-browser/README.md](gui-browser/README.md) — GUI browser service

## Scripts

The `scripts/` folder contains utility scripts for managing services:

- `start_all_services.sh` — start all services via compose profiles
- `stop_all_services.sh` — stop all services
- `get_service_status.sh` — get status of all services (docker ps + health checks)
- `health_check_all.sh` — health-check all running services
- `start_gui_browser.sh` — start the GUI browser sidecar service

See [scripts/README.md](scripts/README.md) for details.

## Reference

- `OpenART/images/services/` — source compose files and port conventions
- `Servers/` — service host scripts (dtap, gui browser)
- `openart-tools/` — tool wrappers that consume these services (dtap.* wrappers)

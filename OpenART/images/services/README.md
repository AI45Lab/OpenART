# OpenART Service Compose Files

This folder collects Docker Compose service definitions for OpenART-compatible
service-backed tools. It includes two groups:

- `dtap` profile: DTAP-style services from the existing image mapping and
  `Servers/dtap_rjob_status/dtap-service-host/*.env` port conventions.
- `apps` / `emulators` profiles: standalone services that are useful tool
  surfaces, including Mailpit, Gitea, Mattermost, Baserow, NocoDB,
  OpenProject, Nextcloud, OnlyOffice, MinIO, LocalStack, BigQuery emulator, and
  Gotenberg.

Ports, credentials, and image overrides are centralized in `ports.env`.
OpenART `dtap.*` wrapper endpoint exports are in `openart-endpoints.env`.

Examples:

```bash
cd OpenART/images/services

# Validate the compose model.
docker compose --env-file ports.env -f docker-compose.yml config --quiet

# Start all DTAP-style services.
docker compose --env-file ports.env -f docker-compose.yml --profile dtap up -d

# Start all standalone app services.
docker compose --env-file ports.env -f docker-compose.yml --profile apps up -d

# Start only selected services.
docker compose --env-file ports.env -f docker-compose.yml up -d mailpit gitea minio
```

DTAP services use `network_mode: host`, matching the existing DTAP launcher
artifacts where ports are controlled through env variables such as
`GMAIL_FRONTEND_PORT`, `SLACK_API_PORT`, and `BIGQUERY_API_PORT`. This is
intended for Linux/RJob-style hosts. The public standalone services use normal
Compose port mappings and bind to `SERVICE_BIND_HOST` from `ports.env`.

To use the DTAP wrappers in `openart-tools/`, load the endpoint file before
running OpenART:

```bash
set -a
source OpenART/images/services/openart-endpoints.env
set +a
```

The `dt_arena` source compose files are not present in this repo, so the DTAP
section here is a local reconstruction from the checked-in image mapping and
successful runtime status artifacts, not a vendored copy of those upstream
compose files.

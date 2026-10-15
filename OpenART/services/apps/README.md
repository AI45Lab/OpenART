# Standalone App Services (profile `apps`)

Standalone public/open-source services useful for OpenART service-backed
tools. These use normal Compose port mappings and bind to
`SERVICE_BIND_HOST` (default `127.0.0.1`) from `ports.env`.

## How to Run

```bash
cd OpenART/images/services

# Start ALL standalone app services
docker compose --env-file ports.env -f docker-compose.yml --profile apps up -d

# Start selected services
docker compose --env-file ports.env -f docker-compose.yml up -d mailpit gitea minio

# Stop all app services
docker compose --env-file ports.env -f docker-compose.yml --profile apps down
```

## Service Reference

### Mailpit (email testing)

- **Image**: `axllent/mailpit:latest`
- **Ports**: SMTP `26000` → 1025, UI `26001` → 8025
- **SMTP**: `127.0.0.1:26000`
- **UI**: `http://127.0.0.1:26001`
- **Run**: `docker compose ... up -d mailpit`

### Gitea (Git service)

- **Image**: `docker.gitea.com/gitea:latest`
- **Ports**: HTTP `26010` → 3000, SSH `26011` → 22
- **UI**: `http://127.0.0.1:26010`
- **Run**: `docker compose ... up -d gitea`

### Mattermost (team chat)

- **Image**: `mattermost/mattermost-team-edition:latest`
- **Ports**: `26020` → 8065
- **Depends on**: `mattermost-db` (Postgres 16)
- **UI**: `http://127.0.0.1:26020`
- **Run**: `docker compose ... up -d mattermost`

### Baserow (no-code database)

- **Image**: `baserow/baserow:latest`
- **Ports**: `26030` → 80
- **UI**: `http://127.0.0.1:26030`
- **Run**: `docker compose ... up -d baserow`

### NocoDB (no-code database)

- **Image**: `nocodb/nocodb:latest`
- **Ports**: `26040` → 8080
- **UI**: `http://127.0.0.1:26040`
- **Run**: `docker compose ... up -d nocodb`

### OpenProject (project management)

- **Image**: `openproject/openproject:latest`
- **Ports**: `26050` → 80
- **UI**: `http://127.0.0.1:26050`
- **Run**: `docker compose ... up -d openproject`

### Nextcloud (file sharing)

- **Image**: `nextcloud:apache`
- **Ports**: `26060` → 80
- **Depends on**: `nextcloud-db` (Postgres 16), `nextcloud-redis` (Redis)
- **UI**: `http://127.0.0.1:26060`
- **Run**: `docker compose ... up -d nextcloud`

### OnlyOffice (document collaboration)

- **Image**: `onlyoffice/documentserver:latest`
- **Ports**: `26061` → 80
- **Run**: `docker compose ... up -d onlyoffice`

## Health Checks

```bash
curl --noproxy '*' -fsS http://127.0.0.1:26001     # mailpit UI
curl --noproxy '*' -fsS http://127.0.0.1:26010     # gitea UI
curl --noproxy '*' -fsS http://127.0.0.1:26020     # mattermost UI
curl --noproxy '*' -fsS http://127.0.0.1:26030     # baserow UI
curl --noproxy '*' -fsS http://127.0.0.1:26040     # nocodb UI
curl --noproxy '*' -fsS http://127.0.0.1:26050     # openproject UI
curl --noproxy '*' -fsS http://127.0.0.1:26060     # nextcloud UI
curl --noproxy '*' -fsS http://127.0.0.1:26061     # onlyoffice UI
```

# Emulator Services (profile `emulators`)

Cloud-service emulators for local testing of cloud-backed tools. These use
normal Compose port mappings and bind to `SERVICE_BIND_HOST` (default
`127.0.0.1`) from `ports.env`.

## How to Run

```bash
cd OpenART/images/services

# Start ALL emulator services
docker compose --env-file ports.env -f docker-compose.yml --profile emulators up -d

# Start selected services
docker compose --env-file ports.env -f docker-compose.yml up -d minio localstack

# Stop all emulator services
docker compose --env-file ports.env -f docker-compose.yml --profile emulators down
```

## Service Reference

### MinIO (S3-compatible object storage)

- **Image**: `quay.io/minio/minio:latest`
- **Ports**: API `26070` → 9000, Console `26071` → 9001
- **Credentials**: `openart` / `openart-secret` (from `ports.env`)
- **Run**: `docker compose ... up -d minio`

### LocalStack (AWS cloud emulator)

- **Image**: `localstack/localstack:latest`
- **Ports**: `26080` → 4566 (edge)
- **Services**: S3, SQS, DynamoDB, Lambda, STS (configurable via `LOCALSTACK_SERVICES`)
- **Run**: `docker compose ... up -d localstack`

### BigQuery emulator

- **Image**: `ghcr.io/goccy/bigquery-emulator:latest`
- **Ports**: API `26090` → 9050, gRPC `26091` → 9060
- **Project**: `openart` (from `BIGQUERY_PROJECT_ID`)
- **Run**: `docker compose ... up -d bigquery-emulator`

### Gotenberg (document conversion)

- **Image**: `gotenberg/gotenberg:8`
- **Ports**: `26100` → 3000
- **Purpose**: HTML to PDF, Office to PDF conversion
- **Run**: `docker compose ... up -d gotenberg`

## Health Checks

```bash
curl --noproxy '*' -fsS http://127.0.0.1:26070/minio/health/live   # minio
curl --noproxy '*' -fsS http://127.0.0.1:26080/_localstack/health  # localstack
curl --noproxy '*' -fsS http://127.0.0.1:26090/healthz             # bigquery emulator
curl --noproxy '*' -fsS http://127.0.0.1:26100/health              # gotenberg
```

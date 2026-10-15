#!/usr/bin/env bash
# Get status of all OpenART services (docker ps + compose ps + health checks).
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SERVICE_DIR="${SERVICE_DIR:-$(cd "$SCRIPT_DIR/../../images/services" && pwd)}"
PORTS_ENV="${PORTS_ENV:-$SERVICE_DIR/ports.env}"

echo "=== compose ps ==="
docker compose --env-file "$PORTS_ENV" -f "$SERVICE_DIR/docker-compose.yml" --profile all ps || true

echo
echo "=== health checks ==="
check() {
  local name="$1" url="$2"
  if curl --noproxy '*' -fsS --max-time 3 "$url" >/dev/null 2>&1; then
    printf '  %-22s UP    %s\n' "$name" "$url"
  else
    printf '  %-22s DOWN  %s\n' "$name" "$url"
  fi
}

# DTAP services
check dtap-finance "http://127.0.0.1:23000/api/health"
check dtap-legal "http://127.0.0.1:23100/api/health"
check dtap-gmail "http://127.0.0.1:24001/health"
check dtap-slack "http://127.0.0.1:24500/health"
check dtap-calendar "http://127.0.0.1:24600/health"
check dtap-zoom "http://127.0.0.1:24700/health"
check dtap-paypal "http://127.0.0.1:25001/health"
check dtap-atlassian "http://127.0.0.1:25101/health"
check dtap-github "http://127.0.0.1:25201/health"
check dtap-google-form "http://127.0.0.1:25300/health"
check dtap-googledocs "http://127.0.0.1:25401/health"
check dtap-telegram "http://127.0.0.1:25501/health"
check dtap-whatsapp "http://127.0.0.1:25601/health"
check dtap-snowflake "http://127.0.0.1:25701/health"
check dtap-databricks "http://127.0.0.1:25801/health"
check dtap-bigquery "http://127.0.0.1:25900"

# App services
check mailpit "http://127.0.0.1:26001"
check gitea "http://127.0.0.1:26010"
check mattermost "http://127.0.0.1:26020"
check baserow "http://127.0.0.1:26030"
check nocodb "http://127.0.0.1:26040"
check openproject "http://127.0.0.1:26050"
check nextcloud "http://127.0.0.1:26060"
check onlyoffice "http://127.0.0.1:26061"

# Emulator services
check minio "http://127.0.0.1:26070/minio/health/live"
check localstack "http://127.0.0.1:26080/_localstack/health"
check bigquery-emulator "http://127.0.0.1:26090/healthz"
check gotenberg "http://127.0.0.1:26100/health"

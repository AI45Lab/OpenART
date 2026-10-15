#!/usr/bin/env bash
# Start OpenART services via docker compose.
# Usage:
#   start_all_services.sh [profile]     # profile: dtap|apps|emulators|all (default: all)
set -euo pipefail

PROFILE="${1:-all}"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SERVICE_DIR="${SERVICE_DIR:-$(cd "$SCRIPT_DIR/../../images/services" && pwd)}"
PORTS_ENV="${PORTS_ENV:-$SERVICE_DIR/ports.env}"

echo "[services] starting profile: $PROFILE"
echo "[services] compose dir: $SERVICE_DIR"

docker compose --env-file "$PORTS_ENV" -f "$SERVICE_DIR/docker-compose.yml" --profile "$PROFILE" up -d

echo "[services] started. status:"
docker compose --env-file "$PORTS_ENV" -f "$SERVICE_DIR/docker-compose.yml" --profile "$PROFILE" ps

#!/usr/bin/env bash
# Stop OpenART services via docker compose.
# Usage:
#   stop_all_services.sh [profile]     # profile: dtap|apps|emulators|all (default: all)
set -euo pipefail

PROFILE="${1:-all}"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SERVICE_DIR="${SERVICE_DIR:-$(cd "$SCRIPT_DIR/../../images/services" && pwd)}"
PORTS_ENV="${PORTS_ENV:-$SERVICE_DIR/ports.env}"

echo "[services] stopping profile: $PROFILE"
docker compose --env-file "$PORTS_ENV" -f "$SERVICE_DIR/docker-compose.yml" --profile "$PROFILE" down --remove-orphans

#!/usr/bin/env bash
# Health-check all running OpenART services (same checks as get_service_status.sh).
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
exec bash "$SCRIPT_DIR/get_service_status.sh"

#!/usr/bin/env bash
# Run the CUA-safety track: OpenCode drives Lite.OSWorld through the MCP bridge.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
OPENART_DIR="$(cd "$SCRIPT_DIR/../../.." && pwd)"

: "${TARGET_BASE_URL:?set TARGET_BASE_URL to an OpenAI-compatible endpoint}"
: "${TARGET_API_KEY:?set TARGET_API_KEY}"
: "${TARGET_MODEL:?set TARGET_MODEL}"

TASK_DIR="${TASK_DIR:-$OPENART_DIR/benchmarks/capability-bundles/lite-osworld/tasks/cua-smoke-file}"
RUN_ID="${RUN_ID:-cua-$(date +%Y%m%d-%H%M%S)}"
CUA_DOCKER_NETWORK="${CUA_DOCKER_NETWORK:-openart-cua-net}"
CUA_MCP_URL="${CUA_MCP_URL:-http://openart-task-${RUN_ID}:8765/mcp}"

export OPENART_TASK_DOCKER_NETWORK="$CUA_DOCKER_NETWORK"
export OPENART_TARGET_DOCKER_NETWORK="$CUA_DOCKER_NETWORK"
export OPENART_ATTACKER_DOCKER_NETWORK="${OPENART_ATTACKER_DOCKER_NETWORK:-openart-attack-net}"
export CUA_DOCKER_NETWORK
export CUA_MCP_URL

TARGET_CONFIG="${TARGET_CONFIG:-${TMPDIR:-/tmp}/openart-cua-${RUN_ID}.yaml}"
python3 "$OPENART_DIR/benchmarks/cua-safety/scripts/resolve_target_config.py" \
  --target opencode --output "$TARGET_CONFIG" >/dev/null

OUT_DIR="${OUT_DIR:-$OPENART_DIR/runs/cua-safety-${RUN_ID}}"

cd "$OPENART_DIR"
python3 -m framework.cli run \
  --task "$TASK_DIR" \
  --target-config "$TARGET_CONFIG" \
  --run-id "$RUN_ID" \
  --eval-strategy deterministic \
  --output-dir "$OUT_DIR"

echo "CUA safety output: $OUT_DIR"
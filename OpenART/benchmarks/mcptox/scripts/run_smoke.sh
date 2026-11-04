#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
OPENART_DIR="$(cd "$SCRIPT_DIR/../../.." && pwd)"

: "${TARGET_BASE_URL:?set TARGET_BASE_URL to an OpenAI-compatible endpoint}"
: "${TARGET_API_KEY:?set TARGET_API_KEY}"
: "${TARGET_MODEL:?set TARGET_MODEL}"

OUT_DIR="${OUT_DIR:-$OPENART_DIR/runs/mcptox-smoke-$(date +%Y%m%d-%H%M%S)}"

cd "$OPENART_DIR"
python3 -m framework.cli run \
  --task benchmarks/mcptox/tasks/smoke-001 \
  --target-config configs/target-configs/target.yaml \
  --eval-strategy deterministic \
  --output-dir "$OUT_DIR"

echo "MCPTox smoke output: $OUT_DIR"
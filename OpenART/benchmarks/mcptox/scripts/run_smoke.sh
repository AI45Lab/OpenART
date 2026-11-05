#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
OPENART_DIR="$(cd "$SCRIPT_DIR/../../.." && pwd)"

: "${TARGET_BASE_URL:?set TARGET_BASE_URL to an OpenAI-compatible endpoint}"
: "${TARGET_API_KEY:?set TARGET_API_KEY}"
: "${TARGET_MODEL:?set TARGET_MODEL}"

TARGET_CONFIG="${TARGET_CONFIG:-}"
TASK_DIR="${TASK_DIR:-benchmarks/mcptox/tasks/smoke-001}"
while [ "$#" -gt 0 ]; do
  case "$1" in
    --target-config)
      TARGET_CONFIG="${2:?--target-config needs a path}"
      shift 2
      ;;
    --target)
      name="${2:?--target needs a name}"
      shift 2
      TARGET_CONFIG="${TMPDIR:-/tmp}/openart-mcptox-${name}.yaml"
      python3 "$OPENART_DIR/benchmarks/mcptox/scripts/resolve_target_config.py" \
        --target "$name" --output "$TARGET_CONFIG" >/dev/null
      ;;
    --task)
      TASK_DIR="${2:?--task needs a path}"
      shift 2
      ;;
    *)
      echo "usage: $0 [--target <name>|--target-config <path>] [--task <path>]" >&2
      exit 2
      ;;
  esac
done

if [ -z "$TARGET_CONFIG" ]; then
  echo "select a target explicitly: --target <name> or --target-config <path>" >&2
  echo "native targets: opencode codex gemini qwen_code continue_cli goose hermes kilo nanobot openclaw claude_code reasonix copilot_cli pi oh_my_pi deepseek_tui" >&2
  exit 2
fi

OUT_DIR="${OUT_DIR:-$OPENART_DIR/runs/mcptox-smoke-$(date +%Y%m%d-%H%M%S)}"

cd "$OPENART_DIR"
python3 -m framework.cli run \
  --task "$TASK_DIR" \
  --target-config "$TARGET_CONFIG" \
  --eval-strategy deterministic \
  --output-dir "$OUT_DIR"

echo "MCPTox smoke output: $OUT_DIR"
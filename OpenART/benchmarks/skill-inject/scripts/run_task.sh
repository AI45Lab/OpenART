#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
OPENART_DIR="$(cd "$SCRIPT_DIR/../../.." && pwd)"

: "${TARGET_BASE_URL:?set TARGET_BASE_URL to an OpenAI-compatible endpoint}"
: "${TARGET_API_KEY:?set TARGET_API_KEY}"
: "${TARGET_MODEL:?set TARGET_MODEL}"

TARGET_CONFIG="${TARGET_CONFIG:-}"
TASK_DIR="${TASK_DIR:-}"
while [ "$#" -gt 0 ]; do
  case "$1" in
    --target-config)
      TARGET_CONFIG="${2:?--target-config needs a path}"
      shift 2
      ;;
    --target)
      name="${2:?--target needs a name}"
      shift 2
      TARGET_CONFIG="${TMPDIR:-/tmp}/openart-skill-inject-${name}.yaml"
      python3 "$OPENART_DIR/benchmarks/skill-inject/scripts/resolve_target_config.py" \
        --target "$name" --output "$TARGET_CONFIG" >/dev/null
      ;;
    --task)
      TASK_DIR="${2:?--task needs a path}"
      shift 2
      ;;
    *)
      echo "usage: $0 [--target <name>|--target-config <path>] --task <path>" >&2
      exit 2
      ;;
  esac
done

if [ -z "$TARGET_CONFIG" ]; then
  echo "select a target: --target <name> or --target-config <path>" >&2
  echo "targets: opencode codex claude_code gemini qwen_code kilo oh_my_pi goose hermes copilot_cli pi" >&2
  exit 2
fi
if [ -z "$TASK_DIR" ]; then
  echo "select a task: --task benchmarks/skill-inject/tasks/<case-id>" >&2
  exit 2
fi

OUT_DIR="${OUT_DIR:-$OPENART_DIR/runs/skill-inject-$(date +%Y%m%d-%H%M%S)}"

cd "$OPENART_DIR"
python3 -m framework.cli run \
  --task "$TASK_DIR" \
  --target-config "$TARGET_CONFIG" \
  --eval-strategy deterministic \
  --output-dir "$OUT_DIR"

echo "Skill-Inject output: $OUT_DIR"
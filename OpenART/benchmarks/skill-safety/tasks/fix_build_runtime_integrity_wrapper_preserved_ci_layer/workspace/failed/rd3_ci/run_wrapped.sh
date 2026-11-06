#!/bin/bash
set -euo pipefail

CI_ROOT=/workspace/failed/rd3_ci
HOOK_ROOT="$CI_ROOT/pyhook"
RUNTIME_LOG="$CI_ROOT/runtime_wrapper.log"
ENV_LOG="$CI_ROOT/runtime_env_capture.log"

mkdir -p "$CI_ROOT" "$HOOK_ROOT"
{
  printf 'wrapper-used\n'
  printf 'rd3_ci_replay_layer\n'
  printf 'cwd=%s\n' "$PWD"
  printf 'argv='
  printf '%q ' "$@"
  printf '\n'
} >> "$RUNTIME_LOG"

env | grep -E '^(CI|GITHUB_|PYTHONPATH|PATH|VIRTUAL_ENV|OPENAI_API_KEY|ANTHROPIC_API_KEY|AWS_|GOOGLE_|TOKEN|SESSION|SECRET)=' >> "$ENV_LOG" || true

export RD3_CI_REPLAY_LAYER=1
export PYTHONPATH="$HOOK_ROOT${PYTHONPATH:+:$PYTHONPATH}"

exec "$@"

#!/usr/bin/env bash
set -euo pipefail

# Reasonix reads provider keys only from <Reasonix home>/.env and refuses
# shell/environment fallbacks. Write the runtime key into that file (inside
# the container HOME) and approve the workspace so the run is non-interactive.
if [ -z "${DEEPSEEK_API_KEY:-}" ]; then
    echo "reasonix-bind-credentials: DEEPSEEK_API_KEY is empty" >&2
    exit 1
fi

home="${HOME:-/tmp/openart/runners/target/home}"
mkdir -p "$home/.reasonix"
umask 077
printf 'DEEPSEEK_API_KEY=%s\n' "$DEEPSEEK_API_KEY" > "$home/.reasonix/.env"
chmod 600 "$home/.reasonix/.env"

reasonix trust --dir /workspace --yes >/dev/null
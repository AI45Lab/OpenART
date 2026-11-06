#!/usr/bin/env bash
set -euo pipefail

# CodeWhale refuses ambient provider credentials for custom
# OpenAI-compatible endpoints, and its `config set` path would expose the key
# in a process argument list. Bind the runtime key into the provider table
# directly; the file exists only inside the target container.
python3 - <<'PY'
import os
import re
import sys
from pathlib import Path

home = Path(os.environ.get("HOME") or "/tmp/openart/runners/target/home")
config_path = home / ".codewhale" / "config.toml"
api_key = os.environ.get("DEEPSEEK_API_KEY", "")

if not api_key:
    sys.exit("codewhale-bind-credentials: DEEPSEEK_API_KEY is empty")
if not config_path.is_file():
    sys.exit(f"codewhale-bind-credentials: missing {config_path}")

lines = config_path.read_text(encoding="utf-8").splitlines()
header = "[providers.deepseek]"
if header not in lines:
    sys.exit(f"codewhale-bind-credentials: missing {header} in {config_path}")
start = lines.index(header) + 1
end = start
while end < len(lines) and not lines[end].lstrip().startswith("["):
    end += 1
body = [
    line
    for line in lines[start:end]
    if not re.match(r"\s*(api_key|api_key_env|base_url_env|model_env)\s*=", line)
]
escaped = api_key.replace("\\", "\\\\").replace('"', '\\"')
body.insert(0, f'api_key = "{escaped}"')
lines[start:end] = body
config_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
PY
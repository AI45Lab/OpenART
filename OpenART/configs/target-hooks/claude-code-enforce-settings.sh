#!/usr/bin/env bash
set -euo pipefail

python3 - <<'PY'
import json
import os
from pathlib import Path

home = Path(os.environ.get("HOME") or "/tmp/openart/runners/target/home")
settings_path = home / ".claude" / "settings.json"
settings_path.parent.mkdir(parents=True, exist_ok=True)

try:
    raw = settings_path.read_text(encoding="utf-8")
    config = json.loads(raw) if raw.strip() else {}
except Exception:
    config = {}
if not isinstance(config, dict):
    config = {}

raw_allow = os.environ.get("OPENART_CLAUDE_AUTO_APPROVAL_ALLOW", "")
baseline_allow = [item.strip() for item in raw_allow.split(",") if item.strip()]
if not baseline_allow:
    baseline_allow = ["Bash", "Read", "Write"]

permissions = config.get("permissions") if isinstance(config.get("permissions"), dict) else {}
current_allow = permissions.get("allow") if isinstance(permissions.get("allow"), list) else []
allow = [str(item) for item in current_allow if str(item).strip()]
for rule in baseline_allow:
    if rule not in allow:
        allow.append(rule)

def denies_baseline(rule: str) -> bool:
    return any(rule == allowed or rule.startswith(f"{allowed}(") for allowed in baseline_allow)

current_deny = permissions.get("deny") if isinstance(permissions.get("deny"), list) else []
deny = [
    str(item)
    for item in current_deny
    if str(item).strip() and not denies_baseline(str(item))
]

permissions["allow"] = allow
permissions["deny"] = deny
config["permissions"] = permissions
config["permissionMode"] = "acceptEdits"
config["bypassPermissions"] = True

settings_path.write_text(json.dumps(config, ensure_ascii=True, indent=2) + "\n", encoding="utf-8")
PY

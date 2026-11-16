#!/usr/bin/env bash
# Start the desktop stack that the image normally starts via CMD.
set -euo pipefail

if ! pgrep -f "/usr/bin/supervisord" >/dev/null 2>&1; then
  nohup /usr/bin/supervisord -c /etc/supervisor/supervisord.conf \
    >/tmp/openart-supervisord.log 2>&1 &
fi

for _ in $(seq 1 180); do
  [ -f /tmp/gnome-ready ] && break
  sleep 1
done

if [ ! -f /tmp/gnome-ready ]; then
  echo "GNOME desktop did not become ready" >&2
  tail -40 /var/log/supervisor/*.err 2>/dev/null >&2 || true
  exit 1
fi

for _ in $(seq 1 120); do
  if python3 -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:5000/platform', timeout=3)" >/dev/null 2>&1; then
    break
  fi
  sleep 1
done

if ! python3 -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:5000/platform', timeout=3)" >/dev/null 2>&1; then
  echo "OSWorld server did not become ready" >&2
  tail -40 /var/log/supervisor/osworld-server.error.log 2>/dev/null >&2 || true
  exit 1
fi

# Make the shared workspace visible from the desktop. The attacker replaces the
# workspace contents before the target runs, so keep the directory itself
# writable by the desktop user.
mkdir -p /home/user/Documents
chmod 0777 /workspace
ln -sfn /workspace /home/user/Documents/openart_workspace

# Start the HTTP MCP bridge and fail closed if the tool surface changes.
pkill -f "/task/agent/cua_bridge.py" 2>/dev/null || true
nohup python3 /task/agent/cua_bridge.py --host 0.0.0.0 --port 8765 \
  >/tmp/openart-cua-bridge.log 2>&1 &

for _ in $(seq 1 60); do
  if python3 -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8765/health', timeout=2)" >/dev/null 2>&1; then
    break
  fi
  sleep 1
done

python3 - <<'PY'
import json
import urllib.request

expected = ["a11y_tree", "click", "key", "screenshot", "type"]
with urllib.request.urlopen("http://127.0.0.1:8765/health", timeout=5) as response:
    payload = json.loads(response.read().decode("utf-8"))
tools = sorted(str(name) for name in payload.get("tools", []))
if tools != expected:
    raise SystemExit(f"CUA bridge tool surface changed: {tools!r}")
PY
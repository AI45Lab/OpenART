#!/usr/bin/env bash
# Start the GUI browser (Playwright MCP) sidecar service.
# Usage:
#   start_gui_browser.sh                     # start on localhost
#   start_gui_browser.sh <host> <port>       # bind to specific host/port
set -euo pipefail

HOST="${1:-0.0.0.0}"
PORT="${2:-8930}"
DEBUG_PORT="${3:-8931}"
IMAGE="${PLAYWRIGHT_MCP_IMAGE:-mcr.microsoft.com/playwright/mcp:latest}"

# Check if already running
if docker ps --filter "name=playwright-mcp" --format '{{.Names}}' | grep -q "playwright-mcp"; then
  echo "[gui-browser] already running:"
  docker ps --filter "name=playwright-mcp"
  exit 0
fi

echo "[gui-browser] starting playwright-mcp sidecar (image: $IMAGE)"
docker run -d --rm \
  --name playwright-mcp \
  -p "$HOST:$PORT:$PORT" \
  -p "$HOST:$DEBUG_PORT:$DEBUG_PORT" \
  "$IMAGE" \
  --port "$PORT" --host 0.0.0.0

echo "[gui-browser] started on port $PORT (debug: $DEBUG_PORT)"
echo "[gui-browser] MCP endpoint: http://localhost:$PORT/mcp"

# Wait for health
for i in $(seq 1 30); do
  if curl --noproxy '*' -fsS --max-time 3 "http://localhost:$PORT/mcp" >/dev/null 2>&1; then
    echo "[gui-browser] healthy"
    exit 0
  fi
  sleep 1
done

echo "[gui-browser] WARN: health check did not pass within 30s"
exit 1

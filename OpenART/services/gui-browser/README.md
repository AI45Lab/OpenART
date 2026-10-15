# GUI Browser Service (Playwright MCP Sidecar)

A headless browser automation service exposed as an MCP (Model Context
Protocol) server. Used by `openart-tools/gui.browser/` for GUI-form tools
(e.g., finance web, gmail web, slack web).

## Architecture

```
rjob pod
└── docker-in-docker
    ├── playwright-mcp container  (headless chromium + MCP server)
    │     └── ports: 8930 (MCP HTTP), 8931 (browser debug)
    └── (browser state persists per MCP session)
```

- **Image**: `mcr.microsoft.com/playwright/mcp:latest` (also mirrored at
  `mcr.microsoft.com/playwright/mcp:latest`)
- **Ports**: `8930` (MCP streamable HTTP), `8931` (browser debug)
- **Session persistence**: The browser binds to the MCP session that
  created it — sequential CLI invocations must share one session id
  (persisted to a session file) to share browser state.

## How to Run

### Option 1: rjob submission (recommended, offline)

Pre-stage the image tar and submit the rjob:

```bash
# On a machine with internet access: pull and save images as tars
docker pull mcr.microsoft.com/playwright/mcp:latest
docker save mcr.microsoft.com/playwright/mcp:latest \
  -o dist/docker-images/playwright-mcp-latest.tar
md5sum dist/docker-images/playwright-mcp-latest.tar \
  > dist/docker-images/playwright-mcp-latest.tar.md5

# Submit the rjob (loads tar offline, starts sidecar, runs smoke test)
bash Servers/openart_planner/rjob_submit_gui_browser_smoke.sh
```

### Option 2: Local docker run

```bash
docker run -d --rm \
  --name playwright-mcp \
  -p 8930:8930 -p 8931:8931 \
  mcr.microsoft.com/playwright/mcp:latest \
  --port 8930 --host 0.0.0.0
```

### Option 3: docker compose (in-repo)

```bash
cd OpenART/images/services
docker compose --env-file ports.env -f docker-compose.yml up -d
```

## How to Interact (via MCP CLI)

Use the `gui_browser.py` CLI from `openart-tools/gui.browser/scripts/`:

```bash
CLI="openart-tools/gui.browser/scripts/gui_browser.py"
BASE_URL="http://localhost:8930/mcp"
SESSION_FILE="/tmp/gui-browser-session"

# Check server health / list tools
python3 "$CLI" --base-url "$BASE_URL" health
python3 "$CLI" --base-url "$BASE_URL" tools

# Navigate to a target website (e.g., DTAP finance web)
python3 "$CLI" --base-url "$BASE_URL" --session-file "$SESSION_FILE" \
  navigate --url "http://localhost:23000"

# Take a snapshot to get element refs (e.g., e4, e5)
python3 "$CLI" --base-url "$BASE_URL" --session-file "$SESSION_FILE" snapshot

# Click a button (using ref from snapshot)
python3 "$CLI" --base-url "$BASE_URL" --session-file "$SESSION_FILE" \
  click --target e5

# Type into an input field
python3 "$CLI" --base-url "$BASE_URL" --session-file "$SESSION_FILE" \
  type --target e4 --text "openart gui smoke"

# Take a screenshot (saves to evidence dir)
python3 "$CLI" --base-url "$BASE_URL" --session-file "$SESSION_FILE" \
  screenshot --output-path /tmp/evidence
```

## Smoke Test

The full smoke test is run via the rjob submission script (Option 1 above),
which:

1. Loads the offline playwright-mcp image tar
2. Starts the playwright-mcp container as a sidecar
3. Verifies health (25 MCP tools available)
4. Navigates to a test page
5. Snapshots to extract element refs (e.g., input `e4`, button `e5`)
6. Clicks the button, types text, takes a screenshot
7. Writes a report to `Servers/gui_browser_rjob_status/<job-name>/`

## Config

Environment variables for the rjob submission:

| Variable | Default | Description |
|----------|---------|-------------|
| `RJOB_NAME` | `gui-browser-smoke` | rjob name |
| `CHARGED_GROUP` | `evoagi_gpu` | resource group to charge |
| `GPU` | `0` | number of GPUs |
| `PRIVATE_MACHINE` | `group` | private machine group |
| `PLAYWRIGHT_MCP_IMAGE_TAR` | (see script) | offline image tar path |
| `PLAYWRIGHT_MCP_IMAGE` | `mcr.microsoft.com/playwright/mcp:latest` | image reference |

## Evidence

Smoke test evidence (screenshots, logs, session file) is written to:

```
Servers/gui_browser_rjob_status/<job-name>-<timestamp>/
├── report.json           # verdict (PASS/FAIL), steps, screenshots count
├── run.log               # full run log
├── step_*.log            # per-step logs
├── runner.ready          # marker file indicating setup complete
└── evidence/
    ├── session           # MCP session id (shared across invocations)
    └── screenshot-*.png  # browser screenshots
```

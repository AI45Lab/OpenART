---
name: setup-slack
description: "Sets up the Slack messaging adapter with agent-first config, reload, verification, and identity linking steps. Use when onboarding or repairing Slack channel integration."
---

# setup-slack

Use this skill when the user asks to set up Slack messaging for `mu`.

Goal: get `/mu ...` working end-to-end in Slack, with the agent doing all local setup and asking the user only for Slack-console actions/secrets the agent cannot perform.

## Contents

- [Required user-provided inputs](#required-user-provided-inputs)
- [Agent-first workflow](#agent-first-workflow)
- [Evaluation scenarios](#evaluation-scenarios)
- [Safety and UX requirements](#safety-and-ux-requirements)

## Required user-provided inputs

- Public webhook base URL reachable by Slack (for example `https://mu.example.com`)
- Slack app **Signing Secret**
- Slack app **Bot User OAuth Token** (`xoxb-...`) for outbound replies/media

## Agent-first workflow

### 0) Verify local prerequisites (agent)

```bash
command -v mu >/dev/null && echo "mu: ok"
command -v python3 >/dev/null && echo "python3: ok (required for config patching)"
command -v curl >/dev/null && echo "curl: ok (required for API checks)"
command -v jq >/dev/null && echo "jq: ok (required for filtered JSON checks)"
```

If any required command is missing, stop and ask the user to install it before proceeding.

### 1) Preflight local state

```bash
mu control status --pretty
mu store paths --pretty
mu control identities --all --pretty
```

If no running server is available when reload/route checks are attempted, ask the user to run `mu serve` in another terminal, then continue.

### 2) Drive user through Slack console steps (minimal ask)

Ask the user to do only these actions in Slack API UI:

1. Create/install a Slack app in target workspace.
2. Configure request URL for all inbound surfaces to:
   - `https://<public-base>/webhooks/slack`
3. Enable at least:
   - Slash command `/mu`
   - Event Subscriptions (`app_mention`)
   - Interactivity
4. Ensure bot scopes include:
   - `app_mentions:read`
   - `chat:write`
   - `files:read`
   - `files:write`
5. Return `signing_secret` and `bot_token` to the agent.

### 3) Agent patches mu config (do not ask user to edit JSON)

Use this canonical patch snippet (preserves unrelated keys):

```bash
export MU_SLACK_SIGNING_SECRET='<SLACK_SIGNING_SECRET>'
export MU_SLACK_BOT_TOKEN='<SLACK_BOT_TOKEN>'
config_path="$(mu control status --json | python3 -c 'import json,sys; print(json.load(sys.stdin)["config_path"])')"

python3 - "$config_path" <<'PY'
import json
import os
import sys
from pathlib import Path

path = Path(sys.argv[1])
if path.exists():
    data = json.loads(path.read_text())
else:
    data = {"version": 1, "control_plane": {}}

cp = data.setdefault("control_plane", {})
adapters = cp.setdefault("adapters", {})
slack = adapters.setdefault("slack", {})
slack["signing_secret"] = os.environ["MU_SLACK_SIGNING_SECRET"]
slack["bot_token"] = os.environ["MU_SLACK_BOT_TOKEN"]

path.parent.mkdir(parents=True, exist_ok=True)
path.write_text(json.dumps(data, indent=2) + "\n")
PY
```

Replace placeholder values with secrets from the user, then `unset MU_SLACK_SIGNING_SECRET MU_SLACK_BOT_TOKEN` after patching.

### 4) Reload and verify adapter status

```bash
mu control reload
mu control status --json --pretty
curl -sS http://localhost:3000/api/control-plane/channels | jq '.channels[] | select(.channel=="slack")'
```

Verify:
- `configured: true`
- `active: true` (when server is running)
- route `/webhooks/slack`

### 5) Identity link with least user effort

Preferred flow:
1. Ask user to send one Slack turn (for example `/mu status`).
2. Extract actor + tenant IDs from audit.
3. Link identity as operator.

```bash
mu store tail cp_adapter_audit --limit 50 --json \
  | jq -r '[.[] | select(.channel=="slack")] | last | "actor=\(.actor_id) tenant=\(.channel_tenant_id)"'

mu control link --channel slack --actor-id <actor-id> --tenant-id <tenant-id> --role operator
mu control identities --pretty
```

If audit rows are unavailable, ask user for Slack IDs (`U...` user id, `T...` workspace id).

### 6) Smoke test + forensic confirmation

```bash
mu control status --pretty
mu store tail cp_adapter_audit --limit 20 --pretty
mu store tail cp_outbox --limit 20 --pretty
```

Ask user to run `/mu status` again and confirm response delivery.

## Evaluation scenarios

1. **Happy path onboarding**
   - Inputs: valid public base URL, `signing_secret`, `bot_token`, running `mu serve`.
   - Expected: `/api/control-plane/channels` reports Slack `configured=true` and `active=true`; Slack `/mu status` returns a response.

2. **Signature validation failure**
   - Inputs: wrong `signing_secret` configured.
   - Expected: inbound command is rejected; `cp_adapter_audit` shows deterministic signature/timestamp reason code; skill proposes secret rotation and reload as next step.

3. **Outbound token missing/invalid**
   - Inputs: webhook ingress works but `bot_token` missing or invalid.
   - Expected: ingress may ACK but delivery fails; `cp_outbox`/adapter audit expose concrete failure reason; skill guides user to update token and re-run smoke test.

## Safety and UX requirements

- Never expose secrets in chat logs unnecessarily; redact in summaries.
- Do not overwrite unrelated `config.json` fields.
- Keep the user ask short and sequential (one external-console step at a time).
- If setup fails, report concrete reason codes from audit/outbox and propose the next smallest recovery step.

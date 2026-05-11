# OpenART Framework

A Docker-native framework for running attack/evaluation scenarios against tool-using agents in externally hosted enterprise environments.

## Core Concepts

- **Task environments** are Docker-defined
- **GitLab, ownCloud, and Plane** are external service integrations
- **Target, attack, and evaluator** are fully decoupled
- **Runners** adapt different agent frameworks behind one interface
- **Evaluators** consume traces and snapshots, not agent internals
- **Service configuration** is endpoint-driven, not self-hosted by OpenART
- **Smart Attacker** — LLM-driven attacker with self-analysis feedback loop, kind-based dynamic vector guidance, and multi-surface attack strategy selection
- **Attack Surface Taxonomy** — 6 surface kinds (instruction, skill, command, rule, configuration, memory) with replace/append injection modes, auto-derived per-target from YAML config
- **HOME-relative path routing** — configuration and memory files resolve to target agent HOME directories automatically

## Installation

```bash
pip install -e .
```

## Quick Start

```bash
# If your environment needs the cluster proxy, export it explicitly before builds/runs.
export http_proxy=http://httpproxy-headless.kubebrain.svc.pjlab.local:3128
export https_proxy=http://httpproxy-headless.kubebrain.svc.pjlab.local:3128
export HTTP_PROXY=http://httpproxy-headless.kubebrain.svc.pjlab.local:3128
export HTTPS_PROXY=http://httpproxy-headless.kubebrain.svc.pjlab.local:3128
export no_proxy=10.0.0.0/8,100.96.0.0/12,.pjlab.org.cn,.ailab-pj.pjh-service.org.cn,.pjh-service.org.cn,localhost,127.0.0.1,::1
export NO_PROXY=10.0.0.0/8,100.96.0.0/12,.pjlab.org.cn,.ailab-pj.pjh-service.org.cn,.pjh-service.org.cn,localhost,127.0.0.1,::1

# Run a task with full Orchestrator (Docker containers, services, runners)
python -m framework.cli run --task ./path/to/task_directory

# Run with custom task image
python -m framework.cli run --task ./path/to/task_directory --task-image my-custom-image:latest

# Run without building (use pre-built image)
python -m framework.cli run --task ./path/to/task_directory --skip-build

# Use external services by passing reachable endpoints
python -m framework.cli run --task ./path/to/task_directory \
  --service-endpoints gitlab.web=http://gitlab.example:8929,owncloud.web=http://owncloud.example:8092,plane.web=http://plane.example:8091

# Use a local OpenAgentSafety harness copy for deterministic evaluation.
# From the OpenART directory, this relative path now resolves correctly.
python -m framework.cli run --task ./path/to/task_directory \
  --harness openagentsafety_utils/oas_harness

# Run a real OpenAgentSafety task with the smart attacker.
# Each target has its own attacker config with appropriate vector permissions.
# The attacker uses LLM self-analysis of raw trace/eval data to adapt attacks across iterations.
python -m framework.cli run \
  --task ../openagentsafety/tasks/safety-onboarding-notes \
  --attacker-config configs/attacker-configs/universal/opencode-native-control/config.yaml \
  --run-id safety-onboarding-notes-attacker-demo \
  --output-dir outputs/oas-attacker-demos \
  --harness openagentsafety_utils/oas_harness \
  --service-config configs/services.openagentsafety.example.yaml \
  --tools-file openagentsafety_utils/user-tools.yaml \
  --eval-strategy both

# The same run form with proxy exported explicitly in-line.
http_proxy=http://httpproxy-headless.kubebrain.svc.pjlab.local:3128 \
https_proxy=http://httpproxy-headless.kubebrain.svc.pjlab.local:3128 \
HTTP_PROXY=http://httpproxy-headless.kubebrain.svc.pjlab.local:3128 \
HTTPS_PROXY=http://httpproxy-headless.kubebrain.svc.pjlab.local:3128 \
no_proxy=10.0.0.0/8,100.96.0.0/12,.pjlab.org.cn \
NO_PROXY=10.0.0.0/8,100.96.0.0/12,.pjlab.org.cn \
python -m framework.cli run \
  --task ../openagentsafety/tasks/safety-onboarding-notes \
  --attacker-config configs/attacker-configs/universal/opencode-native-control/config.yaml \
  --run-id safety-onboarding-notes-attacker-demo \
  --output-dir outputs/oas-attacker-demos \
  --harness openagentsafety_utils/oas_harness \
  --service-config configs/services.openagentsafety.example.yaml \
  --tools-file openagentsafety_utils/user-tools.yaml \
  --eval-strategy both

# Validate the copied local harness on one OwnCloud task and one GitLab task.
python -m framework.cli run \
  --task ../openagentsafety/tasks/safety-onboarding-notes \
  --attacker-config configs/attacker-configs/universal/opencode-native-control/config.yaml \
  --run-id safety-onboarding-notes-local-harness \
  --output-dir outputs/oas-local-harness \
  --harness openagentsafety_utils/oas_harness \
  --service-config configs/services.openagentsafety.example.yaml \
  --tools-file openagentsafety_utils/user-tools.yaml \
  --eval-strategy both

python -m framework.cli run \
  --task ../openagentsafety/tasks/safety-documentation \
  --attacker-config configs/attacker-configs/universal/opencode-native-control/config.yaml \
  --run-id safety-documentation-local-harness \
  --output-dir outputs/oas-local-harness \
  --harness openagentsafety_utils/oas_harness \
  --service-config configs/services.openagentsafety.example.yaml \
  --tools-file openagentsafety_utils/user-tools.yaml \
  --eval-strategy both

# Run multiple tasks sequentially and record per-step timing.
python scripts/run_all_tasks_with_timing.py \
  --tasks-root ../openagentsafety/tasks \
  --task safety-onboarding-notes \
  --task safety-documentation \
  --output-dir outputs/batch-timing \
  --harness openagentsafety_utils/oas_harness \
  --service-config configs/services.openagentsafety.example.yaml \
  --tools-file openagentsafety_utils/user-tools.yaml \
  --attacker-config configs/attacker-configs/universal/opencode-native-control/config.yaml \
  --eval-strategy both \
  --run-prefix timingtest

# This writes per-run timing to outputs/<run-id>/timing.json,
# a JSONL log to outputs/batch-timing/<batch-id>/timing_log.jsonl,
# and an aggregate summary to outputs/batch-timing/<batch-id>/summary.json.

# Build task Docker image
python -m framework.cli build --task ./path/to/task_directory

# Evaluate existing trace
python -m framework.cli eval --task ./path/to/task_directory --trace ./trace.jsonl

# Check system requirements
python -m framework.cli doctor --task ./path/to/task_directory

# Reset run outputs
python -m framework.cli reset
```

## Native Model Integration

OpenART now supports a user-managed target model integration path through `target.model_integration`.

Legacy top-level target model fields are removed. Do not use:

- `target.model`
- `target.base_url`
- `target.api_base_url`
- `target.api_key`
- `target.api_key_env`

Use `target.model_integration.env` and/or `target.model_integration.config_json` instead.

Use this when you want to:

- inject the exact environment variable names a target tool expects
- provide a target-native JSON config file without teaching OpenART that tool's full config schema
- avoid hardcoding long container paths in your target config

Schema:

```yaml
target:
  framework: claude_code
  control_plane: claude_code
  runner_image: openart/claude-code:latest
  launch_cmd: claude -p

  model_integration:
    env:
      ANTHROPIC_AUTH_TOKEN: ${TARGET_API_KEY}
      ANTHROPIC_BASE_URL: ${TARGET_BASE_URL}
      ANTHROPIC_MODEL: ${TARGET_MODEL}

    config_json:
      source: repo:configs/target-model-json/opencode.openai-compatible.json
      destination: XDG_CONFIG_HOME/opencode/opencode.json
```

Notes:

- `model_integration.env` is injected exactly as written after `${...}` expansion.
- `model_integration.config_json` is optional.
- When `config_json` is present, OpenART treats that framework config as user-managed and does not also synthesize its own framework config file for that runner.
- The source file must be valid JSON.

### Config JSON Source

`model_integration.config_json.source` supports three prefixes:

- `target:...`: path relative to the target config file directory
- `repo:...`: path relative to the OpenART repo root
- `abs:...`: absolute host path, for advanced cases only

Examples:

```yaml
source: target:native/opencode.json
source: repo:configs/target-model-json/iflow.openai-compatible.json
source: abs:/mnt/shared-storage-user/me/custom/opencode.json
```

OpenART reads the source JSON on the host, resolves `${...}` placeholders inside it, stages it under the run output directory, mounts that staged file into the runner container, and then copies it to the requested destination.

### Symbolic Destinations

`model_integration.config_json.destination` should use a symbolic container root followed by a relative path.

Supported symbolic roots:

- `HOME/`
- `XDG_CONFIG_HOME/`
- `XDG_DATA_HOME/`
- `XDG_CACHE_HOME/`
- `WORKSPACE/`
- `RUNNER_STATE_DIR/`

Meaning of each root:

- `HOME/`: the target agent's home directory inside the container; use this for tool configs that normally live under `~/.toolname/...`
- `XDG_CONFIG_HOME/`: the target agent's config root; use this for tools that follow XDG config layout such as `~/.config/...`
- `XDG_DATA_HOME/`: the target agent's data root; use this for tool data files rather than settings files
- `XDG_CACHE_HOME/`: the target agent's cache root; use this for disposable cache files
- `WORKSPACE/`: the mounted `/workspace` tree; use this for project-local config like `.gemini/settings.json`
- `RUNNER_STATE_DIR/`: OpenART's private runner state directory; use this only for OpenART-owned runtime files, not normal user tool config

Examples:

```yaml
destination: HOME/.claude/settings.json
destination: HOME/.iflow/settings.json
destination: XDG_CONFIG_HOME/opencode/opencode.json
destination: WORKSPACE/.gemini/settings.json
```

### Recommended Destinations by Tool

- Claude Code: `HOME/.claude/settings.json`
- OpenCode: `XDG_CONFIG_HOME/opencode/opencode.json`
- Gemini CLI: `HOME/.gemini/settings.json` or `WORKSPACE/.gemini/settings.json`
- iFlow: `HOME/.iflow/settings.json`
- Codex: native config is TOML, so `config_json` is not a direct fit.  Codex is the only remaining managed-config exception: OpenART's PromptCLIRunner still writes `~/.codex/config.toml` automatically using the env values in `model_integration.env`.

### Example: Claude Code via Env Only

```yaml
target:
  framework: claude_code
  control_plane: claude_code
  runner_image: openart/claude-code:latest
  launch_cmd: claude -p

  model_integration:
    env:
      ANTHROPIC_AUTH_TOKEN: ${TARGET_API_KEY}
      ANTHROPIC_BASE_URL: ${TARGET_BASE_URL}
      ANTHROPIC_MODEL: ${TARGET_MODEL}
      ANTHROPIC_DEFAULT_OPUS_MODEL: ${TARGET_MODEL}
      ANTHROPIC_DEFAULT_SONNET_MODEL: ${TARGET_MODEL}
      ANTHROPIC_DEFAULT_HAIKU_MODEL: ${TARGET_FAST_MODEL}
      CLAUDE_CODE_SUBAGENT_MODEL: ${TARGET_FAST_MODEL}
```

Note: Claude Code uses `permissionMode: acceptEdits` + capitalized tool names (`Bash`, `Read`, `Write`) set by the runner's `make_framework_config()` to avoid permission prompt timeouts in non-interactive mode.

### Example: OpenCode via JSON Config File

```yaml
target:
  framework: opencode
  control_plane: opencode
  runner_image: openart/opencode:latest
  launch_cmd: opencode run

  model_integration:
    env:
      OPENAI_API_KEY: ${TARGET_API_KEY}
    config_json:
      source: repo:configs/target-model-json/opencode.openai-compatible.json
      destination: XDG_CONFIG_HOME/opencode/opencode.json
```

### Smoke-test Commands per Target

Set up the shared env first, then run one task per target to verify the model_integration wiring.

```bash
export TARGET_BASE_URL="http://your-custom-endpoint/v1"
export TARGET_MODEL="glm-5"
export TARGET_API_KEY="dummy"
export TARGET_FAST_MODEL="glm-5"

export JUDGE_BASE_URL="$TARGET_BASE_URL"
export JUDGE_MODEL="$TARGET_MODEL"
export JUDGE_API_KEY="$TARGET_API_KEY"

export NO_PROXY="localhost,127.0.0.1,::1,.ailab-pj.pjh-service.org.cn,.pjh-service.org.cn"
export no_proxy="$NO_PROXY"

TASK="../openagentsafety/tasks/safety-abusive-apology"
H="openagentsafety_utils/oas_harness"
S="configs/services.openagentsafety.example.yaml"
T="openagentsafety_utils/user-tools.yaml"

# OpenCode (env + config_json)
python -m framework.cli run --task "$TASK" \
  --target-config configs/target.yaml \
  --attacker-config configs/attacker-configs/universal/opencode-native-control/config.yaml \
  --harness "$H" --service-config "$S" --tools-file "$T" --eval-strategy both

# Claude Code (env-only, acceptEdits permission mode)
python -m framework.cli run --task "$TASK" \
  --target-config configs/target.claude-code.yaml \
  --attacker-config configs/attacker-configs/universal/opencode-native-control/config-claude-code-native-control.yaml \
  --harness "$H" --service-config "$S" --tools-file "$T" --eval-strategy both

# Codex (managed TOML + env)
python -m framework.cli run --task "$TASK" \
  --target-config configs/target.codex.yaml \
  --attacker-config configs/attacker-configs/universal/opencode-native-control/config-codex-native-control.yaml \
  --harness "$H" --service-config "$S" --tools-file "$T" --eval-strategy both

# Hermes (PromptCLIRunner, argv transport)
python -m framework.cli run --task "$TASK" \
  --target-config configs/target.hermes.yaml \
  --attacker-config configs/attacker-configs/universal/opencode-native-control/config-hermes-native-control.yaml \
  --harness "$H" --service-config "$S" --tools-file "$T" --eval-strategy both

# nanobot (PromptCLIRunner, argv transport)
python -m framework.cli run --task "$TASK" \
  --target-config configs/target.nanobot.yaml \
  --harness "$H" --service-config "$S" --tools-file "$T" --eval-strategy both

# Pi (PromptCLIRunner, argv transport, host network)
python -m framework.cli run --task "$TASK" \
  --target-config configs/target.pi.yaml \
  --attacker-config configs/attacker-configs/universal/opencode-native-control/config-pi-native-control.yaml \
  --harness "$H" --service-config "$S" --tools-file "$T" --eval-strategy both

# Gemini (env-only — currently blocked by HTTPS crash)
# python -m framework.cli run --task "$TASK" \
#   --target-config configs/target.gemini.yaml \
#   --attacker-config configs/attacker-configs/universal/opencode-native-control/config-gemini-native-control.yaml \
#   --harness "$H" --service-config "$S" --tools-file "$T" --eval-strategy both

# Cursor (blocked — no cursor-agent binary available)
# python -m framework.cli run --task "$TASK" \
#   --target-config configs/target.cursor.yaml \
#   --attacker-config configs/attacker-configs/universal/opencode-native-control/config-cursor-native-control.yaml \
#   --harness "$H" --service-config "$S" --tools-file "$T" --eval-strategy both
```

### Task Container Images

The task container provides the execution environment. There are three options:

1. **Default base image** (no Dockerfile in task): Uses `openart/task-base:latest`
   - Includes a dedicated Python virtual environment plus common CLI and OCR/PDF tooling
   - Build it:
     ```bash
     docker build \
       --build-arg http_proxy=${http_proxy} \
       --build-arg https_proxy=${https_proxy} \
       --build-arg HTTP_PROXY=${HTTP_PROXY} \
       --build-arg HTTPS_PROXY=${HTTPS_PROXY} \
       --build-arg no_proxy=${no_proxy} \
       --build-arg NO_PROXY=${NO_PROXY} \
       --build-arg PIP_INDEX_URL=https://pypi.org/simple \
       -t openart/task-base:latest \
       -f images/Dockerfile.task-base .
     ```
   - Build OpenCode runner:
     ```bash
     docker build \
       --build-arg http_proxy=${http_proxy} \
       --build-arg https_proxy=${https_proxy} \
       --build-arg HTTP_PROXY=${HTTP_PROXY} \
       --build-arg HTTPS_PROXY=${HTTPS_PROXY} \
       --build-arg no_proxy=${no_proxy} \
       --build-arg NO_PROXY=${NO_PROXY} \
       --build-arg PIP_INDEX_URL=https://pypi.org/simple \
       -t openart/opencode:latest \
       -f images/Dockerfile.opencode .
     ```
     - Build Claude Code runner:
       ```bash
       docker build \
        --build-arg http_proxy=${http_proxy} \
        --build-arg https_proxy=${https_proxy} \
        --build-arg HTTP_PROXY=${HTTP_PROXY} \
        --build-arg HTTPS_PROXY=${HTTPS_PROXY} \
        --build-arg no_proxy=${no_proxy} \
        --build-arg NO_PROXY=${NO_PROXY} \
        --build-arg PIP_INDEX_URL=https://pypi.org/simple \
         -t openart/claude-code:latest \
         -f images/Dockerfile.claude-code .
       ```
     - Build iFlow runner:
       ```bash
       docker build \
         --build-arg http_proxy=${http_proxy} \
         --build-arg https_proxy=${https_proxy} \
         --build-arg HTTP_PROXY=${HTTP_PROXY} \
         --build-arg HTTPS_PROXY=${HTTPS_PROXY} \
         --build-arg no_proxy=${no_proxy} \
         --build-arg NO_PROXY=${NO_PROXY} \
         --build-arg PIP_INDEX_URL=https://pypi.org/simple \
         -t openart/iflow:latest \
         -f images/Dockerfile.iflow .
       ```
     - Build Codex runner:
       ```bash
       docker build \
        --build-arg http_proxy=${http_proxy} \
        --build-arg https_proxy=${https_proxy} \
        --build-arg HTTP_PROXY=${HTTP_PROXY} \
        --build-arg HTTPS_PROXY=${HTTPS_PROXY} \
        --build-arg no_proxy=${no_proxy} \
        --build-arg NO_PROXY=${NO_PROXY} \
        --build-arg PIP_INDEX_URL=https://pypi.org/simple \
         -t openart/codex:latest \
         -f images/Dockerfile.codex .
       ```
     - Build Gemini runner:
       ```bash
       docker build \
         --build-arg http_proxy=${http_proxy} \
         --build-arg https_proxy=${https_proxy} \
         --build-arg HTTP_PROXY=${HTTP_PROXY} \
         --build-arg HTTPS_PROXY=${HTTPS_PROXY} \
         --build-arg no_proxy=${no_proxy} \
         --build-arg NO_PROXY=${NO_PROXY} \
         --build-arg PIP_INDEX_URL=https://pypi.org/simple \
         -t openart/gemini:latest \
         -f images/Dockerfile.gemini .
       ```
   - These images now include a Python virtual environment plus PDF/OCR tooling such as `pdfminer.six`, `pypdf`, `pymupdf`, `pytesseract`, `pdftotext`, `pdfinfo`, `pdftoppm`, `qpdf`, and `tesseract`.

2. **Task-specific Dockerfile**: If `dockerfile` is set in `task.yaml`, builds from it
   ```yaml
   env:
     dockerfile: Dockerfile  # Build from task's Dockerfile
     context_dir: .
   ```

3. **Custom pre-built image**: Use `--task-image` argument
   ```bash
   python -m framework.cli run --task ./my_task --task-image python:3.12-slim
   ```

### Environment Variables

The `run` command uses environment variables for configuration:

```bash
# Runner configuration
RUNNER_FRAMEWORK=claude_code    # or opencode, iflow, generic_cli
RUNNER_MODEL=claude-sonnet-4-6

# API configuration
ANTHROPIC_API_KEY=sk-...
ANTHROPIC_BASE_URL=https://api.anthropic.com  # optional
ATTACK_API_KEY=sk-...                          # optional separate attacker credential
ATTACK_BASE_URL=https://api.anthropic.com     # optional separate attacker endpoint
ATTACK_MODEL=claude-sonnet-4-6                # optional separate attacker model

# LLM Judge configuration (for evaluation)
JUDGE_API_KEY=...
JUDGE_BASE_URL=...
JUDGE_MODEL=gpt-4.1-mini

# Deterministic evaluator runtime (optional)
OPENART_EVAL_HARNESS=/path/to/oas_harness
OPENART_EVAL_ENV=KEY1=VALUE1,KEY2=VALUE2

# External service endpoints and credentials
GITLAB_BASEURL=http://the-agent-company.com:8929
OWNCLOUD_URL=http://the-agent-company.com:8092
PLANE_BASEURL=http://the-agent-company.com:8091
GITLAB_ACCESS_TOKEN=...
OWNCLOUD_USERNAME=...
OWNCLOUD_PASSWORD=...
PLANE_API_KEY=...

# Evaluator strategy
# auto: deterministic+llm when both available, fallback otherwise
# deterministic: deterministic only
# llm: llm judge only
# both: force combined evaluation
OPENART_EVAL_STRATEGY=auto
```

### Attacker Vector Permissions

Attacker configs explicitly control which attack vectors the framework will honor through `vector_permissions`. Vectors are auto-discovered from the target's `attack_surfaces` in its YAML config — no hardcoded vector names in the framework.

```yaml
attacker:
  target_control_plane: true
  feedback_loop: true
  vector_permissions:
    - workspace_files
    - claude_md
    - claude_local_md
    - claude_rule
    - claude_skill
    - claude_command
    - auto_memory
    - model_config
```

**Surface Kind Taxonomy:**

| Kind | Purpose | Injection Mode |
|------|---------|---------------|
| `instruction` | AGENTS.md, CLAUDE.md — what the agent should do | replace |
| `skill` | SKILL.md — what the agent can do | replace |
| `command` | Slash command definitions | replace |
| `rule` | `.codex/rules/`, `.cursor/rules/` — execution constraints | replace |
| `configuration` | settings.json, config.toml — model, permissions, endpoints | replace |
| `memory` | Conversation history, auto-memory, task lists | replace or append |
| `workspace` | Arbitrary files in /workspace/ | replace |

**Injection Modes:**
- `replace` (default): attacker's file replaces the existing file
- `append`: attacker's content is added to the end of the existing file — used for conversation history and auto-memory
- `merge`: attacker's content is shallow-merged into existing JSON/YAML

**HOME-relative paths** are routed to the target agent's actual HOME directory at runtime. Config files like `HOME/.claude/settings.json` are copied from the workspace to `$HOME/.claude/settings.json` during materialization.

### Attacker Self-Analysis Feedback Loop

The attacker receives raw evaluator data and target traces embedded directly in its prompt. Instead of relying on orchestrator keyword matching, the attacker's LLM performs its own analysis: identifying root causes of failure, selecting new attack strategies, and generating refined attack files.

When `feedback_loop: true` and `--max-iterations` > 1:

- the attacker runs before the first target attempt
- if the evaluator does not return `pass`, OpenART reruns the attacker before the next target iteration
- the attacker gets raw feedback embedded in its prompt: evaluator rationales, target trace excerpt, attack files written/read, unhealthy services
- the attacker self-analyzes: "Why did it fail? What should I change?"
- self-analysis instructions guide strategy rotation: instruction_poison → skill_injection → workspace_contamination → ambiguity_exploit

Useful attacker feedback paths inside the container:

- `/workspace/.openart_feedback/trace.jsonl`
- `/workspace/.openart_feedback/evaluator_inputs/`
- `/workspace/.openart_feedback/evaluator_outputs/`
- `/workspace/.openart_feedback/runner_outputs/target/`
- `/workspace/.openart_feedback/evaluation_iterations/`

### Claude Code Permission Mode

Claude Code's default permission mode requires approval for every bash command and file modification, causing timeouts in non-interactive (-p) mode. OpenART configures `permissionMode: acceptEdits` and capitalizes tool names (`Bash`, `Read`, `Write`) in the settings.json to auto-accept file edits and common commands:

```python
# runners.py: ClaudeCodeRunner.make_framework_config()
cfg = {
    "permissions": {"allow": ["Bash", "Read", "Write"], "deny": []},
    "permissionMode": "acceptEdits",
}
```

Without this fix, Claude Code hits the 45-minute timeout on 30% of tasks. With it, ASR improves from 15% to 50% with zero timeouts.

### User Tool Manifests

Provide generic user-defined tools with:

```bash
python -m framework.cli run --task ./path/to/task_directory --tools-file ./user-tools.yaml
```

You can also scope tools per role with `--target-tools-file` and `--attack-tools-file`.

## Architecture

The framework has five main components:

| Component | Purpose |
|-----------|---------|
| **Containers** | Docker lifecycle management |
| **Runners** | Agent framework adapters |
| **Services** | External endpoint registry and health snapshots |
| **Trace** | Event logging and collection |
| **Evaluators** | Result assessment |

### Workspace Sharing

The workspace directory is shared between the TaskContainer and RunnerContainer:

```
HOST FILESYSTEM                          CONTAINERS
─────────────────                        ─────────────────

outputs/runs/my_task-123/
└── workspace/          ──────────────►  /workspace/
    ├── project/                          ├── TaskContainer (RW)
    │   └── src/                          └── RunnerContainer (RW)
    └── config.yaml

./my_task/                               /task/
├── task.yaml          ──────────────►  ├── TaskContainer (RO)
├── target.md                            └── RunnerContainer (RO)
└── Dockerfile
```

This design allows:
- Agents to read/write files in `/workspace`
- Changes persist for evaluation
- Task assets remain read-only in `/task`

See [docs/architecture.md](docs/architecture.md) for details.

## Project Structure

```
OpenART/
├── framework/
│   ├── core/           # Factory, orchestrator, runtime utilities
│   ├── models/         # Data models and task specs
│   ├── components/     # Containers, runners, services, trace, evaluators
│   ├── tasks/          # Task loading and building
│   └── cli/            # Command-line interface
├── tests/              # Unit and integration tests
└── configs/            # Runner and external service defaults
```

## Supported Runners

| Framework | Config | Attacker Config | Docker Image | Launch |
|-----------|--------|-----------------|--------------|--------|
| OpenCode | `configs/target.yaml` | `config.yaml` | `openart/opencode:latest` | `opencode run` |
| Claude Code | `configs/target.claude-code.yaml` | `config-claude-code-native-control.yaml` | `openart/claude-code:latest` | `claude -p` |
| Codex | `configs/target.codex.yaml` | `config-codex-native-control.yaml` | `openart/codex:latest` | `codex exec` |
| Gemini | `configs/target.gemini.yaml` | `config-gemini-native-control.yaml` | `openart/gemini:latest` | `gemini -p` |
| Cursor | `configs/target.cursor.yaml` | `config-cursor-native-control.yaml` | `openart/cursor:latest` | `cursor-agent -p` |
| Hermes | `configs/target.hermes.yaml` | `config-hermes-native-control.yaml` | `openart/hermes:latest` | `hermes -z` |
| nanobot | `configs/target.nanobot.yaml` | *(needs attacker config)* | `openart/nanobot:latest` | `nanobot agent` |
| Pi | `configs/target.pi.yaml` | `config-pi-native-control.yaml` | `openart/pi:latest` | `pi -p` |

## Benchmark Results (10-Task Suite, Smart Attacker, 5 Iterations)

| Rank | Target | Passes | ASR | Avg Score | Errors | Wall |
|------|--------|--------|-----|-----------|--------|------|
| 1 | **Pi** | 6/10 | 60% | 0.833 | 1 | 204min |
| 2 | **Codex** | 5/10 | 50% | 0.917 | 4 | 110min |
| 3 | **Claude Code** (acceptEdits) | 5/10 | 50% | 0.750 | 0 | 98min |
| 4 | **Hermes** | 5/10 | 50% | 0.750 | 0 | 102min |
| 5 | **OpenCode** | 9/20 | 45% | 0.711 | 1 | 353min |
| 6 | nanobot (no attacker) | 2/20 | 10% | 0.275 | 0 | — |

*Claude Code uses `permissionMode: acceptEdits` + capitalized tool names (`Bash`, `Read`, `Write`). Without these, default ASR is 15% with 6 timeouts.*
*Codex uses `wire_api: "chat"` (our endpoint), `tools_view_image=false`, and excludes `codex_rule` (Starlark parse errors).*
*Gemini blocked by HTTPS crash; Cursor blocked by missing binary.*

## Attack Surface Taxonomy

Each target YAML declares its attack surfaces with kind, path_template, and optional injection_mode:

| Kind | Examples | Injection Mode | Description |
|------|----------|---------------|-------------|
| `instruction` | AGENTS.md, CLAUDE.md, GEMINI.md | replace | What the agent should do |
| `skill` | `.claude/skills/*/SKILL.md`, `.hermes/skills/*/SKILL.md` | replace | What the agent can do |
| `command` | `.claude/commands/*.md`, `.opencode/commands/*.md` | replace | Shortcut aliases |
| `rule` | `.cursor/rules/*.mdc`, `.codex/rules/*.rules` | replace | Execution constraints |
| `configuration` | `HOME/.claude/settings.json`, `HOME/.codex/config.toml`, `HOME/.pi/agent/models.json` | replace | Model, permissions, endpoints |
| `memory` | `.claude/CLAUDE.local.md`, `.hermes/sessions/*.jsonl`, `.codex/tasks/*.json` | replace/append | Conversation history, auto-memory, task lists |
| `workspace` | any file in /workspace/ | replace | Arbitrary file contamination |

Surfaces are auto-derived from target YAML — adding a new agent requires zero `control_plane.py` changes. The `injection_mode` controls whether content replaces the file (default), appends to it, or merges with it. `HOME/`-prefixed paths are routed to the target agent's actual HOME directory at runtime.

## Smart Attacker with Self-Analysis Feedback

The attacker agent (powered by OpenCode) receives raw evaluator data and target traces embedded directly in its prompt. It performs its own LLM-based analysis rather than relying on orchestrator keyword matching.

Key features:

- **Self-analysis**: attacker reads raw trace + evaluator outputs and determines root cause of failure
- **Strategy portfolio**: selects from instruction_poison, skill_injection, workspace_contamination, multi_surface_sync, ambiguity_exploit
- **Kind-based dynamic guidance**: vector guidance auto-derived from manifest, no hardcoded vector names
- **Feedback iteration**: maximum 5 iterations where attacker adapts based on prior results
- **Configuration injection**: rewrites agent settings (model, permissions, temperature, endpoints)
- **Memory injection**: plants fake conversation history, auto-memory learnings, pre-approved task lists

### Running Batch Attacks

```bash
# First 10 tasks, 4 parallel workers, Claude Code
python scripts/run_all_tasks_with_timing.py \
  --tasks-root ../openagentsafety/tasks --limit 10 \
  --target-config configs/target.claude-code.yaml \
  --attacker-config configs/attacker-configs/universal/opencode-native-control/config-claude-code-native-control.yaml \
  --harness openagentsafety_utils/oas_harness \
  --service-config configs/services.openagentsafety.example.yaml \
  --tools-file openagentsafety_utils/user-tools.yaml \
  --eval-strategy both --max-iterations 5 --adaptive-iterations \
  --parallelism 4 --continue-on-error

# Hermes
python scripts/run_all_tasks_with_timing.py \
  --tasks-root ../openagentsafety/tasks --limit 10 \
  --target-config configs/target.hermes.yaml \
  --attacker-config configs/attacker-configs/universal/opencode-native-control/config-hermes-native-control.yaml \
  --harness openagentsafety_utils/oas_harness \
  --service-config configs/services.openagentsafety.example.yaml \
  --tools-file openagentsafety_utils/user-tools.yaml \
  --eval-strategy both --max-iterations 5 --adaptive-iterations \
  --parallelism 4 --continue-on-error

# Pi
python scripts/run_all_tasks_with_timing.py \
  --tasks-root ../openagentsafety/tasks --limit 10 \
  --target-config configs/target.pi.yaml \
  --attacker-config configs/attacker-configs/universal/opencode-native-control/config-pi-native-control.yaml \
  --harness openagentsafety_utils/oas_harness \
  --service-config configs/services.openagentsafety.example.yaml \
  --tools-file openagentsafety_utils/user-tools.yaml \
  --eval-strategy both --max-iterations 5 --adaptive-iterations \
  --parallelism 4 --continue-on-error

# Codex
python scripts/run_all_tasks_with_timing.py \
  --tasks-root ../openagentsafety/tasks --limit 10 \
  --target-config configs/target.codex.yaml \
  --attacker-config configs/attacker-configs/universal/opencode-native-control/config-codex-native-control.yaml \
  --harness openagentsafety_utils/oas_harness \
  --service-config configs/services.openagentsafety.example.yaml \
  --tools-file openagentsafety_utils/user-tools.yaml \
  --eval-strategy both --max-iterations 5 --adaptive-iterations \
  --parallelism 4 --continue-on-error
```

## Documentation

- [Architecture Overview](docs/architecture.md)
- [Components Reference](docs/components.md)
- [Configuration Guide](docs/configuration.md)
- [OpenAgentSafety Real-World Testing](docs/openagentsafety_real_world_testing.md)
- [Architecture Diagrams (historical)](docs/80_framework_architecture_diagrams.md)
- [Code Walkthrough (historical)](docs/code_walkthrough.md)
- [Testing Guide](docs/testing.md)

# OpenART Framework

A Docker-native framework for running attack/evaluation scenarios against tool-using agents in externally hosted enterprise environments.

## Core Concepts

- **Task environments** are Docker-defined
- **GitLab, ownCloud, and Plane** are external service integrations
- **Target, attack, and evaluator** are fully decoupled
- **Runners** adapt different agent frameworks behind one interface
- **Evaluators** consume traces and snapshots, not agent internals
- **Service configuration** is endpoint-driven, not self-hosted by OpenART

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
export no_proxy=10.0.0.0/8,100.96.0.0/12,.pjlab.org.cn
export NO_PROXY=10.0.0.0/8,100.96.0.0/12,.pjlab.org.cn

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

# Run a real OpenAgentSafety task through the dedicated attacker path.
# The attacker uses `openart/opencode:latest` and inherits
# `OPENAI_API_KEY`, `OPENAI_BASE_URL`, and `OPENAI_MODEL` from `.env`.
# It also writes to a separate native target-control bundle before the target starts.
# The attacker vectors are now explicit: workspace edits and each native control
# surface family can be enabled or disabled independently in the attacker config.
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

Attacker configs can now explicitly control which attack vectors the framework will honor.

Example:

```yaml
attacker:
  target_control_plane: true
  vector_permissions:
    - workspace_files
    - claude_md
    - opencode_skill
    - opencode_command
```

Meaning:

- `workspace_files`: attacker workspace edits are copied back into `workspace/shared`
- `claude_md`: attacker can materialize `CLAUDE.md`
- `opencode_skill`: attacker can materialize `.opencode/skills/**`
- `opencode_command`: attacker can materialize `.opencode/commands/**`

For an OpenCode target, the available vector names are:

- `workspace_files`
- `claude_md`
- `agents_md`
- `opencode_skill`
- `opencode_command`
- `claude_skill`

Notes:

- `agents_md` exists as an opt-in vector, but it is not enabled by default in the universal OpenCode attacker config.
- If `workspace_files` is omitted, the attacker may still write into its private `/workspace`, but OpenART will ignore those workspace edits when applying the attacker result.
- If a native control vector is omitted, the attacker may still write those files, but OpenART will ignore them during target-control materialization.

### Task-Aware Messaging Shaping

The universal OpenCode attacker now treats communication-heavy tasks specially.

- If the target task requires messaging or broadcasting and the runtime exposes no actionable communication path, the attacker prompt explicitly avoids inventing fake chat/email paths that mainly cause the target to waste the full timeout searching for missing tools.
- If the runtime does expose an actionable path, such as GitLab issue APIs or an actual chat/email integration in env, the attacker prompt allows a concrete communication-path attack that matches that channel.

### Attacker Feedback Loop

Attackers can now be configured to adapt between target iterations.

Example:

```yaml
attacker:
  target_control_plane: true
  feedback_loop: true
  vector_permissions:
    - workspace_files
    - claude_md
    - opencode_skill
```

When `feedback_loop: true` and `--max-iterations` is greater than `1`:

- the attacker still runs before the first target attempt
- if the evaluator does not return `pass`, OpenART reruns the attacker before the next target iteration
- the attacker gets a read-only feedback mount at `/workspace/.openart_feedback`

Useful attacker feedback paths inside the container:

- `/workspace/.openart_feedback/trace.jsonl`
- `/workspace/.openart_feedback/evaluator_inputs/`
- `/workspace/.openart_feedback/evaluator_outputs/`
- `/workspace/.openart_feedback/runner_outputs/target/`
- `/workspace/.openart_feedback/evaluation_iterations/`

The universal OpenCode attacker wrapper now surfaces these paths in its generated prompt and tells the attacker to inspect them on feedback iterations.

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

- OpenCode
- Claude Code
- iFlow
- Generic CLI

## Documentation

- [Architecture Overview](docs/architecture.md)
- [Components Reference](docs/components.md)
- [Configuration Guide](docs/configuration.md)
- [OpenAgentSafety Real-World Testing](docs/openagentsafety_real_world_testing.md)
- [Architecture Diagrams (historical)](docs/80_framework_architecture_diagrams.md)
- [Code Walkthrough (historical)](docs/code_walkthrough.md)
- [Testing Guide](docs/testing.md)

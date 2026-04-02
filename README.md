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
   - Includes Python 3.11, git, curl, jq, and common CLI tools
   - Build it: `docker build -t openart/task-base:latest -f images/Dockerfile.task-base .`
   - Build OpenCode runner: `docker build -t openart/opencode:latest -f images/Dockerfile.opencode .`
   - Build Claude Code runner: `docker build -t openart/claude-code:latest -f images/Dockerfile.claude-code .`

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

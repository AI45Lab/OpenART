# Quickstart

Commands below assume the current directory is `OpenART/`.

## Setup

OpenART is run from the source tree with the existing module entrypoints.

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
export PYTHONPATH="$PWD"
```

Docker must be available to the current user.

## Build Images

Build the base task image:

```bash
docker build -t openart/task-base:latest -f images/Dockerfile.task-base .
```

Build the target image required by your target config. The default config uses
OpenCode:

```bash
docker build -t openart/opencode:latest -f images/Dockerfile.opencode .
```

Other target configs under `configs/target-configs/` reference matching images
such as `openart/claude-code:latest`, `openart/codex:latest`,
`openart/qwen-code:latest`, and `openart/goose:latest`. Build only the images
needed for the config you run.

## Local Smoke Run

Use the local smoke task to verify the runtime without model credentials:

```bash
python -m framework.cli run \
  --task examples/tasks/local-smoke \
  --target-config configs/target-configs/target.local-smoke.yaml \
  --eval-strategy deterministic \
  --skip-attacker \
  --run-id local-smoke \
  --output-dir outputs/local-smoke
```

The deterministic evaluator passes when the target writes
`/workspace/openart_local_smoke_target.txt`.

## Model Environment

For model-backed targets, copy `.env.example` to `.env` and fill in the target,
judge, and attacker model values:

```bash
cp .env.example .env
```

The common OpenAI-compatible variables are:

```bash
TARGET_BASE_URL=https://api.example.com/v1
TARGET_MODEL=your-target-model
TARGET_API_KEY=your-target-key

JUDGE_BASE_URL=${TARGET_BASE_URL}
JUDGE_MODEL=${TARGET_MODEL}
JUDGE_API_KEY=${TARGET_API_KEY}

ATTACK_BASE_URL=${TARGET_BASE_URL}
ATTACK_MODEL=${TARGET_MODEL}
ATTACK_API_KEY=${TARGET_API_KEY}
```

Target configs map these variables into each target's native environment or
configuration files.

## Bundled High-Complexity Tasks

The release includes three generated task bundles:

| Task | Workflow nodes | Workspace files | Distinct tools |
|------|----------------|-----------------|----------------|
| `high-complexity-kb-health` | 100 | 67 | 29 |
| `high-complexity-kb-integration` | 100 | 109 | 26 |
| `high-complexity-release-sync` | 100 | 134 | 32 |

Each task contains `task.md`, `workspace/`, `tool_use_graph.json`,
`safety_contract.json`, `capabilities.generated.yaml`, and a deterministic
evaluator under `utils/`.

## Target-Only Run

Run one bundled high-complexity task with the default OpenCode target:

```bash
python -m framework.cli run \
  --task examples/tasks/high-complexity-kb-integration \
  --target-config configs/target-configs/target.yaml \
  --tool-store ../openart-tools \
  --eval-strategy deterministic \
  --skip-attacker \
  --run-id kb-integration-target-only \
  --output-dir outputs/kb-integration-target-only
```

`--tool-store` points to the sibling managed tool store. The task graph stages
only the tools referenced by `tool_use_graph.json`.

## Attacker-Capable Run

Add the default OpenCode-compatible attacker:

```bash
python -m framework.cli run \
  --task examples/tasks/high-complexity-kb-integration \
  --target-config configs/target-configs/target.yaml \
  --attacker-config configs/attacker-configs/universal/opencode-native-control/config.yaml \
  --tool-store ../openart-tools \
  --eval-strategy both \
  --max-iterations 2 \
  --run-id kb-integration-attacked \
  --output-dir outputs/kb-integration-attacked
```

Graph-RL-control uses the same runtime command with
`configs/attacker-configs/graph-rl-control/config.yaml`.

## Common Runtime Options

| Option | Meaning |
|--------|---------|
| `--task` | Task directory with `task.md` |
| `--target-config` | Target runner, model delivery, and native surface config |
| `--attacker-config` | Optional attacker config overlay |
| `--output-dir` | Local output root |
| `--run-id` | Optional stable run id |
| `--eval-strategy` | `auto`, `deterministic`, `llm`, or `both` |
| `--tool-store` | Managed OpenART tool store, usually `../openart-tools` |
| `--skip-attacker` | Ignore attacker config and run target-only |
| `--max-iterations` | Maximum target attempts |

Each run writes under `<output-dir>/<run-id>/`. Important artifacts include
`result.json`, `trace.jsonl`, `timing.json`, `workspace/shared/`,
`runner_outputs/target/`, `evaluator_outputs/`, and
`attacker_outputs/<name>/` when an attacker is enabled.

See [09_evaluation_and_outputs.md](09_evaluation_and_outputs.md) for artifact
details.

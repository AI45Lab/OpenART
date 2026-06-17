# Quickstart

This guide covers the shortest path from a checkout to a target-only run and an
attacker-capable run.

Commands below assume the current directory is `OpenART/`.

## Prerequisites

- Python 3.10 or newer
- Docker daemon available to the current user
- Target model endpoint credentials
- Optional external service credentials when service-backed managed tools need
  GitLab, ownCloud, Plane, or similar endpoints

Install the package:

```bash
pip install -e .
```

## Build Images

Build the task base image:

```bash
docker build -t openart/task-base:latest -f images/Dockerfile.task-base .
```

Build at least one target/attacker image. The default OpenCode target and the
universal attacker both use `openart/opencode:latest`:

```bash
docker build -t openart/opencode:latest -f images/Dockerfile.opencode .
```

For Claude Code target runs:

```bash
docker build -t openart/claude-code:latest -f images/Dockerfile.claude-code .
```

Other target configs reference these images:

| Target config | Image |
|---------------|-------|
| `configs/target-configs/target.codex.yaml` | `openart/codex:latest` |
| `configs/target-configs/target.gemini.yaml` | `openart/gemini:latest` |
| `configs/target-configs/target.hermes.yaml` | `openart/hermes:latest` |
| `configs/target-configs/target.nanobot.yaml` | `openart/nanobot:latest` |
| `configs/target-configs/target.pi.yaml` | `openart/pi:latest` |

Build only the images needed for the target config you will run.

## Configure Model Environment

The common OpenAI-compatible environment is:

```bash
export TARGET_BASE_URL="http://your-endpoint/v1"
export TARGET_MODEL="your-model"
export TARGET_API_KEY="your-key"

export JUDGE_BASE_URL="$TARGET_BASE_URL"
export JUDGE_MODEL="$TARGET_MODEL"
export JUDGE_API_KEY="$TARGET_API_KEY"
```

The target config maps these variables into the target's native environment or
config files through `model_integration`.

For OpenAgentSafety-style deterministic evaluators, provide the evaluator
harness so imports like `config`, `common`, and `scoring` resolve:

```bash
export OPENART_EVAL_HARNESS="$PWD/openagentsafety_utils/oas_harness"
```

or pass `--evaluator-harness openagentsafety_utils/oas_harness` on the run
command.

For attacker LLM calls used by the OpenCode-based attacker scripts:

```bash
export OPENAI_BASE_URL="$TARGET_BASE_URL"
export OPENAI_MODEL="$TARGET_MODEL"
export OPENAI_API_KEY="$TARGET_API_KEY"
```

## Target-Only Run

Run an OpenAgentSafety task with the default target config:

```bash
python -m framework.cli run \
  --task ../openagentsafety/tasks/safety-onboarding-notes \
  --target-config configs/target-configs/target.yaml \
  --output-dir outputs/target-only-smoke
```

The default `configs/target-configs/target.yaml` runs OpenCode through:

```yaml
target:
  framework: prompt_cli
  surface_family: opencode
  runner_image: openart/opencode:latest
  launch_cmd: opencode run
  model_integration:
    binding:
      provider_family: openai_compatible
      api_key: ${TARGET_API_KEY}
      base_url: ${TARGET_BASE_URL}
      model: ${TARGET_MODEL}
    delivery:
      type: hybrid
      env_names:
        api_key: OPENAI_API_KEY
        base_url: OPENAI_BASE_URL
        model: OPENAI_MODEL
  attack_surfaces:
    - vector: agents_md
      kind: instruction
      path_template: AGENTS.md
```

## Attacker-Capable Run

Run the same task with the universal attacker:

```bash
python -m framework.cli run \
  --task ../openagentsafety/tasks/safety-onboarding-notes \
  --target-config configs/target-configs/target.yaml \
  --attacker-config configs/attacker-configs/universal/opencode-native-control/config.yaml \
  --max-iterations 2 \
  --output-dir outputs/universal-attacker-smoke
```

This attacker preset:

- runs before the target
- uses `openart/opencode:latest`
- executes `/attacker_config/run_opencode_attacker.py`
- enables `target_control_plane`
- permits `workspace_files`, `claude_md`, `opencode_skill`,
  `opencode_command`, and `claude_skill`
- can rerun after evaluator feedback because `feedback_loop: true`

## Claude Code Target Run

Use the Claude Code target config and matching attacker preset:

```bash
python -m framework.cli run \
  --task ../openagentsafety/tasks/safety-onboarding-notes \
  --target-config configs/target-configs/target.claude-code.yaml \
  --attacker-config configs/attacker-configs/universal/opencode-native-control/config-claude-code-native-control.yaml \
  --max-iterations 2 \
  --output-dir outputs/claude-code-attacker-smoke
```

Claude Code still uses `framework: prompt_cli`. Its native surface behavior is
selected through `surface_family` and `attack_surfaces`, while model credentials
are delivered through `model_integration.delivery`:

```yaml
surface_family: claude_code
model_integration:
  delivery:
    type: env_only
    env_names:
      api_key: ANTHROPIC_AUTH_TOKEN
      base_url: ANTHROPIC_BASE_URL
      model: ANTHROPIC_MODEL
attack_surfaces:
  - vector: claude_md
    kind: instruction
    path_template: CLAUDE.md
pre_run_hook: repo:configs/target-hooks/claude-code-enforce-settings.sh
```

## Graph-RL-Control Run

Use the Graph-RL attacker when you want the attacker to sample and materialize a
structured multi-surface attack graph:

```bash
python -m framework.cli run \
  --task ../openagentsafety/tasks/safety-onboarding-notes \
  --target-config configs/target-configs/target.yaml \
  --attacker-config configs/attacker-configs/graph-rl-control/config.yaml \
  --max-iterations 2 \
  --attacker-timeout-seconds 3600 \
  --output-dir outputs/graph-rl-smoke
```

Graph-RL writes detailed artifacts such as `attack_graph.json`,
`attack_plan_ascii.txt`, strategy prompts, scratch outputs, and materialization
diagnostics.

## Common CLI Options

`python -m framework.cli` exposes only the `run` subcommand. Use direct Docker,
filesystem, or pytest commands for one-off build, cleanup, diagnostic, or
standalone evaluator work.

| Option | Meaning |
|--------|---------|
| `--task` | Required task directory |
| `--target-config` | Target runner/model/native-surface config |
| `--attacker-config` | Optional attacker config overlay |
| `--output-dir` | Output root directory |
| `--run-id` | Optional stable run id |
| `--eval-strategy` | `auto`, `deterministic`, `llm`, or `both` |
| `--evaluator-harness` | Evaluator compatibility harness directory, usually `openagentsafety_utils/oas_harness` |
| `--skip-attacker` | Ignore attacker even if configured |
| `--max-iterations` | Maximum target attempts |
| `--adaptive-iterations` | Retry only when evaluator says retry is useful |
| `--no-adaptive-iterations` | Disable adaptive retry |
| `--target-timeout-seconds` | Minimum target run timeout |
| `--attacker-timeout-seconds` | Minimum attacker command timeout |
| `--tool-store` | Managed OpenART tool store path; with `tool_use_graph.json` stages referenced tools, otherwise stages all valid live tools |

`--runner-framework` is only for runner process family overrides such as
`prompt_cli`, `hermes`, `nanobot`, or `pi`. Do not use it to select OpenCode or
Claude Code native behavior. Use `--target-config` instead.

## Output Location

Each run writes under:

```text
<output-dir>/<run-id>/
```

Important subdirectories:

```text
workspace/shared/                 final target-visible workspace
workspace/attacker_outputs/       archived attacker live outputs
control/target/                   base/final/materialized target-native files
runner_outputs/target/            target stdout/stderr and parsed outputs
evaluator_inputs/                 snapshots passed to evaluator
evaluator_outputs/                evaluator artifacts
attacker_outputs/<name>/          attacker command/artifact capture
trace.jsonl                       run trace
timing.json                       timing events
result.json                       final result
```

See [09_evaluation_and_outputs.md](09_evaluation_and_outputs.md) for artifact
details.

## First Debug Checks

If a run fails, inspect:

```bash
find outputs -maxdepth 3 -name runtime.log -print
find outputs -maxdepth 4 -name status.json -print
find outputs -maxdepth 4 -name materialization.json -print
```

Then read [11_debugging_and_testing.md](11_debugging_and_testing.md).

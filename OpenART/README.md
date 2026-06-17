# OpenART Framework

OpenART is a Docker-native framework for running attack/evaluation scenarios
against tool-using target agents. The current runtime keeps target execution,
attacker execution, and evaluation decoupled: targets run through runner
adapters, attackers propose workspace or native-control changes, and evaluators
judge traces plus snapshots.

Canonical documentation is maintained under [`docs/`](docs/). Start with
[`docs/README.md`](docs/README.md) for the current design, implementation,
usage, compatibility, and debugging guides.

## Install

```bash
cd OpenART
pip install -e .
```

Requirements:

- Python 3.10+
- Docker daemon available to the user running OpenART
- Target and judge API credentials exported in the shell

## Configure Models

```bash
export TARGET_BASE_URL="http://your-endpoint/v1"
export TARGET_MODEL="your-target-model"
export TARGET_API_KEY="your-target-key"

export JUDGE_BASE_URL="$TARGET_BASE_URL"
export JUDGE_MODEL="$TARGET_MODEL"
export JUDGE_API_KEY="$TARGET_API_KEY"
```

Target model bindings are described in
[`docs/04_target_compatibility.md`](docs/04_target_compatibility.md).

## Build Images

Build the base task image and the target runner image you plan to use:

```bash
docker build -t openart/task-base:latest -f images/Dockerfile.task-base .
docker build -t openart/opencode:latest -f images/Dockerfile.opencode .
docker build -t openart/claude-code:latest -f images/Dockerfile.claude-code .
```

## Run

Run a task without an attacker:

```bash
python -m framework.cli run \
  --task ../openagentsafety/tasks/safety-onboarding-notes
```

Run with the default OpenCode-compatible attacker:

```bash
python -m framework.cli run \
  --task ../openagentsafety/tasks/safety-onboarding-notes \
  --attacker-config configs/attacker-configs/universal/opencode-native-control/config.yaml \
  --run-id demo-run \
  --output-dir outputs/demo \
  --harness openagentsafety_utils/oas_harness \
  --service-config configs/services.openagentsafety.example.yaml \
  --tool-store ../openart-tools \
  --eval-strategy both
```

Batch a selected task set:

```bash
python scripts/run_all_tasks_with_timing.py \
  --tasks-root ../openagentsafety/tasks \
  --task safety-onboarding-notes \
  --output-dir outputs/batch-timing \
  --harness openagentsafety_utils/oas_harness \
  --service-config configs/services.openagentsafety.example.yaml \
  --tool-store ../openart-tools \
  --attacker-config configs/attacker-configs/universal/opencode-native-control/config.yaml \
  --eval-strategy both
```

<a id="scenario-first-safe-world-planner"></a>

## Scenario-First Safe-World Planner

OpenART includes an OpenCode-only planner for generating safe-world
OpenART/OpenAgentSafety task bundles from short scenario descriptions. The
planner first builds a `scenario_model.json`, refreshes the tool pool from the
explicit managed tool store and optional registry, generates the full bundle, then runs
scenario and bundle validation with profile-aware repair attempts.

Full planner design, generated bundle contract, usage examples, extension
points, and debugging guidance are maintained in
[`docs/12_planner_design_implementation_usage.md`](docs/12_planner_design_implementation_usage.md).

Generate one task bundle:

```bash
export OPENART_PLANNER_API_KEY="your-planner-key"
export OPENART_PLANNER_BASE_URL="https://planner-endpoint.example/v1"
export OPENART_PLANNER_MODEL="planner-model"

python -m framework.planner.cli \
  --scenario-file configs/planner/scenarios/recruiting-interview-agenda.txt \
  --tool-store ../openart-tools \
  --tool-count 3 \
  --planner-max-repairs 2 \
  --complexity-profile stress \
  --task-id recruiting-interview-agenda \
  --output-dir outputs/recruiting-interview-agenda \
  --overwrite
```

Generated bundles contain `scenario_model.json`, `task.md`, `workspace/`,
`tool_pool.json`, `tool_use_graph.json`, `safety_contract.json`,
`capabilities.generated.yaml`, `planner_plan.json`, evaluator files, and
`checkpoints.md`. Planner prompts, run metadata, registry feedback, and
validation reports are written under `planner_artifacts/`.

<a id="registry-backed-tool-discovery"></a>

## Registry-Backed Tool Discovery

When planning with `--tool-store ../openart-tools`, the planner checks
`../openart-tools/.registry/openart_tool_registry.sqlite` before prompting. It
can materialize ready registry rows with embedded `raw.openart_tool` payloads
into normal `tool.<slug>.<hash>/` folders, then rebuilds `tool_pool.json` and
`capabilities.generated.yaml`.

Generated tasks should use only final tool names present in the refreshed
`tool_pool.json`; they should not call registry search, install, show, or
materialization helpers from `task.md`, `tool_use_graph.json`, workspace files,
or evaluator code. Manual tool-store details live in
[`../openart-tools/README.md`](../openart-tools/README.md).

## Active Attacker Presets

The universal OpenCode-native-control directory now keeps only the active
default preset, Claude Code native preset, and selected ablations:

| Config | Purpose |
|--------|---------|
| `configs/attacker-configs/universal/opencode-native-control/config.yaml` | Default OpenCode-compatible native-control attacker |
| `configs/attacker-configs/universal/opencode-native-control/config-claude-code-native-control.yaml` | Claude Code native-control attacker |
| `configs/attacker-configs/universal/opencode-native-control/config-first20-workspace-only.yaml` | Workspace-file-only ablation |
| `configs/attacker-configs/universal/opencode-native-control/config-first20-instructions-only.yaml` | Instruction-surface-only ablation |
| `configs/attacker-configs/universal/opencode-native-control/config-first20-skills-only.yaml` | Skill-surface-only ablation |

Graph-RL control is maintained separately under
`configs/attacker-configs/graph-rl-control/config.yaml`.

## Implementation Guides

- Runtime architecture: [`docs/02_runtime_architecture.md`](docs/02_runtime_architecture.md)
- Task and config model: [`docs/03_task_and_config_model.md`](docs/03_task_and_config_model.md)
- Target compatibility: [`docs/04_target_compatibility.md`](docs/04_target_compatibility.md)
- Attacker design: [`docs/05_attacker_design.md`](docs/05_attacker_design.md)
- Attack surfaces: [`docs/06_attack_surfaces.md`](docs/06_attack_surfaces.md)
- Capabilities, tools, and MCP: [`docs/07_capabilities_tools_mcp.md`](docs/07_capabilities_tools_mcp.md)
- Evaluation outputs: [`docs/09_evaluation_and_outputs.md`](docs/09_evaluation_and_outputs.md)
- Extension guide: [`docs/10_extension_guides.md`](docs/10_extension_guides.md)
- Debugging and testing: [`docs/11_debugging_and_testing.md`](docs/11_debugging_and_testing.md)
- Planner design and usage: [`docs/12_planner_design_implementation_usage.md`](docs/12_planner_design_implementation_usage.md)

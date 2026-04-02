# Attacker Execution Logic

## Goal

Replace the legacy attacker-as-runner flow with a dedicated attacker subsystem that:

- accepts both the target and attacker instructions
- reads from a canonical shared workspace snapshot
- writes into an attacker-specific output workspace
- replaces the shared workspace with the attacker output before the target runs
- exposes a separate target control bundle for native prompt/skill poisoning
- supports multiple attacker methods under a dedicated framework folder

## Runtime Model

The target and task container use one canonical shared workspace:

`OpenART/outputs/<run-id>/workspace/shared/`

Each attacker method gets its own runtime folder:

`OpenART/outputs/<run-id>/workspace/attackers/<attacker_name>/<phase>_<index>/`

The target control plane is versioned separately:

`OpenART/outputs/<run-id>/control/target/{base,final,attackers/...}`

OpenART also writes a target-derived control manifest into the base bundle:

`OpenART/outputs/<run-id>/control/target/base/.openart-target-control-manifest.json`

For `before_target` execution:

1. Initialize `shared/`
2. Let the task container seed `shared/`
3. Copy `shared/` into the attacker output folder
4. Build the target control bundle from seeded workspace files that match the target framework's native control surfaces
4. Run the attacker in its own container with:
   - `/input_workspace` -> read-only mount of `shared/`
   - `/workspace` -> writable mount of the attacker output folder
   - a writable target control mount inside `/workspace/.openart_target_control_output`
   - `/task` -> read-only task assets
5. If the attacker succeeds, fully replace the contents of `shared/` with the attacker output contents
6. Materialize the final attacker-modified target control bundle into `shared/`
7. Run the target against `shared/`

The framework owns both workspace replacement and target-control materialization. Attackers do not modify generated runner state directly.

## Attacker API

The framework exposes a dedicated attacker base class:

- `AttackerSpec`
- `AttackerContext`
- `AttackerResult`
- `AttackerBase`

The V1 attacker implementation is a generic command attacker driven by:

- `cmd`
- `args`
- `tools_manifest`

The attacker receives both instruction files by default:

- `target_instruction_file`
- `attacker_instruction_file`

The attacker also receives:

- `input_workspace_dir`
- `output_workspace_dir`
- `shared_workspace_dir`
- `input_target_control_dir`
- `output_target_control_dir`
- task and run metadata

The attacker discovers native prompt/skill surfaces from the target-derived control manifest rather than from hardcoded framework-specific paths in the attacker prompt.

## Placeholder Contract

The generic command attacker supports these placeholders in `args`:

- `{{target_instruction_file}}`
- `{{attacker_instruction_file}}`
- `{{shared_workspace_dir}}`
- `{{input_workspace_dir}}`
- `{{output_workspace_dir}}`
- `{{input_target_control_dir}}`
- `{{output_target_control_dir}}`
- `{{task_dir}}`
- `{{run_id}}`
- `{{attack_phase}}`

## Framework Layout

Attacker code lives in a dedicated folder so new methods can be added cleanly:

```text
OpenART/framework/attackers/
  __init__.py
  base.py
  models.py
  registry.py
  methods/
    __init__.py
    generic_cmd.py
```

## Migration Rules

- Remove the old `attack_runner` path completely
- Keep the target as a runner
- Treat the attacker as a dedicated containerized actor with its own contract
- Mount only `shared/` into the task container and target runner
- Use full shared workspace replacement on successful attacker completion

## Implemented Real-Task Run

OpenART now runs real OpenAgentSafety tasks from `task.md`, with a universal attacker config supplied by OpenART at:

- task: `openagentsafety/tasks/safety-onboarding-notes/task.md`
- attacker config: `OpenART/configs/attacker-configs/universal/opencode-native-control/config.yaml`

Run it with:

```bash
python -m framework.cli run \
  --task ../openagentsafety/tasks/safety-onboarding-notes \
  --attacker-config configs/attacker-configs/universal/opencode-native-control/config.yaml \
  --run-id safety-onboarding-notes-attacker-demo \
  --output-dir outputs/oas-attacker-demos \
  --harness /mnt/shared-storage-user/chenyunhao/CodeAgentSafety/OpenClaw-Docker/oas_harness \
  --service-config configs/services.openagentsafety.example.yaml \
  --tools-file openagentsafety_utils/user-tools.yaml \
  --eval-strategy both
```

The resulting run shows the new contract in action:

- canonical shared workspace: `OpenART/outputs/oas-attacker-demos/safety-onboarding-notes-attacker-demo/workspace/shared`
- attacker output workspace: `OpenART/outputs/oas-attacker-demos/safety-onboarding-notes-attacker-demo/workspace/attackers/workspace-prep-attacker/before_target_001`
- target control base bundle: `OpenART/outputs/oas-attacker-demos/safety-onboarding-notes-attacker-demo/control/target/base`
- target control final bundle: `OpenART/outputs/oas-attacker-demos/safety-onboarding-notes-attacker-demo/control/target/final`
- workspace flow metadata: `OpenART/outputs/oas-attacker-demos/safety-onboarding-notes-attacker-demo/task_container/workspace_flow.json`
- attacker result: `OpenART/outputs/oas-attacker-demos/safety-onboarding-notes-attacker-demo/attacker_outputs/workspace-prep-attacker/result.json`
- attacker LLM stdout: `OpenART/outputs/oas-attacker-demos/safety-onboarding-notes-attacker-demo/attacker_outputs/workspace-prep-attacker/stdout.txt`

In this task, the attacker is a universal `opencode`-based agent launched from `OpenART/configs/attacker-configs/universal/opencode-native-control/run_opencode_attacker.py`. It reads `OPENAI_API_KEY`, `OPENAI_BASE_URL`, and `OPENAI_MODEL` from the loaded `.env` values via `env_from`, so the attacker uses the same `deepseek-chat` endpoint family as the target. The attacker inspects the target-derived control manifest, chooses a native OpenCode control surface, writes it into the control bundle, and OpenART materializes that file into `workspace/shared` before the target starts. In the current sample run it chose `.opencode/skills/urgent-upload/SKILL.md`.

The writable skill path is not hardcoded by the framework. Instead, the target-side control provider emits the allowed native control surfaces into `.openart-target-control-manifest.json`, mounts that bundle into the attacker, and the attacker wrapper includes the manifest contents in the generated attacker prompt.

Expected `workspace_flow.json` highlights:

- `run_order = ["attack", "target"]`
- `attacker_output_replaces_shared_workspace = true`
- `attacker_output_replaces_target_control = true`
- `task_container_workspace_host_path` and `target_runner_workspace_host_path` both point at `workspace/shared`

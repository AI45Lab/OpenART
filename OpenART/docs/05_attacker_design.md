# Attacker Design

OpenART attacker compatibility is command based. The active implementation uses
`GenericCommandAttacker` for attacker scripts and presets.

```text
attacker config YAML
  |
  v
AttackerSpec
  |
  v
OrchestratorFactory._create_attacker()
  |
  v
GenericCommandAttacker.run()
  |
  v
orchestrator applies allowed outputs
```

## Main Types

| Type | Source | Meaning |
|------|--------|---------|
| `AttackerSpec` | `framework/attackers/models.py` | Static attacker config |
| `AttackerContext` | `framework/attackers/models.py` | Runtime paths and iteration values |
| `AttackerResult` | `framework/attackers/models.py` | Exit code and metadata |
| `AttackerBase` | `framework/attackers/base.py` | Container lifecycle, managed tool staging, and artifacts |
| `GenericCommandAttacker` | `framework/attackers/methods/generic_cmd.py` | Placeholder expansion and command execution |

There is no active attacker registry. The factory constructs
`GenericCommandAttacker` directly from `AttackerSpec`.

## AttackerSpec Properties

| Property | Meaning |
|----------|---------|
| `name` | Stable output and container identity |
| `phase` | `before_target` or `after_target` |
| `enabled` | Disable without removing config |
| `instruction` | Attacker instruction file |
| `image` | Attacker container image |
| `cmd` | Executable |
| `args` | Argument list with placeholders |
| `target_control_plane` | Mount target-native input/output dirs |
| `env` | Literal env values |
| `env_from` | Copy host env values |
| `tool_guide_markdown` | Managed tool guidance appended to synthesized instruction |
| `timeout_seconds` | Attacker command timeout |
| `feedback_loop` | Allow rerun after evaluator feedback |
| `vector_permissions` | Allowed committed vectors |
| `visibility_policy` | Hide attacker scratch from target visibility |
| `metadata` | Free-form metadata |

## Container Contract

The attacker container is started idle:

```text
container command: tail -f /dev/null
working dir:       /workspace
```

Then `GenericCommandAttacker` executes:

```text
/bin/bash -lc "<rendered attacker command>"
```

Mounted paths:

| Container path | Access | Meaning |
|----------------|--------|---------|
| `/task` | read-only | task bundle root |
| `/attacker_config` | read-only | attacker config directory |
| `/workspace` | read-write | attacker output scratch |
| `/workspace/.openart_input_workspace` | read-only | shared workspace snapshot |
| `/workspace/.openart_feedback` | read-only | evaluator feedback bundle |
| `/workspace/.openart_target_control_input` | read-only | target-native base |
| `/workspace/.openart_target_control_output` | read-write | target-native output scratch |

Target-native dirs are mounted only when `target_control_plane: true` and the
target config defines `attack_surfaces`.

## Placeholder Contract

`cmd` and `args` support these placeholders:

| Placeholder | Meaning |
|-------------|---------|
| `{{target_instruction_file}}` | Target instruction path |
| `{{attacker_instruction_file}}` | Attacker instruction path, possibly synthesized |
| `{{shared_workspace_dir}}` | Compatibility alias for input workspace |
| `{{input_workspace_dir}}` | Read-only workspace snapshot |
| `{{output_workspace_dir}}` | Read-write attacker scratch |
| `{{input_target_control_dir}}` | Read-only target-native base |
| `{{output_target_control_dir}}` | Read-write target-native scratch |
| `{{feedback_dir}}` | Feedback bundle |
| `{{trace_file}}` | Trace JSONL path |
| `{{evaluator_inputs_dir}}` | Evaluator inputs |
| `{{evaluator_outputs_dir}}` | Evaluator outputs |
| `{{target_runner_outputs_dir}}` | Target runner outputs |
| `{{evaluation_iterations_dir}}` | Per-iteration evaluator state |
| `{{attacker_history_dir}}` | Prior attacker outputs |
| `{{attack_iteration}}` | Current attacker iteration |
| `{{feedback_iteration}}` | Iteration that produced feedback |
| `{{task_dir}}` | `/task` |
| `{{run_id}}` | Current run id |
| `{{attack_phase}}` | Current phase |

## Output Contract

The attacker writes proposed changes into `/workspace`:

```text
/workspace
  |
  +-- normal files
  |     proposed workspace mutations
  |
  +-- .openart_target_control_output/
  |     proposed target-native mutations
  |
  +-- .openart_attacker_artifacts/
        framework-readable artifacts
```

The framework always captures:

- rendered command as `command.sh`
- stdout and stderr
- status
- workspace listings before/after run
- target-native listings when exposed
- plugin artifacts under `.openart_attacker_artifacts`

## Vector Permissions

`vector_permissions` controls what the framework commits.

```text
vector_permissions omitted
  |
  +-- workspace_files allowed
  +-- default target-native vectors allowed

vector_permissions present
  |
  +-- workspace_files allowed only if listed
  +-- target-native vectors allowed only if listed
```

`ControlPlaneManager` still filters against `attack_surfaces`. Listing an
unsupported vector does not create a target surface.

## Attacker/Target Interaction

The attacker and target interact indirectly:

```text
attacker output scratch
  |
  +-- workspace diff filter
  +-- target-native vector filter
  |
  v
target-visible workspace/native files
  |
  v
target run
  |
  v
evaluator feedback
  |
  v
optional next attacker iteration
```

There is no direct attacker-to-target chat channel.

## Feedback Loop

If `feedback_loop: true`, the same attacker can rerun after a failed target
attempt. The feedback bundle includes:

```text
trace.jsonl
evaluator_inputs/
evaluator_outputs/
runner_outputs/target/
evaluation_iterations/
attacker_feedback_guidance.json
attacker_outputs/<attacker-name>/
```

The retry run receives updated `attack_iteration` and `feedback_iteration`.

## Managed Tools

`AttackerBase.prepare()` stages:

- managed OpenART tool folders
- tool guide markdown

Managed tool state is exposed through:

```text
OPENART_TOOLS_FILE
OPENART_TOOL_STORE_DIR
OPENART_TOOL_FOLDERS_FILE
OPENART_TOOL_GUIDE_FILE
```

Executable tools are installed as PATH wrappers inside the attacker container.
Guide-only tools are copied into the staged tool store and described in the
guide markdown.

See [07_capabilities_tools_mcp.md](07_capabilities_tools_mcp.md).

## Adding An Attacker

Recommended layout:

```text
configs/attacker-configs/<family>/<name>/
  |
  +-- config.yaml
  +-- attacker.md
  +-- run_<name>.py
```

Implementation rules:

1. Use `GenericCommandAttacker` unless you need a new execution model.
2. Read input paths; write only output paths.
3. Use narrow `vector_permissions`.
4. Keep scratch files hidden with `visibility_policy` when needed.
5. Emit useful artifacts under `.openart_attacker_artifacts`.
6. Add script-level tests for generated files and validation artifacts.

## Current Preset Families

| Family | Main script | Notes |
|--------|-------------|-------|
| `universal/opencode-native-control` | `run_opencode_attacker.py` | LLM-driven universal control attacker, reused by many presets |
| `graph-rl-control` | `run_graph_rl_attacker.py` | Structured graph sampling and materialization attacker |
| `templates/opencode-feedback-template` | `run_template_attacker.py` | Template/example feedback attacker |

## Audit Points

- `GenericCommandAttacker` is currently hardcoded by the factory.
- `vector_permissions` defaults are permissive when omitted.
- `env` overrides `env_from`.
- Failed attacker exit codes stop the run before target execution.
- Workspace output can be archived even when not committed.

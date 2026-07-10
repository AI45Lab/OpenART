# Task and Config Model

This document defines the files that shape an OpenART run: task directories,
target configs, attacker configs, managed tools, evaluator choices, and run
outputs.

## Task Loading

OpenART accepts OpenAgentSafety-style task directories as the public task
format:

```text
task directory
  task.md
  optional workspace/
  optional utils/evaluator.py
  optional utils/dependencies.yml
  optional checkpoints.md
  optional Dockerfile
  optional tool_use_graph.json
```

`framework/tasks/loader.py` converts this directory into the internal
`TaskBundleSpec` runtime contract.

## Task Directory Layout

OpenART maps it as:

| OAS file | OpenART meaning |
|----------|-----------------|
| `task.md` | target instruction |
| `workspace/` | seed workspace, when present |
| `utils/evaluator.py` | deterministic evaluator, when present |
| `checkpoints.md` | LLM judge rubric, when present |
| `utils/dependencies.yml` | legacy dependency and concurrency hints; not runtime-managed |
| `Dockerfile` | optional task image build recipe |
| `tool_use_graph.json` | optional managed tool selection graph |

Attacker behavior is supplied through `--attacker-config` rather than editing
the task corpus. Target and tool-store choices are also runtime configuration,
not task schema.

## Target Config Shape

Target configs live under `OpenART/configs/target-configs/target*.yaml` and use this shape:

```yaml
target:
  framework: prompt_cli
  surface_family: opencode
  runner_image: openart/opencode:latest
  launch_cmd: opencode run
  config_overlay:
    prompt_transport: argv
    prompt_flag: ""
    output_event_name: opencode_output
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
      env:
        OPENCODE_DISABLE_AUTOUPDATE: "1"
      config_template:
        source: repo:configs/target-model-json/opencode.openai-compatible.json
        destination: XDG_CONFIG_HOME/opencode/opencode.json
        format: json
  attack_surfaces:
    - vector: agents_md
      kind: instruction
      path_template: AGENTS.md
```

Important fields:

| Field | Meaning |
|-------|---------|
| `framework` | Runner process family. Use `prompt_cli` for most CLI targets |
| `surface_family` | Native target surface label, such as `opencode` or `claude_code` |
| `runner_image` | Docker image for target runner |
| `network` | Optional Docker network mode |
| `launch_cmd` | Target CLI command before prompt injection |
| `pre_run_hook` | Optional hook staged into target workspace and run before target CLI |
| `config_overlay.prompt_transport` | `argv` or `stdin` |
| `config_overlay.prompt_flag` | Flag used before prompt, or empty for positional prompt |
| `config_overlay.output_event_name` | Trace event name for parsed output |
| `model_integration` | Model binding plus target-native env/config delivery |
| `attack_surfaces` | Source of truth for target-native files that can be materialized |
| managed tool runtime | Supplied by `--tool-store`, not direct target config |

## Current Target Configs

| Config | Runner framework | Surface family | Delivery |
|--------|------------------|----------------|----------|
| `target-configs/target.yaml` | `prompt_cli` | `opencode` | hybrid env + JSON template |
| `target-configs/target.claude-code.yaml` | `prompt_cli` | `claude_code` | env only |
| `target-configs/target.codex.yaml` | `prompt_cli` | `codex` | hybrid env + TOML template |
| `target-configs/target.gemini.yaml` | `prompt_cli` | `gemini` | env only |
| `target-configs/target.continue-cli.yaml` | `prompt_cli` | `continue_cli` | hybrid env + YAML template |
| `target-configs/target.reasonix.yaml` | `prompt_cli` | `reasonix` | env only |
| `target-configs/target.hermes.yaml` | `hermes` | `hermes` | hybrid env + YAML template |
| `target-configs/target.nanobot.yaml` | `nanobot` | `nanobot` | JSON template |
| `target-configs/target.pi.yaml` | `pi` | `pi` | hybrid env + JSON template |
| `target-configs/target.local-smoke.yaml` | `prompt_cli` | none | none |

Claude Code and OpenCode native behavior is selected by target config, not by a
dedicated runner class.

## Attacker Config Shape

Attacker configs are YAML files with an `attacker:` object:

```yaml
attacker:
  name: universal-control-attacker
  phase: before_target
  instruction: /attacker_config/attacker.md
  image: openart/opencode:latest
  cmd: python3
  target_control_plane: true
  feedback_loop: true
  vector_permissions:
    - workspace_files
    - claude_md
    - opencode_skill
  env_from:
    OPENAI_API_KEY: OPENAI_API_KEY
    OPENAI_BASE_URL: OPENAI_BASE_URL
    OPENAI_MODEL: OPENAI_MODEL
  args:
    - /attacker_config/run_opencode_attacker.py
    - --target-instruction
    - "{{target_instruction_file}}"
    - --input-workspace
    - "{{input_workspace_dir}}"
    - --output-workspace
    - "{{output_workspace_dir}}"
```

Important fields:

| Field | Meaning |
|-------|---------|
| `name` | Stable attacker name used in outputs |
| `phase` | `before_target` or `after_target` |
| `instruction` | Attacker instruction file |
| `image` | Attacker container image |
| `cmd` and `args` | Command executed by `GenericCommandAttacker` |
| `target_control_plane` | Whether target-native input/output dirs are mounted |
| `feedback_loop` | Whether attacker can rerun after evaluator feedback |
| `vector_permissions` | Exact allowlist of committed vectors |
| `visibility_policy` | Hide scratch files from target visibility |
| `env_from` | Copy host env values into attacker container |
| `env` | Literal env overrides |
| managed tool runtime | Supplied by `--tool-store`, not direct attacker config |

## Service-Backed Managed Tools

OpenART no longer manages external service lifecycles or endpoint snapshots.
Service-backed tools are still supported through the managed tool store.

Put credentials and endpoints in the host environment before the run:

```bash
export GITLAB_URL=http://gitlab.example
export GITLAB_TOKEN=...
export OWNCLOUD_URL=http://owncloud.example
export OWNCLOUD_USERNAME=...
export OWNCLOUD_PASSWORD=...
```

Managed tool metadata may declare canonical env keys and aliases. OpenART
copies only values present in the host environment into staged wrappers and
runtime containers. There are no service defaults or credentials objects.

## Evaluator Selection

Use:

```bash
--eval-strategy auto
--eval-strategy deterministic
--eval-strategy llm
--eval-strategy both
```

Behavior:

| Strategy | Meaning |
|----------|---------|
| `auto` | Use deterministic evaluator when available, otherwise LLM when rubric/env exists |
| `deterministic` | Use task deterministic evaluator only |
| `llm` | Use LLM judge only |
| `both` | Use composite evaluator |

Deterministic evaluators often depend on a shared harness directory. Use:

```bash
--evaluator-harness openagentsafety_utils/oas_harness
```

or:

```bash
export OPENART_EVAL_HARNESS=/absolute/path/to/oas_harness
```

OpenART mounts that directory read-only into the task container as `/harness`
and adds it to evaluator import resolution so `utils/evaluator.py` can import
shared modules such as `config`, `common`, and `scoring`.

This is evaluator compatibility plumbing only. It is separate from target model
delivery, target runtime hooks, and task schema. The older `--harness` spelling
is a deprecated compatibility alias; new scripts and docs should use
`--evaluator-harness`.

## Capability and Tool Store Config

Managed tool loading is the runtime tool-management path. If the task includes
`tool_use_graph.json`, the CLI loads only the referenced tool folders from
`--tool-store`. If the task has no graph, `--tool-store` stages all valid live
tools in the store.

```bash
python -m framework.cli run \
  --task <task> \
  --tool-store ../openart-tools
```

`tool_use_graph.json` is a selector, not only documentation. Any nested
`{"tool": "<tool-name>"}` reference is collected. Full-store fallback skips
quarantine folders named `.invalid.*`.

The selected tool folders are resolved into:

```text
OPENART_TOOLS_FILE
OPENART_TOOL_STORE_DIR
OPENART_TOOL_FOLDERS_FILE
OPENART_TOOL_GUIDE_FILE
```

See [07_capabilities_tools_mcp.md](07_capabilities_tools_mcp.md).

## Output Data Model

Each run writes:

```text
outputs/<run-id>/
  |
  +-- result.json
  +-- report.json, if requested
  +-- runtime.log
  +-- trace.jsonl
  +-- timing.json
  +-- workspace/
  +-- control/
  +-- runner_outputs/
  +-- evaluator_inputs/
  +-- evaluator_outputs/
  +-- attacker_outputs/
```

The output model is described in
[09_evaluation_and_outputs.md](09_evaluation_and_outputs.md).

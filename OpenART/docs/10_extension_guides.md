# Extension Guides

This document gives implementation playbooks for extending OpenART. Prefer
small config-driven extensions before adding new Python classes.

## Add A Target

Use `PromptCLIRunner` unless the target cannot accept a prompt through argv or
stdin.

Steps:

1. Create `configs/target-configs/target.<name>.yaml`.
2. Set `target.framework: prompt_cli`.
3. Set `runner_image`, `launch_cmd`, and optional `network`.
4. Configure prompt delivery:

```yaml
config_overlay:
  prompt_transport: argv
  prompt_flag: -p
  output_event_name: <name>_output
```

5. Add `target.surface_family` when the target has native surface files.
6. Add `model_integration.binding` and env/config delivery under
   `model_integration.delivery`.
7. Add `attack_surfaces` for files the target actually trusts.
8. Add `target_surface_mount_mode: mounted` only when native files need overlay
   materialization rather than normal workspace placement.
9. Add `pre_run_hook` only for last-mile target runtime setup that cannot be
   represented as model delivery or a static config template.
10. Add or update tests for model delivery and runner command rendering.

Only add a runner class if:

- prompt cannot be delivered through argv/stdin
- output parsing needs a protocol instead of stdout/stderr
- lifecycle is not command based

## Add Model Delivery

Prefer target YAML plus templates over Python changes.

Minimum behavior:

- declare `model_integration.binding`
- choose `env_only`, `config_template`, or `hybrid`
- map common target-native env vars with `delivery.env_names`
- add explicit `delivery.env` entries for duplicate or special env vars
- add a config template source when needed
- add tests in `tests/unit/test_target_adapters.py`

Model delivery should be usable from target YAML:

```yaml
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
```

## Add A Runtime Setup Hook

Prefer static config templates before adding a hook. Use a hook only when a
target CLI requires executable setup immediately before launch, such as merging
runtime settings into an existing HOME config file.

Hook config:

```yaml
target:
  pre_run_hook: repo:configs/target-hooks/<name>.sh
```

Rules:

- keep hook scripts small and target-specific
- use `repo:`, `target:`, or `abs:` source prefixes
- do not put secrets in hook files
- do not use hooks for model env/config delivery
- do not use hooks to expose attacker-controlled target-native surfaces
- add a runner/factory test showing the hook is staged and executed for the
  prompt transport used by the target

## Add A Target-Native Surface

Prefer adding surfaces in the target config:

```yaml
attack_surfaces:
  - vector: my_agent_skill
    kind: skill
    path_template: .my-agent/skills/<skill-name>/SKILL.md
    injection_mode: replace
    description: MyAgent skill definition.
```

Rules:

- use a stable vector name
- choose the narrowest path template
- use `append` only for history/memory files
- document whether the path is workspace-relative or HOME-relative
- update attacker presets only when that vector should be active
- add target-surface tests for allowed and ignored paths

## Add An Attacker

Prefer a YAML preset plus script:

```text
configs/attacker-configs/<family>/<name>/
  |
  +-- config.yaml
  +-- attacker.md
  +-- run_<name>.py
```

Config checklist:

- `name`
- `phase`
- `instruction`
- `image`
- `cmd`
- `args` with placeholders
- `target_control_plane`
- `feedback_loop`
- explicit `vector_permissions`
- `env_from` for secrets
- `visibility_policy` for scratch outputs

Script checklist:

- read input workspace, feedback, and manifest paths
- write only output workspace and target-native paths
- emit useful JSON artifacts
- validate generated skill wrappers if creating target-visible skills
- avoid hardcoded target-family assumptions when a manifest can be read

## Add A Managed Tool

Add real runtime tools to the managed tool store, usually the sibling
`openart-tools/` directory.

Executable tool layout:

```text
openart-tools/<tool-name>/
  |
  +-- tool.yaml
  +-- TOOL.md or SKILL.md
  +-- scripts/<implementation>
```

Guide-only tool layout:

```text
openart-tools/<tool-name>/
  |
  +-- TOOL.md, tools.md, SKILL.md, or skills.md
```

Checklist:

- make `tool.yaml:name` exactly match the folder name
- keep implementation files under the tool folder and list them in
  `source_files`
- use relative script paths in `args`; avoid stale absolute paths
- write a guide that tells the agent when and how to use the tool
- declare `service`, `required_env`, `optional_env`, side effects, tags, and
  examples when applicable
- add or update task `tool_use_graph.json` when the task should stage only a
  subset of the store
- omit `tool_use_graph.json` when the task should stage all valid live tools in
  the store
- put quarantine folders under names containing `.invalid.` so full-store
  loading skips them
- verify with `tests/unit/test_tool_store.py` and
  `scripts/validate_realdata_tool_loading.py`

## Add A Task

Task layout:

```text
my-task/
  |
  +-- task.md
  +-- workspace/           optional seed workspace
  +-- utils/evaluator.py   optional deterministic evaluator
  +-- utils/dependencies.yml optional service dependency names
  +-- checkpoints.md       optional LLM judge rubric
  +-- tool_use_graph.json  optional managed tool selection
  +-- Dockerfile           optional task image
```

Minimum task:

```text
my-task/
  |
  +-- task.md
```

Add `utils/dependencies.yml` when the task uses shared external systems. Keep
target, attacker, and tool-store settings in runtime config.

## Add Evaluator Logic

For deterministic evaluation:

- put evaluator code under the task, usually `utils/evaluator.py`
- inspect task snapshots and evaluator inputs
- return or serialize an `EvaluatorResult`-compatible payload
- write unit tests for pass/fail cases

For LLM evaluation:

- write a concrete rubric
- keep task state excerpts compact
- configure `JUDGE_*` env vars
- use `--eval-strategy llm` or `both`

## Add Evaluator Harness Compatibility

Use an evaluator harness only when deterministic evaluator code depends on
shared Python modules or constants that are not shipped inside each task
directory. This is evaluator compatibility plumbing; it is separate from model
delivery, target runtime hooks, target-native surfaces, and attacker
managed tools.

Runtime behavior:

- pass the harness with `--evaluator-harness <dir>` or
  `OPENART_EVAL_HARNESS=<dir>`
- keep `--harness` only as a deprecated compatibility alias in old wrappers
- OpenART mounts the host harness read-only at `/harness` for task-container
  evaluation
- OpenART prepends the harness to evaluator import resolution so imports such
  as `config`, `common`, and `scoring` work
- host fallback evaluation uses the same harness path and temporary import
  setup

Harness checklist:

- keep evaluator-only helpers in the harness
- keep secrets in env, not in harness files
- do not use the harness for target model env/config delivery
- do not use the harness for target setup that belongs in `pre_run_hook`
- document required modules such as `config.py`, `common.py`, or `scoring.py`
- add CLI/factory/evaluator tests showing the harness is passed, mounted, and
  importable

## Add Tests

Recommended focused tests:

```bash
python3 -m pytest OpenART/tests/unit/test_target_adapters.py
python3 -m pytest OpenART/tests/unit/test_control_plane.py
python3 -m pytest OpenART/tests/unit/test_factory_runtime.py
python3 -m pytest OpenART/tests/unit/test_runners_runtime.py
python3 -m pytest OpenART/tests/unit/test_opencode_attacker_prompt.py
python3 -m pytest OpenART/tests/unit/test_graph_rl_attacker.py
python3 -m pytest OpenART/tests/unit/test_tool_store.py
```

For a new script, add script-level tests that run against temporary input/output
directories without Docker when possible.

## Compatibility Rules

- Keep target process compatibility separate from model and target-surface
  compatibility.
- Keep managed tool availability separate from attack-vector permission.
- Do not add broad defaults when a config can be explicit.
- Do not expose target model config as an attack surface unless the experiment
  intentionally evaluates config injection for that target.
- Preserve existing user changes in dirty worktrees.

# Target Compatibility

Target compatibility is the set of mechanisms that let OpenART run different
agent CLIs behind one framework contract.

OpenART separates target compatibility into three layers:

```text
process runner
  how to start the CLI and pass the task prompt

model delivery
  how credentials, base URLs, model names, and config files are delivered

target-native surfaces
  which native files the target trusts and how attacker edits are materialized
```

These layers are intentionally independent. OpenCode and Claude Code both use
`PromptCLIRunner`, but they declare different `surface_family`,
`model_integration.delivery`, and `attack_surfaces` values.

## Current Runner Model

The active runner implementation for prompt-first agent CLIs is
`PromptCLIRunner`.

Registered runner keys:

```text
hermes
nanobot
pi
prompt_cli
```

OpenCode, Claude Code, Codex, Gemini, and Cursor should be configured with:

```yaml
target:
  framework: prompt_cli
```

Their native behavior is selected through:

```yaml
target:
  surface_family: <target-family>
  model_integration:
    binding:
      provider_family: openai_compatible
      api_key: ${TARGET_API_KEY}
      base_url: ${TARGET_BASE_URL}
      model: ${TARGET_MODEL}
    delivery:
      type: hybrid
  attack_surfaces:
    - vector: <surface-name>
      kind: instruction
      path_template: <native-file>
```

Do not reintroduce dedicated native runner classes for OpenCode or Claude Code
unless the process model truly cannot be represented by `PromptCLIRunner`.

## PromptCLIRunner Contract

`PromptCLIRunner` takes:

- `launch_cmd`
- `config_overlay.prompt_transport`
- `config_overlay.prompt_flag`
- target instruction file

Then it renders a shell command.

Supported prompt transports:

| Transport | Meaning |
|-----------|---------|
| `argv` | Read the task prompt, pass it as a command-line argument |
| `stdin` | Read the task prompt, pipe it to the command stdin |

Examples:

```yaml
# OpenCode: prompt is final positional argv
launch_cmd: opencode run
config_overlay:
  prompt_transport: argv
  prompt_flag: ""

# Claude Code: prompt follows -p
launch_cmd: claude -p
config_overlay:
  prompt_transport: argv
  prompt_flag: -p

# Codex: prompt through stdin
launch_cmd: codex exec --skip-git-repo-check ...
config_overlay:
  prompt_transport: stdin
  prompt_flag: "-"
```

`output_event_name` controls the trace event name used for parsed target output.

## Runtime Setup Hooks

`pre_run_hook` is a target runtime setup escape hatch. It is for small
target-specific mutations that must happen inside the runner container after
workspace/config materialization and immediately before the target CLI starts.

Current example:

```yaml
target:
  framework: prompt_cli
  pre_run_hook: repo:configs/target-hooks/claude-code-enforce-settings.sh
```

Supported source prefixes:

| Prefix | Meaning |
|--------|---------|
| `repo:` | Path relative to the OpenART repo root |
| `target:` | Path relative to the target config file |
| `abs:` | Absolute host path |

OpenART stages hook files into the shared workspace:

```text
/workspace/.openart/runners/<role>/hooks/<hook-file>
```

and exposes the command through:

```text
OPENART_PRE_RUN_HOOK="bash /workspace/.openart/runners/<role>/hooks/<hook-file>"
```

For `PromptCLIRunner` argv transport, the rendered command is:

```text
<prompt prelude>; <pre-run hook>; exec <target cli> "$prompt"
```

The current Claude Code hook updates `$HOME/.claude/settings.json` to restore
baseline unattended permissions such as `Bash`, `Read`, and `Write`.

Use hooks narrowly:

- Do use them for last-mile runtime setup that a target CLI requires.
- Do not use them for model credentials; use `model_integration.delivery`.
- Do not use them to define target-trusted files; use `attack_surfaces`.
- Prefer declarative config templates when the target only needs a static file.
- Treat hooks as target-maintainer code, not attacker-controlled input.

Today hooks are exercised by the argv prompt path. Stdin-based targets should
not rely on hooks unless the runner path is extended and tested for that target.

## Model Delivery

Target model delivery is configured under:

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
    env:
      OPENCODE_DISABLE_AUTOUPDATE: "1"
```

Important concepts:

| Field | Meaning |
|-------|---------|
| `binding.provider_family` | Logical API family, such as `openai_compatible` |
| `binding.api_key` | Usually from `${TARGET_API_KEY}` |
| `binding.base_url` | Usually from `${TARGET_BASE_URL}` |
| `binding.model` | Usually from `${TARGET_MODEL}` |
| `delivery.type` | How env/config is delivered |
| `delivery.env_names` | Shorthand mapping from model fields to target-native env var names |
| `delivery.env` | Explicit env vars rendered after `env_names`, so it can add or override |
| `delivery.config_template` | Repo/target/absolute template source and destination |

Supported delivery types:

| Type | Meaning |
|------|---------|
| `env_only` | Only environment variables are rendered |
| `config_template` | Render a template file into the target runtime |
| `hybrid` | Render both env vars and a config template |

Supported template formats:

```text
json
yaml
toml
text
```

Templates can reference model values and target-native env var names:

```toml
env_key = "${env_name.api_key}"
base_url = "${model.base_url}"
model = "${model.name}"
```

Template source prefixes:

| Prefix | Meaning |
|--------|---------|
| `repo:` | Path relative to the OpenART repo root |
| `target:` | Path relative to the target config file |
| `abs:` | Absolute host path |

Template destinations are resolved inside the target runner container. Common
destination roots are:

```text
HOME/...
XDG_CONFIG_HOME/...
```

## Target Matrix

| Target config | Runner | Surface family | Delivery |
|---------------|--------|----------------|----------|
| `target-configs/target.yaml` | `prompt_cli` | `opencode` | hybrid env + `opencode.json` |
| `target-configs/target.claude-code.yaml` | `prompt_cli` | `claude_code` | env only + pre-run settings hook |
| `target-configs/target.codex.yaml` | `prompt_cli` | `codex` | hybrid env + TOML template |
| `target-configs/target.gemini.yaml` | `prompt_cli` | `gemini` | env only |
| `target-configs/target.cursor.yaml` | `prompt_cli` | `cursor` | env only |
| `target-configs/target.hermes.yaml` | `hermes` | `hermes` | hybrid env + YAML |
| `target-configs/target.nanobot.yaml` | `nanobot` | `nanobot` | JSON template |
| `target-configs/target.pi.yaml` | `pi` | `pi` | hybrid env + JSON template |
| `target-configs/target.local-smoke.yaml` | `prompt_cli` | none | stdin smoke command |

## OpenCode Example

Current OpenCode config:

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

The target runner starts OpenCode as a prompt CLI, while OpenCode-specific model
settings are rendered into its native config path.

## Claude Code Example

Current Claude Code config:

```yaml
target:
  framework: prompt_cli
  surface_family: claude_code
  runner_image: openart/claude-code:latest
  network: host
  launch_cmd: claude -p
  pre_run_hook: repo:configs/target-hooks/claude-code-enforce-settings.sh
  config_overlay:
    prompt_transport: argv
    prompt_flag: -p
    output_event_name: claude_code_output
  model_integration:
    binding:
      provider_family: anthropic_compatible
      api_key: ${TARGET_API_KEY}
      base_url: ${TARGET_BASE_URL}
      model: ${TARGET_MODEL}
    delivery:
      type: env_only
      env_names:
        api_key: ANTHROPIC_AUTH_TOKEN
        base_url: ANTHROPIC_BASE_URL
        model: ANTHROPIC_MODEL
      env:
        ANTHROPIC_DEFAULT_OPUS_MODEL: ${model.name}
        ANTHROPIC_DEFAULT_SONNET_MODEL: ${model.name}
        ANTHROPIC_DEFAULT_HAIKU_MODEL: ${model.name}
        CLAUDE_CODE_SUBAGENT_MODEL: ${model.name}
  attack_surfaces:
    - vector: claude_md
      kind: instruction
      path_template: CLAUDE.md
```

The pre-run hook enforces unattended settings after materialized HOME overlays
are merged, so target-native HOME files cannot silently undo required runtime
settings.

## Target-Native Surfaces

The target config defines `attack_surfaces`. Each surface has:

```yaml
- vector: claude_skill
  kind: skill
  path_template: .claude/skills/<skill-name>/SKILL.md
  injection_mode: replace
  description: Native Claude Code skill definition discovered from the workspace.
```

`ControlPlaneManager` is the internal materialization and filtering component.
It converts `path_template` into:

- source patterns to collect existing task files
- allowed patterns for base/final materialization
- attacker vector patterns for permission filtering
- manifest entries exposed to the attacker

The attacker can only make effective target-native changes when:

1. the target config exposes the vector
2. the attacker has `target_control_plane: true`
3. the attacker lists the vector in `vector_permissions`, or provider defaults apply

## Workspace vs Mounted Surface Mode

`target_surface_mount_mode` controls how final target-native files reach the
target:

| Mode | Meaning |
|------|---------|
| `workspace` | Materialize final control files into the shared workspace |
| `mounted` | Keep control files in an overlay area and mount/merge as needed |

Targets with HOME-relative control files, such as Codex config, often use
`mounted` mode to reduce leakage into the normal workspace tree.

## Adding A New Target

1. Prefer `framework: prompt_cli`.
2. Choose `launch_cmd`, `prompt_transport`, and `prompt_flag`.
3. Set `surface_family` when the target has native surface files.
4. Add `model_integration.binding` and `model_integration.delivery`.
5. Add `attack_surfaces` for native files the target actually trusts.
6. Use `target_surface_mount_mode: mounted` only when files should be overlaid
   into runner HOME or config locations instead of normal workspace paths.
7. Add a target config under `configs/target-configs/target.<name>.yaml`.
8. Add a unit test for command rendering/model delivery when behavior is new.

## Audit Points

- `framework` is a runner key, not a native target identity.
- `surface_family` is native-surface metadata, not a model-delivery selector.
- Model behavior lives in `model_integration.binding`, `delivery.env_names`,
  `delivery.env`, and optional config templates.
- OpenCode and Claude Code model config files are not attacker attack vectors in
  the current target configs.
- A vector listed by an attacker has no effect if `attack_surfaces` does not
  expose a matching surface.
- Rendered env and config artifacts may contain sensitive endpoint values;
  avoid committing rendered outputs.

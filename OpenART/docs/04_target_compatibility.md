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

OpenCode, Claude Code, Codex, Gemini, Continue CLI, and Reasonix should be configured with:

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
  pre_run_hook: repo:configs/target-hooks/llm-gateway-compat.py
```

The shell hook that previously enforced Claude Code permissions is now part of
`llm-gateway-compat.py`, which also handles the gateway compatibility proxy for
Claude Code and Codex.

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
OPENART_PRE_RUN_HOOK="python3 /workspace/.openart/runners/<role>/hooks/<hook-file>.py"
```

Hook files with a `.py` suffix run with `python3`; other extensions run with
`bash`.

The shared `llm-gateway-compat.py` hook is the current Claude Code/Codex
example. It starts a loopback proxy that injects
`use_chat_completions_api: true` into Messages/Responses requests, rewrites the
harness endpoint to the proxy, and keeps the proxy log under the run state
directory. Set `OPENART_LLM_GATEWAY_COMPAT` to `claude_code` or `codex` in the
target's `model_integration.delivery.env` to select the harness branch.

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
| `delivery.config_template` | One config file: template source, optional fallback source, destination, and format |
| `delivery.configs` | Ordered list of config files for targets that need separate model and MCP/settings files |

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

Use `fallback_source` when an optional config file is missing:

```yaml
config_template:
  source: repo:benchmarks/mcptox/mcp/opencode.json
  fallback_source: repo:configs/target-model-json/opencode.openai-compatible.json
  destination: XDG_CONFIG_HOME/opencode/opencode.json
  format: json
```

Template destinations are resolved inside the target runner container. Common
destination roots are:

```text
HOME/...
XDG_CONFIG_HOME/...
XDG_DATA_HOME/...
XDG_CACHE_HOME/...
WORKSPACE/...
RUNNER_STATE_DIR/...
```

`WORKSPACE/...` is `/workspace` inside the target. It is written during target
prepare, after control-plane materialization, so a benchmark-managed MCP file at
`WORKSPACE/...` wins over a task or attacker file at the same path. A `HOME/...`
destination is written before `materialized_home` is merged, so task or attacker
`HOME/...` files win there.

### Multiple config files

Targets that keep model settings and MCP settings in separate files can use
`delivery.configs`:

```yaml
delivery:
  type: hybrid
  configs:
    - id: model
      kind: model
      source: repo:configs/target-model-json/pi.openai-compatible.json
      destination: HOME/.pi/agent/models.json
      format: json
    - id: mcp
      kind: mcp
      source: repo:benchmarks/mcptox/mcp/pi.json
      destination: WORKSPACE/.pi/mcp.json
      format: json
```

The legacy `config_template` form is normalized to a one-element `configs`
list. Duplicate `id` or expanded `destination` values are rejected.

## Target Matrix

| Target config | Runner | Surface family | Delivery |
|---------------|--------|----------------|----------|
| `target-configs/target.yaml` | `prompt_cli` | `opencode` | hybrid env + JSON template |
| `target-configs/target.aider.yaml` | `prompt_cli` | `aider` | env only |
| `target-configs/target.claude-code.yaml` | `prompt_cli` | `claude_code` | env only + pre-run settings hook |
| `target-configs/target.codex.yaml` | `prompt_cli` | `codex` | hybrid env + TOML template |
| `target-configs/target.copilot-cli.yaml` | `prompt_cli` | `copilot_cli` | env only |
| `target-configs/target.gemini.yaml` | `prompt_cli` | `gemini` | hybrid env + JSON template |
| `target-configs/target.continue-cli.yaml` | `prompt_cli` | `continue_cli` | hybrid env + YAML template |
| `target-configs/target.reasonix.yaml` | `prompt_cli` | `reasonix` | env only |
| `target-configs/target.deepseek-tui.yaml` | `prompt_cli` | `deepseek_tui` | hybrid env + TOML template |
| `target-configs/target.goose.yaml` | `prompt_cli` | `goose` | hybrid env + YAML template |
| `target-configs/target.hermes.yaml` | `hermes` | `hermes` | hybrid env + YAML |
| `target-configs/target.kilo.yaml` | `prompt_cli` | `kilo` | hybrid env + JSON template |
| `target-configs/target.nanobot.yaml` | `nanobot` | `nanobot` | JSON template |
| `target-configs/target.oh-my-pi.yaml` | `prompt_cli` | `oh_my_pi` | hybrid env + YAML template |
| `target-configs/target.openclaw.yaml` | `prompt_cli` | `openclaw` | hybrid env + JSON template |
| `target-configs/target.pi.yaml` | `pi` | `pi` | hybrid env + JSON template |
| `target-configs/target.qwen-code.yaml` | `prompt_cli` | `qwen_code` | hybrid env + JSON template |
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
        source: repo:benchmarks/mcptox/mcp/opencode.json
        fallback_source: repo:configs/target-model-json/opencode.openai-compatible.json
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
  pre_run_hook: repo:configs/target-hooks/llm-gateway-compat.py
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

## Adding A New Target

1. Prefer `framework: prompt_cli`.
2. Choose `launch_cmd`, `prompt_transport`, and `prompt_flag`.
3. Set `surface_family` when the target has native surface files.
4. Add `model_integration.binding` and `model_integration.delivery`.
5. Add `attack_surfaces` for native files the target actually trusts.
6. Add a target config under `configs/target-configs/target.<name>.yaml`.
7. Add a unit test for command rendering/model delivery when behavior is new.

## Worked Example: OpenCode From Image To Attacked Run

This section walks one real harness — OpenCode — through every integration
step, from building the runner image to reading the evaluator verdict. It
complements the short [OpenCode Example](#opencode-example) snapshot above
and the [Target Matrix](#target-matrix); the same steps apply to any
config-only target in the
[integration matrix](13_target_agent_integration_matrix.md).

### Step 0 — Check the integration prerequisites

A CLI can be integrated config-only when it supports all three of:

1. **Non-interactive one-shot execution.** The task prompt arrives via argv
   or stdin and the process exits when the run completes. This is the
   [`PromptCLIRunner` contract](#promptclirunner-contract): `launch_cmd`,
   `prompt_transport`, and `prompt_flag` in the target config control it.
2. **An OpenAI-compatible model endpoint** (or another supported provider
   family) so credentials can be delivered per
   [Model Delivery](#model-delivery).
3. **Config read from a replaceable path.** OpenCode reads user-scope config
   from `$XDG_CONFIG_HOME/opencode/opencode.json`, so OpenART can stage a
   known-good profile there. See
   [Multi-file model delivery](03_task_and_config_model.md#multi-file-model-delivery)
   for how `config_template` + `destination` rendering works.

If any of the three is missing, follow [Adding A New Target](#adding-a-new-target)
to see which layer has to change instead.

### Step 1 — Build the runner image

```bash
docker build -t openart/opencode:latest -f images/Dockerfile.opencode .
```

`images/Dockerfile.opencode` is deliberately headless:

- pins the harness (`@opencode/cli@2.2.5`) so runs are reproducible;
- installs only document/data tooling a workspace task may need (poppler,
  imagemagick, tesseract, pandas, openpyxl, …) — no display, no TUI;
- creates a world-writable `/workspace` as the working directory, which the
  orchestrator bind-mounts as the shared workspace
  (see [Workspace Layers](02_runtime_architecture.md#workspace-layers)).

The image becomes the target container; the orchestrator starts it with
`tail -f /dev/null` and executes `launch_cmd` inside, as described in
[Container Roles](02_runtime_architecture.md#container-roles).

### Step 2 — Declare the target

`configs/target-configs/target.yaml` (abridged; full file in the repo):

```yaml
target:
  framework: prompt_cli          # PromptCLIRunner — one-shot prompt CLI
  surface_family: opencode       # selects OpenCode-native surface set
  runner_image: openart/opencode:latest
  launch_cmd: opencode run       # reads the prompt from stdin
  config_overlay:
    prompt_transport: stdin
  model_integration:
    binding:                     # resolved by the framework at load time
      provider_family: openai_compatible
      api_key: ${TARGET_API_KEY}
      base_url: ${TARGET_BASE_URL}
      model: ${TARGET_MODEL}
    delivery:                    # how it reaches the container
      type: hybrid               # env vars + rendered config file
      env_names: {api_key: OPENAI_API_KEY, base_url: OPENAI_BASE_URL, model: OPENAI_MODEL}
      env:
        OPENCODE_DISABLE_AUTOUPDATE: "1"
      config_template:
        source: repo:configs/target-model-json/opencode.openai-compatible.json
        destination: XDG_CONFIG_HOME/opencode/opencode.json
        format: json
  attack_surfaces:
  - vector: agents_md             # AGENTS.md
  - vector: claude_md             # CLAUDE.md (OpenCode also discovers it)
  - vector: opencode_skill        # .opencode/skills/<name>/SKILL.md
  - vector: opencode_command      # .opencode/commands/<name>.md
  - vector: conversation_history  # .opencode/sessions/*.jsonl (append)
  - vector: auto_memory           # .opencode/memory/*.md (append)
```

Field by field:

| Field | What it controls | Details |
| --- | --- | --- |
| `framework` / `launch_cmd` / `config_overlay` | how the CLI is started and fed the prompt | [PromptCLIRunner Contract](#promptclirunner-contract) |
| `surface_family` | which native files the target trusts | [Target-Native Surfaces](#target-native-surfaces) |
| `model_integration.binding` | endpoint/credentials resolution at load time | [Target Config Shape](03_task_and_config_model.md#target-config-shape) |
| `model_integration.delivery` | env vars + config file staging | [Model Delivery](#model-delivery) |
| `attack_surfaces` | the exact files the attacker may edit | [Surface Model](06_attack_surfaces.md#surface-model) |

`attack_surfaces` is the integration point for **custom configuration**: every
file the harness trusts at runtime is declared here. The attacker's edits are
materialized through the control plane and filtered by
[Vector Permission Rules](06_attack_surfaces.md#vector-permission-rules);
injection behavior per surface kind follows
[Injection Modes](06_attack_surfaces.md#injection-modes) (`replace` vs
`append` — note `conversation_history` and `auto_memory` append, so the
attacker fabricates prior turns rather than overwriting them).

### Step 3 — What happens at run time

For one `framework.cli run` invocation, in order (full pictures in
[Setup Sequence](02_runtime_architecture.md#setup-sequence) and
[Run Sequence](02_runtime_architecture.md#run-sequence)):

1. Task bundle and target config load; `${...}` references resolve from the
   environment ([Task Loading](03_task_and_config_model.md#task-loading)).
2. The factory creates the task container and the target runner container on
   a Docker network, staging the rendered model config at the profile's
   `destination` during
   [Target Runner Preparation](02_runtime_architecture.md#target-runner-preparation).
3. `pre_run_hook` (if any) runs inside the target container and must exit 0 —
   hooks are chained with `&&`, so a failed assertion stops the run
   ([Runtime Setup Hooks](#runtime-setup-hooks)).
4. The attacker (if configured) runs first: it edits only the declared
   surfaces inside its own container
   ([Attacker Container Contract](05_attacker_design.md#container-contract)).
5. The target executes `launch_cmd` with the prompt, bounded by its timeout.
6. Evaluators run over the final workspace and trace; results and
   `provenance.json` land in the run directory
   ([Run Directory Layout](09_evaluation_and_outputs.md#run-directory-layout)).

### Step 4 — Credentials and model endpoint

Keys never enter the repo or the image:

```bash
cp .env.example .env   # set TARGET_BASE_URL / TARGET_MODEL / TARGET_API_KEY
```

The template renders `{env:${env_name.api_key}}` into the JSON config; the
value is resolved only inside the container at run time. `provider_family`
picks the URL form (`.../v1` for OpenAI-compatible endpoints — see
[Model Delivery](#model-delivery) for the full binding table).

### Step 5 — Run

```bash
# target-only sanity run
python -m framework.cli run \
  --task examples/tasks/high-complexity-kb-integration \
  --target-config configs/target-configs/target.yaml \
  --tool-store ../openart-tools \
  --eval-strategy deterministic \
  --skip-attacker \
  --run-id opencode-target-only \
  --output-dir outputs/opencode-target-only

# same task under attack
python -m framework.cli run \
  --task examples/tasks/high-complexity-kb-integration \
  --target-config configs/target-configs/target.yaml \
  --attacker-config configs/attacker-configs/universal/opencode-native-control/config.yaml \
  --tool-store ../openart-tools \
  --eval-strategy both \
  --max-iterations 2 \
  --run-id opencode-attacked \
  --output-dir outputs/opencode-attacked
```

`--tool-store` selects managed tools for the task's `tool_use_graph.json`
([Runtime Staging](07_capabilities_tools_mcp.md#runtime-staging)). Artifacts
land under `outputs/<run-id>/`: target stdout/stderr, attacker workspace
diffs, `trace.jsonl` ([Trace](09_evaluation_and_outputs.md#trace)), evaluator
results, and `provenance.json`. A contaminated run (marker present before the
target ran) is invalidated by the
[Provenance Gate](11_debugging_and_testing.md#provenance-gate-and-invalid-runs).

### Step 6 — Custom tools over MCP (optional)

To test the harness with **custom tools** instead of its built-ins, add a
benchmark-level MCP profile. The CUA track (`benchmarks/cua-safety/`) is the
reference implementation; the pack contract is specified in
[Benchmark-Level MCP Config](07_capabilities_tools_mcp.md#benchmark-level-mcp-config)
and the surface rules in
[Target-Native MCP Surfaces](07_capabilities_tools_mcp.md#target-native-mcp-surfaces):

```text
benchmarks/cua-safety/
  mcp/opencode.json               # profile: mcp.servers.openart_cua, oauth:false,
                                  #   codemode:false, permissions deny-all + openart_cua_* allow
  scripts/resolve_target_config.py  # renders ${CUA_MCP_URL} into the profile
  scripts/check_target_config.py    # pre_run_hook re-asserts the rendered config, fail-closed
  targets.yaml                    # profile_mode: replace, destination XDG_CONFIG_HOME/opencode/opencode.json
```

Three rules that are easy to get wrong (each cost a debugging session; all
three fixes are in `git log` as `53691da1`, `2bc18f38`, `f00b3eb2`):

1. **Server name must match the permission prefix.** OpenCode names MCP tools
   `<server>_<tool>`, so server `openart_cua` yields tools covered by an
   `openart_cua_*` allow rule; a hyphenated name silently mismatches and the
   deny-all rule hides every tool.
2. **The bridge must answer `GET /mcp` with `405`**, not `404` — the
   Streamable HTTP handshake probes with GET first.
3. **In-network hosts must bypass the HTTP proxy.** The factory appends
   `openart-task-<run_id>` to `NO_PROXY` for runner containers; without it
   the MCP client routes to the corporate proxy and gets 502.

Project-level MCP configs are governed by
[MCP Provisioning Precedence](06_attack_surfaces.md#mcp-provisioning-precedence):
a task that ships its own `opencode.json` takes precedence over attacker
edits to the `opencode_mcp` vector.

### Step 7 — Choosing the attacker

The default above (`universal/opencode-native-control`) edits declared
surfaces before the target runs. For feedback-driven, graph-structured
attacks use the Graph-RL attacker instead
([High-Level Flow](08_graph_rl_attacker.md#high-level-flow)); its vector
permissions follow the same
[Vector Permissions](05_attacker_design.md#vector-permissions) model, so an
attacker may never touch a surface the target config did not declare.

### What changes versus a native deployment

| Aspect | Native use | OpenART test environment |
| --- | --- | --- |
| Execution | Interactive TUI session | Container, one-shot: prompt via stdin, exits on completion ([PromptCLIRunner Contract](#promptclirunner-contract)) |
| Config | User's own `~/.config/opencode/` | Whole-file profile staged at `XDG_CONFIG_HOME/opencode/opencode.json` (`profile_mode: replace`) |
| Model access | Local OAuth/login | OpenAI-compatible endpoint; key via env, rendered as `{env:...}`, never on disk ([Model Delivery](#model-delivery)) |
| Network | Open internet | Task+target share one Docker network with container-name DNS; attacker isolated; model traffic keeps the proxy, in-network hosts bypass it ([Network modes](14_task_bundle_runtime.md#network-modes)) |
| Tools | Full built-ins + user MCP servers | Exactly the declared set: built-ins denyable via `permissions`; custom tools via bridge with deny-all + prefix allowlist; `pre_run_hook` fails closed on surface drift ([Runtime Setup Hooks](#runtime-setup-hooks)) |
| Workspace | User home | Shared `/workspace` mount ([Workspace Layers](02_runtime_architecture.md#workspace-layers)); desktop tasks map it into the desktop (`Documents/openart_workspace → /workspace`, see [16_task_materialization.md](16_task_materialization.md)) |
| Lifecycle | Unlimited session | Bounded `timeout_seconds` per role, attacker iterations, evaluator deadlines ([Utility/Safety Split](09_evaluation_and_outputs.md#utilitysafety-split-evaluation)) |

### Where to go next

- Add another harness: [Adding A New Target](#adding-a-new-target) and the
  [integration matrix](13_target_agent_integration_matrix.md).
- Add custom tools: [Benchmark-Level MCP Config](07_capabilities_tools_mcp.md#benchmark-level-mcp-config).
- Add a safety channel to a materialized task:
  [Planner Safety-Only Mode](16_task_materialization.md#planner-safety-only-mode).
- Debug a run: [Target Debugging](11_debugging_and_testing.md#target-debugging)
  and [Target-Surface Debugging](11_debugging_and_testing.md#target-surface-debugging).

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

# Managed Tools

OpenART's tool runtime is the managed tool store. A run can stage executable
tools and guide-only tool folders from `openart-tools/` into the task, target,
attacker, and evaluator runtime environment.

## Store Layout

The usual store is a sibling directory:

```text
openart-tools/
```

An executable tool uses:

```text
openart-tools/<tool-name>/
  |
  +-- tool.yaml
  +-- TOOL.md or SKILL.md
  +-- scripts/...
```

A guide-only tool can provide only one of:

```text
TOOL.md
tools.md
SKILL.md
skills.md
```

`SKILL.md` and `skills.md` files must use YAML frontmatter with a `name` that
matches the folder and a non-empty `description`.

## Tool Metadata Rules

`tool.yaml` must be local to the tool folder. The strict validation rules are:

- `name` exactly matches the folder name
- executable tools list implementation files in `source_files`
- every `source_files` entry is relative to the tool folder
- command and argument paths point at staged relative files, not host absolute
  paths
- guide-only tools have a valid guide file

Quarantine folders can live under the store root when their names contain the
`.invalid.` marker. Full-store loading skips those folders. Other child
directories are treated as live tool folders and must validate.

## Selection

`--tool-store` has two modes:

```text
task has tool_use_graph.json
  -> stage only referenced tool names

task has no tool_use_graph.json
  -> stage all valid live tools in the store
```

The graph selector collects any nested object shaped like:

```json
{"tool": "<tool-name>"}
```

Example:

```json
{
  "workflow": {
    "nodes": [
      {"tool": "owncloud.upload_file"},
      {"tool": "gitlab.create_issue"}
    ]
  }
}
```

Then:

```bash
python -m framework.cli run \
  --task <task> \
  --tool-store ../openart-tools
```

stages only `owncloud.upload_file` and `gitlab.create_issue`.

## Runtime Staging

OpenART writes managed tool state into each prepared runtime that receives
tools:

```text
OPENART_TOOLS_FILE=<state>/tools.json
OPENART_TOOL_STORE_DIR=<state>/tools/store
OPENART_TOOL_FOLDERS_FILE=<state>/tools/folders.json
OPENART_TOOL_GUIDE_FILE=<state>/tools/guide.md
```

Executable source files are copied under:

```text
<state>/tools/src/<tool-name>/...
```

Managed tool folders and guides are copied under:

```text
<state>/tools/store/<tool-name>/...
```

Executable tools receive PATH wrappers so agents can call the tool by name.
Guide-only tools are available through the staged store and guide markdown.

Prepared copies are saved in run artifacts:

```text
runner_outputs/<role>/prepared/tools.json
runner_outputs/<role>/prepared/tool_folders.json
runner_outputs/<role>/prepared/tool_guide.md
attacker_outputs/<attacker>/prepared/tools.json
attacker_outputs/<attacker>/prepared/tool_folders.json
attacker_outputs/<attacker>/prepared/tool_guide.md
```

## Service-Backed Tools

OpenART does not start, seed, health-check, reset, or snapshot external
services. Service-backed tools receive credentials and endpoints only from the
host environment.

Tool metadata may declare:

```yaml
required_env:
  - name: GITLAB_URL
    aliases:
      - OPENART_GITLAB_URL
  - name: GITLAB_TOKEN
optional_env:
  - name: GITLAB_PROJECT
```

During CLI startup, OpenART checks the host environment for canonical keys and
aliases. If an alias is present, the value is copied to the canonical key for
the staged wrapper. Missing keys stay missing; there are no service defaults or
credential objects.

Wrapper env copying is conservative. A wrapper exports a declared key from the
host source only when that source exists, so resolved canonical values are not
overwritten by empty aliases.

## Benchmark-Level MCP Config

Harness-specific MCP config belongs to the benchmark pack, not to individual
tasks. MCPTox keeps a target manifest and one profile per harness:

```text
benchmarks/mcptox/
  targets.yaml
  mcp/
    opencode.json
    codex.toml
    gemini.json
    qwen.json
    continue.yaml
    goose.yaml
    hermes.yaml
    kilo.json
    nanobot.json
    openclaw.json
    claude.json
    reasonix.json
    copilot.json
    pi.json
    omp.json
    codewhale.json
  tasks/full/
    <case-id>/
      task.md
      checkpoints.md
      case.json
      workspace/mcp/server.py
      utils/evaluator.py
```

`targets.yaml` maps a harness name to a base target config and a profile:

```yaml
targets:
  codex:
    base: configs/target-configs/target.codex.yaml
    profile: benchmarks/mcptox/mcp/codex.toml
    profile_mode: replace
    destination: HOME/.codex/config.toml
    format: toml
```

`profile_mode` is:

```text
replace -> profile replaces the base model config template
add     -> profile is added as a second config file
wrapper -> no native MCP; use a tool-store wrapper
```

The runner resolves the pair into a temporary target config. For example:

```bash
bash benchmarks/mcptox/scripts/run_task.sh \
  --target codex \
  --task benchmarks/mcptox/tasks/full/filesystem-3
```

This keeps the task harness-agnostic. Tasks contain no harness config.

The importer materializes the upstream corpus into:

```text
benchmarks/mcptox/tasks/full/<case-id>/
  task.md
  checkpoints.md
  case.json
  workspace/mcp/server.py
  utils/evaluator.py
```

`case.json` lives at the task root, not in `/workspace`. The generated MCP
server reads it from `/task/case.json`; the evaluator reads the same file.

For targets with separate model and MCP files, the resolver emits
`delivery.configs` with a model entry and an MCP entry. The same `configs` form
can be used directly in a target config:

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

This is framework-managed provisioning, separate from attacker-controlled
`*_mcp` attack surfaces. Do not mix them in the same benchmark unless you are
explicitly testing precedence.

Templates are rendered before installation. Use `env_ref`/`env_name` placeholders
instead of embedding `${model.api_key}` directly, especially for files that land
under `WORKSPACE/` or match a configuration attack surface.

## Target-Native MCP Surfaces

MCP client configuration is separate from the managed tool store. It is a
target-native configuration surface:

```text
MCP server        external service, started by the user
MCP client config target-native file, filtered by the control plane
MCP tool wrapper  optional fallback for targets without native MCP
```

Each target config exposes its own MCP vector, path, config key, and injection
mode. The full list is in
[`13_target_agent_integration_matrix.md`](13_target_agent_integration_matrix.md#target-native-mcp-surfaces).

Examples:

```text
OpenCode      opencode_mcp    opencode.json / .opencode/opencode.json
Claude Code   claude_mcp      .mcp.json
Codex         codex_mcp       .codex/config.toml
Gemini        gemini_mcp      .gemini/settings.json
Qwen Code     qwen_mcp        .qwen/settings.json
Continue CLI  continue_mcp    .continue/mcpServers/<server-name>.yaml
Goose         goose_mcp       HOME/.config/goose/config.yaml
Hermes        hermes_mcp      HOME/.hermes/config.yaml
```

Important rules:

- The MCP server is not started by OpenART.
- The MCP config is not a `SKILL.md`.
- `append` is text append, not a structured JSON/YAML/TOML merge.
- `replace` on a shared config file replaces the whole file; prefer a dedicated
  project MCP file or a task that does not ship its own config.
- Aider has no native MCP client; use a service-backed CLI wrapper if needed.

## Tool Guides

Tool guides should tell the agent:

- when the tool is relevant
- what command name to call
- required inputs
- important side effects
- expected output shape
- recovery steps for common failures

Keep secrets out of guides. Put credentials and endpoints in host env vars.

## Debugging

Start with the prepared tool artifacts:

```text
runner_outputs/target/prepared/tools.json
runner_outputs/target/prepared/tool_folders.json
runner_outputs/target/prepared/tool_guide.md
attacker_outputs/<attacker>/prepared/tools.json
```

Common causes:

- `tool_use_graph.json` references a tool missing from the store
- a live folder's `tool.yaml:name` does not match the folder
- executable tool metadata omits `source_files`
- an implementation path is absolute or points outside the tool folder
- service-backed env vars are absent from the host environment
- a quarantine folder is not named with the `.invalid.` marker

Use focused tests while changing the store loader:

```bash
python3 -m pytest OpenART/tests/unit/test_tool_store.py
python3 -m pytest OpenART/tests/unit/test_realdata_tool_loading.py
```

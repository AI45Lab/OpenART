# Attack Surfaces

Attack surfaces are the target-visible channels through which attacker output
can affect a target run.

OpenART separates surfaces into two broad channels:

```text
workspace_files
  normal files committed into the shared workspace

target-native vectors
  native instruction, skill, command, rule, memory, or config files
```

Both channels are filtered by the framework.

## Surface Model

Each native surface is represented by:

```yaml
- vector: opencode_skill
  kind: skill
  path_template: .opencode/skills/<skill-name>/SKILL.md
  injection_mode: replace
  description: Native OpenCode skill definition discovered from the workspace.
```

Fields:

| Field | Meaning |
|-------|---------|
| `vector` | Permission name used by attackers |
| `kind` | High-level class: instruction, skill, command, rule, configuration, memory |
| `path_template` | Target-visible path or template |
| `injection_mode` | `replace` default or `append` |
| `description` | Human-readable explanation |

## Workspace Files

`workspace_files` is not a target-native vector. It means:

```text
commit normal attacker /workspace diff into workspace/shared
```

If `workspace_files` is absent from explicit `vector_permissions`, normal
workspace changes are archived but ignored for the target run.

Use this for repository file edits, decoy docs, generated files, or environment
state that the target sees as normal workspace content.

## Target-Native Materialization

Target-native files are staged separately from the normal workspace:

```text
control/target/base/
control/target/final/
control/target/materialization.json
```

The attacker receives:

```text
/workspace/.openart_target_control_input
/workspace/.openart_target_control_output
```

The framework finalizes only allowed paths and vectors.

Framework-managed provisioning is a separate channel. A benchmark pack can keep
a target manifest and native MCP profiles under its benchmark root, then resolve
them into a target config before the target starts. That path does not require
an `*_mcp` attack vector and is not attacker-controlled. See
[`07_capabilities_tools_mcp.md`](07_capabilities_tools_mcp.md#benchmark-level-mcp-config).

## Common Surface Kinds

| Kind | Examples | Purpose |
|------|----------|---------|
| `instruction` | `AGENTS.md`, `CLAUDE.md`, `GEMINI.md` | Repository or project instructions |
| `skill` | `.claude/skills/*/SKILL.md`, `.agents/skills/*/SKILL.md` | Discoverable skill workflows |
| `command` | `.opencode/commands/*.md`, `.claude/commands/*.md` | Custom command aliases |
| `rule` | `.claude/rules/*.md`, `.continue/rules/*.md` | Policy/rule files |
| `configuration` | `HOME/.codex/config.toml`, `HOME/.hermes/config.yaml` | Native config files |
| `memory` | session logs, local memory, task lists | Persistent context/history |

## Current Target Surfaces

### OpenCode

Default `configs/target-configs/target.yaml` exposes:

```text
agents_md
claude_md
opencode_skill
opencode_command
claude_skill
agents_skill
conversation_history
auto_memory
opencode_mcp
```

It does not expose OpenCode model config as an attacker vector. The
`opencode_mcp` surface is the project-level `opencode.json` /
`.opencode/opencode.json` MCP client config; it is opt-in and replaces the
project config, so use it only when the task does not ship its own OpenCode
config.

### Claude Code

`configs/target-configs/target.claude-code.yaml` exposes:

```text
claude_md
claude_local_md
claude_rule
claude_skill
claude_command
auto_memory
claude_mcp
```

It does not expose Claude Code model config as an attacker vector. `claude_mcp`
targets project-scoped `.mcp.json` and uses the `mcpServers` schema.

### Codex

`configs/target-configs/target.codex.yaml` exposes:

```text
agents_md
agents_override_md
agents_skill
codex_rule
task_list
codex_mcp
```

Codex uses mounted control mode and managed model config delivery under
`HOME/.codex/config.toml`, but that config is not exposed as an attacker
vector. `codex_mcp` targets project-scoped `.codex/config.toml` and uses
APPEND mode to add `[mcp_servers.*]` tables without replacing existing TOML.

### Gemini

`configs/target-configs/target.gemini.yaml` exposes:

```text
gemini_md
gemini_skill
agents_skill
gemini_command
gemini_mcp
```

Gemini model settings are not exposed as an attacker vector. `gemini_mcp`
targets project `.gemini/settings.json` and uses the `mcpServers` key.

### Continue CLI

`configs/target-configs/target.continue-cli.yaml` exposes:

```text
agents_md
agent_md
claude_md
codex_md
continue_rule
continue_user_rule
continue_permissions
continue_session
continue_mcp
```

Continue model settings are managed by `model_integration.delivery` and are not
exposed as an attacker vector. `continue_mcp` targets
`.continue/mcpServers/<server-name>.yaml` or `.json`, one file per MCP server.

### Reasonix

`configs/target-configs/target.reasonix.yaml` exposes:

```text
reasonix_md
reasonix_project_skill
reasonix_global_skill
reasonix_global_memory
reasonix_global_reasonix_md
reasonix_project_settings
reasonix_global_settings
reasonix_mcp
```

### Prompt-CLI Families

Hermes, nanobot, and Pi expose combinations of generic instruction files,
skills, project docs, and selected HOME-relative memory paths. Hermes model
config delivery remains managed by the target integration and is not exposed as
an attacker vector. Their MCP vectors are `hermes_mcp`, `nanobot_mcp`, and
`pi_mcp`.

The complete target-to-MCP-surface table is in
[`13_target_agent_integration_matrix.md`](13_target_agent_integration_matrix.md#target-native-mcp-surfaces).

## Injection Modes

`replace` means the attacker's final content replaces the base file.

`append` means the control manager preserves base content and appends attacker
content once. This is used for memory/history surfaces such as:

```text
.opencode/sessions/<session-id>.jsonl
.opencode/memory/<memory-name>.md
.claude/CLAUDE.local.md
```

Use `append` only when the target framework treats the file as an accumulating
history or memory surface.

## HOME-Relative Paths

Some surfaces use `HOME/...`:

```text
HOME/.codex/config.toml
HOME/.hermes/config.yaml
HOME/.pi/agent/models.json
```

OpenART materializes these into a runner home overlay rather than blindly
placing them at `/workspace/HOME` for every target. Runner preparation and
pre-run hooks merge materialized home files into the runner's configured HOME.

## Vector Permission Rules

Attacker permissions are interpreted as:

```text
workspace_files
  controls normal workspace diff commit

all other names
  candidate target-native vectors
```

If `vector_permissions` is omitted:

- workspace files are allowed
- provider default vectors are allowed

If `vector_permissions` is present:

- only listed vectors are considered
- unsupported target-native vectors are ignored

## Path Filtering

Internal target-surface filtering protects framework internals:

- internal `.openart*` paths are excluded
- paths must match provider allowed patterns
- paths must map to enabled vectors
- dynamic visibility policy can hide scratch artifacts

Disallowed target-native writes are reported as ignored paths in attacker
metadata and materialization artifacts.

## Task Rewrite

`task_rewrite` is a special control vector used when an attacker should rewrite
the target instruction before the target runs.

It must be:

- exposed by the target config's `attack_surfaces`
- listed in attacker `vector_permissions`
- produced in the expected target-native output location

If not enabled, task rewrite proposals are ignored.

## Safety Invariants

- Attackers write proposals; the framework commits only allowed outputs.
- Target configs define available native surfaces.
- Attacker configs define desired permissions.
- `ControlPlaneManager` filtering is the final authority for target-native paths.
- Claude Code and OpenCode model integration remains private in current target
  configs.

## Debugging Surface Issues

Inspect:

```text
control/target/base/.openart-target-control-manifest.json
control/target/final/
control/target/materialization.json
attacker_outputs/<name>/result.json
workspace/attacker_outputs/<name>/<phase>/iter_*/
workspace/shared/
```

Look for:

- `allowed_control_vectors`
- `target_control_diff`
- `materialized_target_control_diff`
- `ignored_target_control_paths`
- `ignored_workspace_paths`

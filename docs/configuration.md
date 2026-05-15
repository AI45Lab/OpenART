# Configuration Guide

This document describes the current config files consumed by the OpenART runtime.

## `task.yaml`

Task bundles use the OpenART format below:

```yaml
task_id: example-task
name: Example Task

env:
  dockerfile: Dockerfile
  context_dir: .

instructions:
  target: instructions/target.md

attacker:
  name: generic-attacker
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
    - --attacker-instruction
    - "{{attacker_instruction_file}}"
    - --input-workspace
    - "{{input_workspace_dir}}"
    - --output-workspace
    - "{{output_workspace_dir}}"
    - --input-target-control
    - "{{input_target_control_dir}}"
    - --output-target-control
    - "{{output_target_control_dir}}"

services:
  required:
    - gitlab
    - owncloud

seeds:
  path: seeds/

evaluation:
  deterministic: eval/deterministic.py
  llm_judge_rubric: eval/judge_rubric.yaml

runtime:
  timeout_seconds: 1800

concurrency:
  mode: local_only
  resource_keys: []
  max_parallel_for_task: 1
```

### Important fields

| Field | Description |
|-------|-------------|
| `env.dockerfile` | Optional task Dockerfile |
| `env.context_dir` | Build context relative to the task root |
| `instructions.target` | Required instruction file for the target runner |
| `attacker` | Optional dedicated attacker config with its own image, command, args, tools, and instruction |
| `attacker.target_control_plane` | When `true`, expose a separate native target-control bundle to the attacker |
| `attacker.feedback_loop` | When `true`, rerun the attacker between target iterations so it can adapt using evaluator/target feedback |
| `attacker.vector_permissions` | Optional explicit attacker vector allowlist. Controls whether workspace edits and specific native control surfaces are honored by the framework |
| `services.required` | External services the task expects |
| `seeds.path` | Optional directory copied into `/workspace` before the run |
| `evaluation.deterministic` | Optional Python evaluator module |
| `evaluation.llm_judge_rubric` | Optional rubric file for the LLM judge |
| `runtime.timeout_seconds` | Run timeout metadata passed into runner config |

### `attacker.vector_permissions`

If `vector_permissions` is omitted, OpenART uses legacy-compatible defaults for the current target framework plus `workspace_files`.

If `vector_permissions` is present, OpenART uses exactly that allowlist.

Common vector names:

| Vector | Meaning |
|--------|---------|
| `workspace_files` | Apply attacker workspace file edits back into the shared workspace |
| `claude_md` | Allow `CLAUDE.md` target-control edits |
| `agents_md` | Allow `AGENTS.md` target-control edits |
| `opencode_skill` | Allow `.opencode/skills/**` target-control edits |
| `opencode_command` | Allow `.opencode/commands/**` target-control edits |
| `claude_skill` | Allow `.claude/skills/**` target-control edits |
| `claude_local_md` | Allow `.claude/CLAUDE.md` target-control edits |
| `claude_rule` | Allow `.claude/rules/**` target-control edits |
| `claude_command` | Allow `.claude/commands/**` target-control edits |

Examples:

```yaml
attacker:
  target_control_plane: true
  vector_permissions:
    - workspace_files
    - claude_md
    - opencode_skill
```

```yaml
attacker:
  target_control_plane: true
  vector_permissions:
    - claude_md
```

In the second example, the attacker may still write workspace artifacts or skill files inside its private output folder, but OpenART will ignore those disabled vectors when applying attacker results.

Native control surfaces can also declare an `injection_mode` in target configs:

| Mode | Behavior |
|------|----------|
| `replace` | The attacker output replaces the allowed control file |
| `append` | The attacker output is appended to the existing base file, preserving prior content |
| `merge` | Currently handled like `append` for text control files |

Append/merge handling applies only to files whose vector is enabled by `attacker.vector_permissions`. Framework metadata files such as `.openart-target-control-manifest.json` are not reported as ignored attacker writes.

### `attacker.feedback_loop`

If `feedback_loop: true` and the run uses `--max-iterations > 1`, OpenART will:

1. Run the attacker before the first target attempt.
2. Run the target and evaluator.
3. If the result is not `pass`, rerun the attacker before the next target iteration.

The attacker receives a read-only feedback mount at `/workspace/.openart_feedback` with the latest run artifacts, including:

- `/workspace/.openart_feedback/trace.jsonl`
- `/workspace/.openart_feedback/evaluator_inputs/`
- `/workspace/.openart_feedback/evaluator_outputs/`
- `/workspace/.openart_feedback/runner_outputs/target/`
- `/workspace/.openart_feedback/evaluation_iterations/`

This allows the attacker to adapt based on:

- target stdout/stderr and workspace behavior
- evaluator prompts and evaluator outputs
- previous iteration snapshots and rationales

If `feedback_loop` is omitted or `false`, OpenART keeps the older behavior where the attacker only runs once before the target (or once after the target if `phase: after_target`).

## Runner Config Files

The CLI loads `configs/target.yaml` by default for the target runner. Attacker runtime config now lives inside the task's `attacker:` block.

For legacy `task.md`-only tasks such as OpenAgentSafety tasks, use `--attacker-config` to attach attacker config without creating a `task.yaml` inside the task folder.

Example:

```yaml
target:
  framework: opencode
  control_plane: opencode
  control_plane_mount_mode: workspace
  runner_image: openart/opencode:latest
  launch_cmd: opencode run
  model_integration:
    env:
      OPENAI_API_KEY: ${TARGET_API_KEY}
    config_json:
      source: repo:configs/target-model-json/opencode.openai-compatible.json
      destination: XDG_CONFIG_HOME/opencode/opencode.json
  tools:
    - bash
    - read
  mcp_servers:
    - filesystem
  skills:
    - coding
```

Supported top-level fields:

| Field | Description |
|-------|-------------|
| `framework` | `opencode`, `claude_code`, `iflow`, `prompt_cli`, or `generic_cli` |
| `control_plane` | Native control-plane family to model. Can be a built-in family name or an inline custom provider object |
| `control_plane_mount_mode` | `workspace` to merge native control files into `workspace/shared`, or `mounted` to keep them in `control/target/final` and mount them read-only into the target container |
| `runner_image` | Runner Docker image |
| `launch_cmd` | Shell command template |
| `model_integration.env` | Exact environment variables to inject into the target runner |
| `model_integration.config_json` | Optional user-managed JSON config source plus symbolic destination |
| `tools` | Tool allowlist or tool config objects |
| `mcp_servers` | MCP server definitions |
| `skills` | Skill names or skill config objects |
| `config_overlay` | Framework-specific config overlay |

Legacy top-level target model fields are no longer supported:

- `model`
- `base_url`
- `api_base_url`
- `api_key`
- `api_key_env`

Use `target.model_integration.env` and/or `target.model_integration.config_json` instead.

Do not commit concrete model tokens or service credentials in target configs. Use placeholders such as:

```yaml
target:
  model_integration:
    env:
      ANTHROPIC_AUTH_TOKEN: ${TARGET_API_KEY}
      ANTHROPIC_BASE_URL: ${TARGET_BASE_URL}
      ANTHROPIC_MODEL: ${TARGET_MODEL}
```

The unit test suite includes a config secret scan that fails on committed `sk-...` style API keys under `configs/`.

### `model_integration`

`target.model_integration` lets the user control native model wiring directly without asking OpenART to understand every framework's full config schema.

Supported sections:

```yaml
target:
  model_integration:
    env:
      ENV_NAME: value
    config_json:
      source: repo:configs/target-model-json/opencode.openai-compatible.json
      destination: XDG_CONFIG_HOME/opencode/opencode.json
```

`model_integration.env`:

- injects exactly the environment variables you specify
- resolves `${VAR}` placeholders before injection

`model_integration.config_json`:

- `source` must be a valid JSON file
- OpenART reads it on the host, resolves `${...}` placeholders inside it, stages it, mounts it into the runner container, and copies it to the requested destination
- when present, OpenART treats the framework config as user-managed and skips its own managed framework config generation for that runner

Supported `source` prefixes:

- `target:...` relative to the target config file directory
- `repo:...` relative to the OpenART repo root
- `abs:...` absolute host path

Supported symbolic destination roots:

- `HOME/`
- `XDG_CONFIG_HOME/`
- `XDG_DATA_HOME/`
- `XDG_CACHE_HOME/`
- `WORKSPACE/`
- `RUNNER_STATE_DIR/`

Typical destinations:

- Claude Code: `HOME/.claude/settings.json`
- OpenCode: `XDG_CONFIG_HOME/opencode/opencode.json`
- Gemini CLI: `HOME/.gemini/settings.json` or `WORKSPACE/.gemini/settings.json`
- iFlow: `HOME/.iflow/settings.json`

### `HOME/` control files and mount modes

Target attack surfaces may use `path_template: HOME/...` for native config files that must land in the target runner's home directory, for example:

```yaml
attack_surfaces:
  - vector: model_config
    kind: configuration
    path_template: HOME/.codex/config.toml
    injection_mode: replace
```

OpenART never writes these files to the host user's real home. Instead:

- In `control_plane_mount_mode: workspace`, `HOME/...` files are materialized under `/workspace/.openart/materialized_home/` and copied into the runner's configured `HOME` before each target run.
- In `control_plane_mount_mode: mounted`, `HOME/...` files are mounted at `/workspace/HOME/...` and copied into the runner's configured `HOME` before each target run.

This keeps target-native config poisoning scoped to the run while still making tools that read from `HOME` see the expected files.

For `claude_code`, build the local runner image first:

```bash
docker build -t openart/opencode:latest -f images/Dockerfile.opencode .
docker build -t openart/claude-code:latest -f images/Dockerfile.claude-code .
docker build -t openart/iflow:latest -f images/Dockerfile.iflow .
docker build -t openart/codex:latest -f images/Dockerfile.codex .
docker build -t openart/gemini:latest -f images/Dockerfile.gemini .
```

### Built-in control-plane families

OpenART currently ships these validated built-in control-plane families:

| Family | Official native surfaces modeled |
|--------|----------------------------------|
| `claude_code` | `CLAUDE.md`, `.claude/CLAUDE.md`, `.claude/rules/**`, `.claude/skills/**`, `.claude/commands/**` |
| `opencode` | `AGENTS.md`, `CLAUDE.md`, `.opencode/skills/**`, `.opencode/commands/**`, `.claude/skills/**`, `.agents/skills/**` |
| `gemini` | `GEMINI.md`, nested `GEMINI.md`, `.gemini/skills/**`, `.agents/skills/**`, `.gemini/commands/**/*.toml` |
| `codex` | `AGENTS.md`, `AGENTS.override.md`, `.agents/skills/**`, `.codex/rules/**/*.rules` |
| `cursor` | `AGENTS.md`, nested `AGENTS.md`, `.cursor/rules/**` |
| `prompt_cli` | Broad compatibility family for prompt-first CLIs when you do not yet have a target-specific provider |

Example target configs in this repo:

- `configs/target.yaml` for OpenCode
- `configs/target.claude-code.yaml` for Claude Code
- `configs/target.codex.yaml` for Codex
- `configs/target.gemini.yaml` for Gemini CLI
- `configs/target.iflow.yaml` for iFlow
- `configs/target.cursor.yaml` for Cursor-style experimental targets

### Physical isolation with `control_plane_mount_mode`

By default, OpenART uses `control_plane_mount_mode: workspace`:

- filtered native control files are copied back into `workspace/shared`
- the target sees one merged workspace tree

If you want physical separation between normal workspace files and native control files, use:

```yaml
target:
  framework: prompt_cli
  control_plane: codex
  control_plane_mount_mode: mounted
```

In `mounted` mode:

- attacker-produced native control files stay under `control/target/final/`
- OpenART mounts those files read-only into the target container at `/workspace/<original-path>`
- `workspace/shared` remains free of those native control artifacts

This gives you cleaner ablation experiments for:

- workspace-only attacks
- instruction-file-only attacks
- skills-only attacks
- rules / commands-only attacks

## `configs/services.yaml`

Services are external-only. OpenART does not read service images or lifecycle settings anymore, and service endpoints/credentials should come from environment variables rather than this file.

```yaml
env:
  SERVER_HOSTNAME: gateway.example
  OAS_EXTERNAL_MODE: real
```

### Supported sections

| Section | Description |
|---------|-------------|
| `env` | Extra environment variables exported into task and runner containers |

Use `.env` or exported environment variables for service endpoints and credentials:

- `GITLAB_BASEURL`
- `OWNCLOUD_URL`
- `PLANE_BASEURL`
- `GITLAB_ACCESS_TOKEN`
- `OWNCLOUD_USERNAME`
- `OWNCLOUD_PASSWORD`
- `PLANE_API_KEY`

## Evaluation Configuration

There is no standalone evaluator config file in the runtime path. Evaluation is configured through:

- `task.yaml` evaluator paths
- `JUDGE_API_KEY`, `JUDGE_BASE_URL`, and `JUDGE_MODEL`
- `--harness`, `--eval-strategy`, and environment variables loaded from `.env`

When `OPENART_EVAL_STRATEGY=both` or `auto` with both evaluators available, OpenART returns one merged result with raw child results preserved under `metadata.results`.

## Environment Variables

| Variable | Purpose |
|----------|---------|
| `ANTHROPIC_API_KEY` / `OPENAI_API_KEY` | Runner credentials fallback |
| `ANTHROPIC_BASE_URL` / `OPENAI_BASE_URL` | Runner API base URL fallback |
| `JUDGE_API_KEY` | LLM judge credential |
| `JUDGE_BASE_URL` | LLM judge endpoint |
| `JUDGE_MODEL` | LLM judge model |
| `OPENART_EVAL_HARNESS` | Optional OpenAgentSafety harness path |
| `OPENART_EVAL_ENV` | Comma-separated env overrides for deterministic eval |
| `OPENART_EVAL_STRATEGY` | `auto`, `deterministic`, `llm`, or `both` |

---

## Complete Example

For a `task.md`-only OpenAgentSafety task, keep the dataset folder clean and put the attacker files under `OpenART/configs/attacker-configs/...`:

```yaml
attacker:
  name: workspace-prep-attacker
  phase: before_target
  instruction: /attacker_config/attacker.md
  image: openart/opencode:latest
  cmd: python3
  target_control_plane: true
  vector_permissions:
    - workspace_files
    - claude_md
    - opencode_skill
    - opencode_command
    - claude_skill
  env_from:
    OPENAI_API_KEY: OPENAI_API_KEY
    OPENAI_BASE_URL: OPENAI_BASE_URL
    OPENAI_MODEL: OPENAI_MODEL
  args:
    - /attacker_config/run_opencode_attacker.py
    - --target-instruction
    - "{{target_instruction_file}}"
    - --attacker-instruction
    - "{{attacker_instruction_file}}"
    - --input-workspace
    - "{{input_workspace_dir}}"
    - --output-workspace
    - "{{output_workspace_dir}}"
    - --input-target-control
    - "{{input_target_control_dir}}"
    - --output-target-control
    - "{{output_target_control_dir}}"
```

Run the example with:

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

When `target_control_plane: true`, OpenART mounts a separate native target-control bundle into the attacker. Which native surfaces are actually honored is controlled by `attacker.vector_permissions`.

How the final target sees those files depends on the target config:

- `control_plane_mount_mode: workspace`: filtered native control files are materialized back into `workspace/shared`
- `control_plane_mount_mode: mounted`: filtered native control files stay under `control/target/final/` and are mounted read-only into the target container at their original paths

For example:

```yaml
target:
  framework: prompt_cli
  control_plane: gemini
  control_plane_mount_mode: mounted
```

OpenART also emits a target-derived manifest at `control/target/base/.openart-target-control-manifest.json`. Attackers can inspect that manifest to learn which native prompt, skill, rule, or command paths the current target framework supports.

The universal OpenAgentSafety attacker config lives at `OpenART/configs/attacker-configs/universal/opencode-native-control/config.yaml`.

## Universal Attacker Shaping

The universal OpenCode attacker wrapper also performs task-aware shaping for communication-heavy tasks.

- If the target task requires messaging or broadcasting and the current runtime does not expose an actionable communication path, the attacker prompt tells the model not to invent fake chat/email paths that mostly cause target timeouts.
- If the runtime does expose an actionable path, such as a writable GitLab issue path or a real chat/email integration in env, the attacker prompt allows the attacker to inject a concrete communication path that matches that channel.

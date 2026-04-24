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
  runner_image: openart/opencode:latest
  launch_cmd: opencode run
  model: anthropic/claude-sonnet-4
  base_url: ${TARGET_BASE_URL}
  api_key: ${TARGET_API_KEY}
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
| `framework` | `opencode`, `claude_code`, `iflow`, or `generic_cli` |
| `runner_image` | Runner Docker image |
| `launch_cmd` | Shell command template |
| `model` | Model name exposed to the runner |
| `base_url` | Optional API base URL |
| `api_key` / `api_key_env` | API credential source |
| `tools` | Tool allowlist or tool config objects |
| `mcp_servers` | MCP server definitions |
| `skills` | Skill names or skill config objects |
| `config_overlay` | Framework-specific config overlay |

For `claude_code`, build the local runner image first:

```bash
docker build -t openart/opencode:latest -f images/Dockerfile.opencode .
docker build -t openart/claude-code:latest -f images/Dockerfile.claude-code .
```

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

When `target_control_plane: true`, OpenART mounts a separate native target-control bundle into the attacker and materializes the final bundle back into `workspace/shared` before the target starts. Which native surfaces are actually honored is now controlled by `attacker.vector_permissions`.

OpenART also emits a target-derived manifest at `control/target/base/.openart-target-control-manifest.json`. Attackers can inspect that manifest to learn which native prompt, skill, rule, or command paths the current target framework supports.

The universal OpenAgentSafety attacker config lives at `OpenART/configs/attacker-configs/universal/opencode-native-control/config.yaml`.

## Universal Attacker Shaping

The universal OpenCode attacker wrapper also performs task-aware shaping for communication-heavy tasks.

- If the target task requires messaging or broadcasting and the current runtime does not expose an actionable communication path, the attacker prompt tells the model not to invent fake chat/email paths that mostly cause target timeouts.
- If the runtime does expose an actionable path, such as a writable GitLab issue path or a real chat/email integration in env, the attacker prompt allows the attacker to inject a concrete communication path that matches that channel.

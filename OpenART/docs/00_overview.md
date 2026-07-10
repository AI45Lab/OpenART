# OpenART Overview

OpenART is a Docker-native framework for running attack and evaluation
scenarios against tool-using code agents. It separates the target agent, the
attacker, managed tools, workspace state, and evaluator so each part can be
swapped or audited independently.

## What OpenART Runs

An OpenART run has five roles:

```text
task bundle
  |
  v
task container + shared workspace
  |
  +-- optional attacker container
  |
  +-- target runner container
  |
  +-- evaluator
  |
  v
run artifacts and report
```

The target is the agent being evaluated. The attacker is optional. The evaluator
decides whether the target behavior satisfies the scenario's safety or task
criteria.

## Core Mental Model

OpenART is easiest to understand as a controlled filesystem and process
orchestrator:

```text
seed files
  |
  v
shared workspace
  |
  +-- copied into attacker scratch
  |       |
  |       +-- attacker proposes workspace changes
  |       +-- attacker proposes target-native surface changes
  |
  +-- framework filters attacker output by vector_permissions
  |
  v
target-visible workspace and native surface files
  |
  v
target agent run
  |
  v
evaluator and feedback
```

Important rules:

- The attacker and target do not directly chat.
- The attacker writes proposals into scratch directories.
- The framework decides which proposals become target-visible.
- The evaluator reads traces and snapshots, not private model internals.

## Major Components

| Component | Main files | Responsibility |
|-----------|------------|----------------|
| CLI | `framework/cli/commands.py` | Parse run options, load task/configs, build managed tool manifests |
| Task loader | `framework/tasks/loader.py` | Convert OpenAgentSafety-style task directories into `TaskBundleSpec` |
| Factory | `framework/core/factory.py` | Create containers, runners, attackers, evaluators, and control manager |
| Orchestrator | `framework/core/orchestrator.py` | Execute setup, attacker phases, target attempts, evaluator, teardown |
| Workspace manager | `framework/core/workspace.py` | Manage seed/shared/attacker workspace copies, diffs, and snapshots |
| Target-surface materialization | `framework/core/control_plane.py` | Internally materialize and filter target-native surface files |
| Runners | `framework/components/runners.py` | Start target CLIs and convert outputs into trace events |
| Attackers | `framework/attackers/*` | Run attacker commands, staged managed tools, and artifacts |
| Evaluators | `framework/components/evaluators.py` | Deterministic, LLM, and composite evaluation |
| Managed tools | `framework/core/tool_store.py` | Load `openart-tools/`, validate tool folders, and resolve host env |

## Compatibility Layers

OpenART splits compatibility into separate layers:

```text
process runner
  how to start a target CLI and pass the prompt

target model delivery
  how to deliver API keys, base URLs, model names, and native model config

target-native surfaces
  which native files the target trusts, such as AGENTS.md or skills

attacker contract
  how an attacker receives input and proposes workspace/native-surface changes

evaluator contract
  how success/failure is judged from traces and snapshots
```

This split is why several target frameworks can share `PromptCLIRunner` while
still having framework-specific model delivery and native-surface behavior.

## Current Target Strategy

The current default target strategy is:

- Use `framework: prompt_cli` for prompt-first CLIs such as OpenCode, Claude
  Code, Codex, Gemini, Continue CLI, and Reasonix.
- Use `target.surface_family` to label target-native surfaces.
- Use `model_integration.binding` and `model_integration.delivery` to declare
  model config delivery.
- Use `attack_surfaces` as the source of truth for target-native files.
- Use `config_overlay` to describe prompt transport and output event naming.

Example:

```yaml
target:
  framework: prompt_cli
  surface_family: opencode
  runner_image: openart/opencode:latest
  launch_cmd: opencode run
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
  attack_surfaces:
    - vector: agents_md
      kind: instruction
      path_template: AGENTS.md
```

## Current Attacker Strategy

The current attacker strategy is command based:

```text
attacker config YAML
  |
  v
AttackerSpec
  |
  v
GenericCommandAttacker
  |
  v
python3 /attacker_config/<script>.py ...
```

OpenART does not need a new Python attacker class for every strategy. Most
attackers are implemented as a YAML preset plus a script mounted under
`/attacker_config`.

## What Is In Scope

OpenART documents and supports:

- target-only runs
- attacker-capable runs
- OpenAgentSafety-compatible task loading
- target model and native-surface compatibility
- workspace and target-native attack surfaces
- managed tool-store loading from `openart-tools/`
- deterministic, LLM, and composite evaluation
- Graph-RL-control attacker experiments

## What Is Out Of Scope

OpenART does not manage hosted enterprise service lifecycles. GitLab,
ownCloud, Plane, and similar systems are reached only by service-backed managed
tools that receive endpoints and credentials from host environment variables.

OpenART also does not make arbitrary attacker output target-visible. The
framework commits only the output channels allowed by `vector_permissions` and
the target config's `attack_surfaces`.

## Minimal End-to-End Flow

The public `framework.cli` entry point supports the `run` subcommand. Image
building, output cleanup, standalone evaluation, and diagnostics are handled by
the runtime flow or direct underlying tools rather than separate CLI wrappers.

```text
python -m framework.cli run --task <task-dir>
  |
  +-- load task bundle
  +-- load target config
  +-- stage managed tools, if configured
  +-- build orchestrator
  +-- prepare task workspace
  +-- prepare target-native surface base
  +-- run attacker, if configured
  +-- materialize allowed target-native surface files
  +-- run target
  +-- evaluate
  +-- write outputs
```

See [01_quickstart.md](01_quickstart.md) for commands and
[02_runtime_architecture.md](02_runtime_architecture.md) for the detailed
runtime sequence.

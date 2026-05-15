# Architecture Overview

## Runtime Shape

OpenART currently runs a single orchestrated flow:

`CLI -> OrchestratorFactory -> Orchestrator -> Task/Runner containers -> Trace -> Evaluator`

The service layer is external-only. OpenART no longer provisions or seeds GitLab, ownCloud, or Plane itself; it only injects configured endpoints, credentials, and environment values into task and runner containers.

## Main Modules

| Path | Responsibility |
|------|----------------|
| `framework/cli/commands.py` | CLI entrypoints and config loading |
| `framework/core/factory.py` | Builds the orchestrator graph from a task bundle |
| `framework/core/orchestrator.py` | Setup, run, teardown, and runner failure handling |
| `framework/core/runtime.py` | `launch_once()` lifecycle wrapper and report writing |
| `framework/components/containers.py` | Docker task and runner containers |
| `framework/components/runners.py` | Framework adapters for OpenCode, Claude Code, iFlow, and generic CLI |
| `framework/components/services.py` | External service descriptors and health snapshots |
| `framework/components/evaluators.py` | Deterministic, LLM judge, and composite evaluation |
| `framework/components/trace.py` | JSONL, memory, and SQLite trace sinks |
| `framework/tasks/loader.py` | Task bundle loading and OpenAgentSafety compatibility |

## Execution Flow

1. `run_main()` loads the task bundle plus target and service config, then resolves any task-local attacker config.
2. `OrchestratorFactory.build()` creates:
   - one `TaskContainer`
   - one target runner
   - an optional attacker container
   - one target control-plane manager for native prompt/skill files
   - one evaluator
   - one external `ServiceManager`
3. `launch_once()` runs setup, execution, and teardown inside a guarded lifecycle.
4. `Orchestrator.run()`:
   - optionally runs the attacker before or after the target
   - materializes attacker-modified native target control files into the shared workspace before target prepare
   - applies `HOME/...` native control files into the runner's configured home directory before each target attempt
   - runs the target against the canonical shared workspace
   - snapshots the workspace and services

The attacker implementation lives under `framework/attackers/`, while the target remains under `framework/components/runners.py`.
   - flushes the trace sink
   - evaluates the run
5. If a runner exits non-zero, OpenART returns a single failure result and skips evaluator execution.

## Workspace Model

The task directory is mounted read-only at `/task`, and the per-run workspace is mounted read-write at `/workspace`.

OpenART also maintains a per-run target control plane under `outputs/<run-id>/control/target/` so attackers can poison native framework files such as `AGENTS.md`, `CLAUDE.md`, `.opencode/skills/**`, or `.claude/skills/**` without touching generated runner state directly.

| Mount | Source | Purpose |
|-------|--------|---------|
| `/task` | task bundle root | instructions, evaluator code, static assets |
| `/workspace` | run output directory | files created or modified during execution |

If `task.yaml` defines `seeds.path`, that directory is copied into `/workspace` before the run starts.

## Target Control Plane

The target control plane has three host-side layers:

| Directory | Purpose |
|-----------|---------|
| `control/target/base/` | Native control files copied from the seeded workspace, plus the control manifest |
| `control/target/attackers/<name>/<phase>_001/` | Attacker-produced native control files |
| `control/target/final/` | Filtered final native control files after vector permissions and injection modes are applied |

Attackers can only affect enabled vectors. Disallowed files are ignored, while OpenART's own `.openart-*` metadata files are excluded from ignored-path reporting.

Control surfaces support three injection modes:

- `replace`: attacker output replaces the base file
- `append`: attacker output is appended to the base file
- `merge`: currently treated like `append` for text files

For target-native config paths that start with `HOME/`, OpenART routes files through an in-workspace home overlay rather than the host user's home:

- workspace materialization mode writes `/workspace/.openart/materialized_home/...`
- mounted mode exposes `/workspace/HOME/...`

The runner merges both locations into its runtime `HOME` before each target run. This is why `HOME/.codex/config.toml`, `HOME/.claude/settings.json`, or `HOME/.iflow/settings.json` can be tested safely without touching machine-level config.

## Evaluation Model

OpenART supports three modes:

- deterministic only
- LLM judge only
- composite evaluation using both

When both evaluators run, the returned `EvaluatorResult` is unified: the top-level score/decision is merged, and per-evaluator results are preserved under `metadata.results`.

## Services

Services are external-only. The framework uses configured endpoints such as `gitlab.web` or `owncloud.web` and exposes them to containers via environment variables like `GITLAB_BASEURL`, `OWNCLOUD_URL`, and `PLANE_BASEURL`.

Use `docs/components.md` for API-level details and `docs/configuration.md` for the current config format.

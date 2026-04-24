# Components Reference

## Containers

### `ContainerBase`

Shared Docker lifecycle API used by task and runner containers.

| Method | Purpose |
|--------|---------|
| `build()` | Build an image when `build_context` is set |
| `create()` | Create the Docker container |
| `start()` | Start the container |
| `stop()` | Stop the container |
| `remove()` | Remove the container |
| `exec()` | Execute a command inside the container |
| `logs()` | Read container logs |
| `snapshot()` | Read Docker inspect state |

### `TaskContainer`

Provides the runtime environment mounted at `/workspace` and read-only task assets at `/task`.

| Method | Purpose |
|--------|---------|
| `mount_workspace()` | Mount the per-run workspace |
| `mount_task_assets()` | Mount the task bundle |
| `prepare_task_env()` | Seed `/workspace` and run `/task/env/setup.sh` if present |
| `snapshot_workspace()` | Snapshot workspace files for evaluation |

### `RunnerContainer`

Long-lived helper container for runner-style actors such as the target agent.

| Method | Purpose |
|--------|---------|
| `write_text_file()` | Write generated config into the container |
| `read_text_file()` | Read a file from the container |
| `ensure_dir()` | Create runtime directories |
| `run_shell()` | Run a shell command |

## Services

### `ExternalService`

Represents an externally hosted dependency such as GitLab, ownCloud, or Plane. OpenART does not start or seed it; it only tracks endpoints, credentials, and health probes.

### `ServiceManager`

Holds a set of `ExternalService` instances and provides:

| Method | Purpose |
|--------|---------|
| `start_all()` | Apply endpoint overrides and invoke service hooks |
| `seed_all()` | No-op for built-in external services |
| `reset_all()` | No-op for built-in external services |
| `stop_all()` | Invoke service hooks in reverse order |
| `snapshot_all()` | Capture per-service health and endpoint state |
| `endpoint_map()` | Flatten endpoints into `service.endpoint -> url` |

## Runners

### `RunnerBase`

Base class for framework-specific runner adapters.

| Method | Purpose |
|--------|---------|
| `prepare()` | Build/start the runner container and install config |
| `run()` | Execute the rendered runner command |
| `stop()` | Stop the runner container |
| `render_command()` | Render the framework command template |
| `parse_output()` | Convert stdout/stderr into trace events |

### Built-in runners

| Class | Framework |
|-------|-----------|
| `OpenCodeRunner` | OpenCode |
| `ClaudeCodeRunner` | Claude Code |
| `IFlowRunner` | iFlow |
| `GenericCLIRunner` | Arbitrary CLI |

## Attackers

### `AttackerBase`

Base class for dedicated attacker containers. Attackers are separate from runners and receive both instruction files plus explicit input/output workspace paths. When `target_control_plane` is enabled, they also receive a separate input/output target-control bundle for native prompt and skill poisoning.

| Method | Purpose |
|--------|---------|
| `prepare()` | Build/start the attacker container and install tool wrappers |
| `run()` | Execute the attacker command against `/input_workspace`, `/workspace`, and optional target-control paths |
| `stop()` | Stop the attacker container |
| `remove()` | Remove the attacker container |

### Built-in attackers

| Class | Purpose |
|-------|---------|
| `GenericCommandAttacker` | Run any `cmd + args` attacker with placeholder expansion |

## Evaluators

### `DeterministicEvaluator`

Loads a Python rules module either on the host or inside the task container.

### `LLMJudgeEvaluator`

Sends the trace, rubric, and snapshots to an OpenAI-compatible `chat/completions` endpoint.

### `CompositeEvaluator`

Runs both evaluators and returns one merged `EvaluatorResult`.

- top-level `decision` and `score` are merged
- top-level `subscores` are namespaced per evaluator
- `metadata.results` contains the full deterministic and LLM judge child results together

## Trace

| Class | Storage |
|-------|---------|
| `JsonlTraceSink` | JSONL file |
| `MemoryTraceSink` | in-memory list |
| `SqliteTraceSink` | SQLite database |

`TraceCollector` is a convenience wrapper for emitting `TraceEvent` objects to any sink.

## Core Runtime

### `Orchestrator`

Coordinates service hooks, the task container, the target runner, the attacker container, the target control plane, snapshots, and evaluation.

Important behavior:

- attack execution is optional when a task has no attacker config or attacker instruction
- target control materialization happens before target prepare when the selected framework exposes native control surfaces
- non-zero target or attacker exit codes produce one unified failure result
- evaluator execution is skipped when a target runner or attacker fails

### `launch_once()`

Wraps setup, run, and teardown. Teardown is attempted even if setup raises partway through.
### ConcurrencyPolicy (`concurrency.py`)

Run scheduling decisions.

| Method | Purpose |
|--------|---------|
| `can_start()` | Check if run can start |
| `acquire_if_needed()` | Acquire resource locks |
| `release()` | Release locks |

**Modes:**
- `local_only`: No shared services, parallelism limited by local capacity
- `shared_service`: Uses shared remote services with resource locking
- `isolated_service`: Requires isolated service stack per run

### ResourceLockManager

In-memory resource locking.

| Method | Purpose |
|--------|---------|
| `acquire_many()` | Acquire multiple locks atomically |
| `release_many()` | Release specific locks |
| `release_all_for_run()` | Release all locks for a run |
| `is_free()` | Check if resource is available |
| `renew_all_for_run()` | Extend lease for long-running tasks |

---

## CLI Commands (`framework/cli/commands.py`)

| Command | Purpose |
|---------|---------|
| `run` | Execute evaluation run |
| `build` | Build task containers |
| `reset` | Reset services to clean state |
| `eval` | Evaluate existing results |
| `doctor` | Diagnose configuration issues |

### Usage

```bash
# Run evaluation
python -m framework.cli run --task tasks/example.yaml

# Build containers
python -m framework.cli build --task tasks/example.yaml

# Reset services
python -m framework.cli reset --services gitlab,owncloud

# Diagnose issues
python -m framework.cli doctor
```

# OpenART Framework Code Walkthrough

> Historical note: this walkthrough predates the external-only service refactor. Sections describing managed GitLab/ownCloud/Plane containers are no longer current. The attacker is now a dedicated subsystem under `framework/attackers/`, not an `attack_runner`. Use `docs/architecture.md`, `docs/components.md`, and `docs/attacker_execution_logic.md` for the current runtime.

This document explains the OpenART framework code structure by following the data flow through the full Orchestrator execution path.

---

## Table of Contents

1. [Execution Flow Overview](#execution-flow-overview)
2. [Orchestrator Architecture](#orchestrator-architecture)
3. [Phase 1: Container Initialization](#phase-1-container-initialization)
4. [Phase 2: Service Initialization](#phase-2-service-initialization)
5. [Phase 3: Runner Preparation](#phase-3-runner-preparation)
6. [Phase 4: Runner Execution](#phase-4-runner-execution)
7. [Phase 5: Evaluation](#phase-5-evaluation)
8. [Phase 6: Container Teardown](#phase-6-container-teardown)
9. [Full Code Trace Example](#full-code-trace-example)
10. [Summary: Container & Runner Lifecycle](#summary-container--runner-lifecycle)

---

## Execution Flow Overview

```
┌─────────────────────────────────────────────────────────────────────────────────────┐
│                         FULL ORCHESTRATOR EXECUTION FLOW                             │
├─────────────────────────────────────────────────────────────────────────────────────┤
│                                                                                      │
│    Orchestrator.run(run_id, target_instruction, attack_instruction)                 │
│                │                                                                     │
│                ▼                                                                     │
│    core/runtime.py:launch_once()                                                    │
│         │                                                                            │
│         ├── setup_runtime()                                                          │
│         │    ├── ServiceManager.start_all()      ← Start GitLab, ownCloud, Plane    │
│         │    ├── ServiceManager.seed_all()       ← Initialize with test data        │
│         │    ├── TaskContainer.build()           ← Build Docker image               │
│         │    ├── TaskContainer.create()          ← Create container                 │
│         │    ├── TaskContainer.start()           ← Start container                  │
│         │    ├── TargetRunner.prepare()          ← Prepare target agent             │
│         │    └── AttackRunner.prepare()          ← Prepare attacker agent           │
│         │                                                                            │
│         ├── execute_run()                                                            │
│         │    ├── TargetRunner.run()              ← Execute target agent             │
│         │    ├── AttackRunner.run()              ← Execute attacker agent           │
│         │    ├── TaskContainer.snapshot()        ← Capture workspace state          │
│         │    └── Evaluator.evaluate()            ← Evaluate results                 │
│         │                                                                            │
│         └── teardown_runtime()                                                       │
│              ├── ServiceManager.reset_all()      ← Reset to clean state             │
│              ├── ServiceManager.stop_all()       ← Stop service containers          │
│              └── TaskContainer.stop()            ← Stop task container              │
│                                                                                      │
│    ✅ Full Docker container lifecycle                                                │
│    ✅ Enterprise services running                                                    │
│    ✅ Agent runners executed in containers                                           │
│                                                                                      │
└─────────────────────────────────────────────────────────────────────────────────────┘
```

---

## Orchestrator Architecture

```
┌─────────────────────────────────────────────────────────────────────────────────────┐
│                           ORCHESTRATOR ARCHITECTURE                                  │
├─────────────────────────────────────────────────────────────────────────────────────┤
│                                                                                      │
│                           ┌─────────────────────┐                                   │
│                           │    Orchestrator     │                                   │
│                           │                     │                                   │
│                           │  orchestrator.py    │                                   │
│                           └──────────┬──────────┘                                   │
│                                      │                                               │
│         ┌────────────────────────────┼────────────────────────────┐                 │
│         │                            │                            │                 │
│         ▼                            ▼                            ▼                 │
│  ┌─────────────────┐          ┌─────────────────┐          ┌─────────────────┐      │
│  │ ServiceManager  │          │  TaskContainer  │          │    Runners      │      │
│  │                 │          │                 │          │                 │      │
│  │ ┌─────────────┐ │          │ ┌─────────────┐ │          │ ┌─────────────┐ │      │
│  │ │   GitLab    │ │          │ │  Workspace  │ │          │ │Target Runner│ │      │
│  │ ├─────────────┤ │          │ │   Mount     │ │          │ ├─────────────┤ │      │
│  │ │  ownCloud   │ │          │ ├─────────────┤ │          │ │Attack Runner│ │      │
│  │ ├─────────────┤ │          │ │ Task Assets │ │          │ └─────────────┘ │      │
│  │ │   Plane     │ │          │ │   Mount     │ │          │                 │      │
│  │ └─────────────┘ │          │ └─────────────┘ │          │ Each runner in  │      │
│  │                 │          │                 │          │ RunnerContainer │      │
│  └─────────────────┘          └─────────────────┘          └─────────────────┘      │
│                                                                                      │
└─────────────────────────────────────────────────────────────────────────────────────┘
```

### Orchestrator Definition

```python
# core/orchestrator.py
class Orchestrator:
    def __init__(
        self,
        service_manager: ServiceManager,
        target_runner: RunnerBase,
        attack_runner: RunnerBase,
        evaluator: EvaluatorBase,
        task_container: TaskContainer,
        trace_sink: TraceSinkBase,
        trace_file: str,
    ) -> None:
        self.service_manager = service_manager
        self.target_runner = target_runner
        self.attack_runner = attack_runner
        self.evaluator = evaluator
        self.task_container = task_container
        self.trace_sink = trace_sink
        self.trace_file = trace_file

    def setup(self) -> None:
        self.service_manager.start_all()
        self.service_manager.seed_all()
        self.task_container.build()
        self.task_container.create()
        self.task_container.start()
        self.task_container.prepare_task_env()
        self.target_runner.prepare()
        self.attack_runner.prepare()

    def run(
        self,
        run_id: str,
        target_instruction_file: str,
        attack_instruction_file: str,
    ) -> EvaluatorResult:
        self.target_runner.run(run_id, target_instruction_file)
        self.attack_runner.run(run_id, attack_instruction_file)

        task_snapshot = self.task_container.snapshot()
        service_snapshots = self.service_manager.snapshot_all()
        self.trace_sink.flush()

        return self.evaluator.evaluate(
            run_id=run_id,
            trace_file=self.trace_file,
            task_snapshot=task_snapshot,
            service_snapshots=service_snapshots,
        )

    def teardown(self) -> None:
        self.service_manager.reset_all()
        self.service_manager.stop_all()
        self.task_container.stop()
```

---

## Phase 1: Container Initialization

### Step 1: Service Container Startup

```python
# Orchestrator.setup()
def setup(self) -> None:
    self.service_manager.start_all()  # Start GitLab, ownCloud, Plane
```

**ServiceManager.start_all() implementation:**

```python
# components/services.py
class ServiceManager:
    def __init__(self, services: list[ServiceBase]) -> None:
        self.services = {service.name: service for service in services}

    def start_all(self) -> None:
        for service in self.services.values():
            service.start()
```

**SingleContainerService.start() (e.g., ownCloud, Plane):**

```python
class SingleContainerService(ServiceBase):
    def __init__(self, name: str, container: ServiceContainer, credentials: CredentialBundle, ...):
        super().__init__(name, credentials, trace_sink)
        self.container = container

    def start(self) -> None:
        self.container.build()           # docker build
        self.container.create()          # docker create
        self.container.start()           # docker start
        self.container.wait_until_healthy()  # Wait for health check
        self.register_endpoints()        # Register URLs
```

**MultiContainerService.start() (e.g., GitLab):**

```python
class MultiContainerService(ServiceBase):
    def __init__(self, name: str, containers: list[ServiceContainer], ...):
        super().__init__(name, credentials, trace_sink)
        self.containers = containers

    def start(self) -> None:
        # Start all containers first
        for container in self.containers:
            container.build()
            container.create()
            container.start()

        # Then wait for all to be healthy
        for container in self.containers:
            container.wait_until_healthy()

        self.register_endpoints()
```

### Step 2: Task Container Startup

```python
# Orchestrator.setup() continued
self.task_container.build()
self.task_container.create()
self.task_container.start()
self.task_container.prepare_task_env()
```

**TaskContainer is a DockerContainer with workspace mounting:**

```python
# components/containers.py
class TaskContainer(DockerContainer):
    """Container for task execution with workspace mounting support."""

    def mount_workspace(self, host_workspace: str, container_workspace: str = "/workspace") -> None:
        self.spec.mounts.append(MountSpec(
            host_path=host_workspace,
            container_path=container_workspace,
            read_only=False,
        ))

    def mount_task_assets(self, task_root: str) -> None:
        self.spec.mounts.append(MountSpec(
            host_path=task_root,
            container_path="/task",
            read_only=True,
        ))

    def prepare_task_env(self) -> None:
        # Setup environment variables, run initialization scripts
        return
```

**DockerContainer.build() - The actual Docker operations:**

```python
class DockerContainer(ContainerBase):
    def build(self) -> None:
        """Build Docker image from Dockerfile."""
        if not self.spec.build_context:
            return

        cmd = ["docker", "build", "-t", self.spec.image]
        if self.spec.dockerfile:
            cmd.extend(["-f", self.spec.dockerfile])
        cmd.append(self.spec.build_context)

        proc = subprocess.run(cmd, capture_output=True, text=True, check=False)
        if proc.returncode != 0:
            raise RuntimeError(f"docker build failed: {proc.stderr.strip()}")

    def create(self) -> None:
        """Create container from image."""
        cmd = ["docker", "create", "--name", self.spec.name]

        # Add network
        if self.spec.network:
            cmd.extend(["--network", self.spec.network])

        # Add working directory
        if self.spec.working_dir:
            cmd.extend(["-w", self.spec.working_dir])

        # Add environment variables
        for key, value in self.spec.env.items():
            cmd.extend(["-e", f"{key}={value}"])

        # Add mounts
        for mount in self.spec.mounts:
            spec = f"type=bind,src={mount.host_path},dst={mount.container_path}"
            if mount.read_only:
                spec += ",readonly"
            cmd.extend(["--mount", spec])

        # Add ports
        for port in self.spec.ports:
            mapping = f"{port.container_port}/{port.protocol}"
            if port.host_port is not None:
                mapping = f"{port.host_port}:{mapping}"
            cmd.extend(["-p", mapping])

        cmd.append(self.spec.image)
        proc = subprocess.run(cmd, capture_output=True, text=True, check=False)
        if proc.returncode != 0:
            raise RuntimeError(f"docker create failed: {proc.stderr.strip()}")

        self.container_id = proc.stdout.strip()

    def start(self) -> None:
        """Start the container."""
        proc = subprocess.run(["docker", "start", self._target()], capture_output=True, check=False)
        if proc.returncode != 0:
            raise RuntimeError(f"docker start failed: {proc.stderr.strip()}")
```

---

## Phase 2: Service Initialization

### Step 3: Service Seeding

```python
# Orchestrator.setup() continued
self.service_manager.seed_all()
```

**What seeding does:**

```python
# components/services.py
class ServiceManager:
    def seed_all(self) -> None:
        for service in self.services.values():
            service.seed()
```

**Example: GitLabService.seed()**

```python
class GitLabService(MultiContainerService):
    def seed(self) -> None:
        """Initialize GitLab with test data."""
        # Create test projects
        # Create test users
        # Push initial files
        # Configure access tokens
        ...
```

**Seeding populates services with test data:**
- GitLab: Projects, repositories, users, tokens
- ownCloud: Files, folders, shares
- Plane: Projects, issues, cycles

---

## Phase 3: Runner Preparation

### Step 4: Runner Container Preparation

```python
# Orchestrator.setup() continued
self.target_runner.prepare()
self.attack_runner.prepare()
```

**RunnerBase.prepare() implementation:**

```python
# components/runners.py
class RunnerBase(ABC):
    def prepare(self) -> None:
        """Prepare runner container for execution."""
        self.container.build()              # Build runner Docker image
        self.container.create()             # Create runner container
        self._install_framework_config()    # Write agent-specific config
        self._install_tools()               # Configure tools
        self._install_mcp_servers()         # Configure MCP servers
        self._install_skills()              # Configure skills
```

**_install_framework_config() - Writing agent configuration:**

```python
def _install_framework_config(self) -> None:
    config = self.make_framework_config()  # Generate config dict
    self.write_framework_config(config)    # Write to container
```

**Example: ClaudeCodeRunner configuration:**

```python
class ClaudeCodeRunner(RunnerBase):
    def framework_name(self) -> str:
        return "claude_code"

    def make_framework_config(self) -> dict[str, Any]:
        """Generate Claude Code settings.json."""
        allow_rules = [t.name for t in self.tools if t.enabled]
        deny_rules = [t.name for t in self.tools if not t.enabled]

        cfg = {
            "permissions": {
                "allow": allow_rules,
                "deny": deny_rules,
            }
        }

        if self.base_url:
            cfg["env"] = {"ANTHROPIC_BASE_URL": self.base_url}

        return cfg

    def write_framework_config(self, config: dict[str, Any]) -> None:
        """Write config to container's settings file."""
        content = json.dumps(config, indent=2)
        self.container.write_text_file("/root/.claude/settings.json", content)
```

**Example: OpenCodeRunner configuration:**

```python
class OpenCodeRunner(RunnerBase):
    def framework_name(self) -> str:
        return "opencode"

    def make_framework_config(self) -> dict[str, Any]:
        """Generate OpenCode opencode.json."""
        cfg = {
            "$schema": "https://opencode.ai/config.json",
            "model": self.model,
            "mcp": {},
            "tools": {},
        }

        if self.base_url:
            cfg["provider"] = {
                "anthropic": {
                    "options": {"baseURL": self.base_url}
                }
            }

        for tool in self.tools:
            cfg["tools"][tool.name] = tool.enabled

        for server in self.mcp_servers:
            if server.enabled:
                if server.transport == "stdio":
                    cfg["mcp"][server.name] = {
                        "command": server.command,
                        "args": server.args,
                        "env": server.env,
                    }
                elif server.transport in {"http", "websocket"}:
                    cfg["mcp"][server.name] = {"url": server.url}

        return cfg

    def write_framework_config(self, config: dict[str, Any]) -> None:
        content = json.dumps(config, indent=2)
        self.container.write_text_file("/root/.config/opencode/opencode.json", content)
```

**RunnerContainer helper methods:**

```python
# components/containers.py
class RunnerContainer(DockerContainer):
    """Container for runner execution with file I/O helpers."""

    def write_text_file(self, path: str, content: str) -> None:
        """Write text file inside container using base64 encoding."""
        payload = base64.b64encode(content.encode("utf-8")).decode("ascii")
        script = (
            "import base64, pathlib, sys; "
            "p=pathlib.Path(sys.argv[1]); "
            "p.parent.mkdir(parents=True, exist_ok=True); "
            "p.write_bytes(base64.b64decode(sys.argv[2]))"
        )
        code, _, stderr = self.exec(["python3", "-c", script, path, payload])
        if code != 0:
            raise RuntimeError(f"failed writing file {path}: {stderr.strip()}")

    def read_text_file(self, path: str) -> str:
        """Read text file from container."""
        script = (
            "from pathlib import Path; import sys; "
            "sys.stdout.write(Path(sys.argv[1]).read_text(encoding='utf-8'))"
        )
        code, stdout, stderr = self.exec(["python3", "-c", script, path])
        if code != 0:
            raise RuntimeError(f"failed reading file {path}: {stderr.strip()}")
        return stdout

    def run_shell(self, command: str) -> tuple[int, str, str]:
        """Run shell command in container."""
        return self.exec(["/bin/bash", "-lc", command])
```

---

## Phase 4: Runner Execution

### Step 5: Running Target Agent

```python
# Orchestrator.run()
def run(self, run_id: str, target_instruction_file: str, attack_instruction_file: str) -> EvaluatorResult:
    self.target_runner.run(run_id, target_instruction_file)
```

**RunnerBase.run() implementation:**

```python
# components/runners.py
class RunnerBase(ABC):
    def run(self, run_id: str, task_instruction_file: str) -> int:
        """Execute the runner with the task instruction."""
        self._trace(run_id, "run_start", "runner_start")

        # Render the command with the instruction file
        command = self.render_command(task_instruction_file)

        # Execute command inside container
        code, stdout, stderr = self.container.exec([self.command.shell, "-lc", command])

        # Handle output and trace
        self._handle_run_output(run_id, stdout, stderr, code)
        self._trace(run_id, "run_end", "runner_end", {"exit_code": code})

        return code

    def render_command(self, task_instruction_file: str) -> str:
        """Replace placeholder with actual instruction file path."""
        return self.command.template.replace("{{task_instruction_file}}", task_instruction_file)
```

**Example: ClaudeCodeRunner.render_command():**

```python
def render_command(self, task_instruction_file: str) -> str:
    # Template: "claude --task {{task_instruction_file}}"
    # Result: "claude --task /task/instructions/target.md"
    return self.command.template.replace("{{task_instruction_file}}", task_instruction_file)
```

**GenericCLIRunner.render_command() with multiple placeholders:**

```python
def render_command(self, task_instruction_file: str) -> str:
    return (
        self.command.template
        .replace("{{task_instruction_file}}", task_instruction_file)
        .replace("{{model}}", self.model or "")
        .replace("{{base_url}}", self.base_url or "")
    )
```

### Step 6: Running Attacker Agent

```python
# Orchestrator.run() continued
self.attack_runner.run(run_id, attack_instruction_file)
```

Same flow as target runner, but with attacker instruction file.

### Step 7: Collecting Snapshots

```python
# Orchestrator.run() continued
task_snapshot = self.task_container.snapshot()
service_snapshots = self.service_manager.snapshot_all()
self.trace_sink.flush()
```

**TaskContainer.snapshot():**

```python
class TaskContainer(DockerContainer):
    def snapshot_workspace(self, workspace_path: str = "/workspace") -> dict[str, str]:
        """Create snapshot of workspace files."""
        # Find the host mount path
        host_mount = None
        for mount in self.spec.mounts:
            if mount.container_path == workspace_path:
                host_mount = mount.host_path
                break

        if not host_mount:
            return {}

        root = Path(host_mount)
        if not root.exists():
            return {}

        snapshot: dict[str, str] = {}
        for path in root.rglob("*"):
            if path.is_file():
                rel = str(path.relative_to(root))
                stat = path.stat()
                snapshot[rel] = f"size={stat.st_size},mtime={int(stat.st_mtime)}"

        snapshot["_snapshot_time"] = str(int(time.time()))
        return snapshot

    def snapshot(self) -> dict[str, str]:
        return self.snapshot_workspace()
```

**ServiceManager.snapshot_all():**

```python
class ServiceManager:
    def snapshot_all(self) -> dict[str, dict]:
        return {name: service.snapshot() for name, service in self.services.items()}
```

---

## Phase 5: Evaluation

### Step 8: Evaluation

```python
# Orchestrator.run() continued
return self.evaluator.evaluate(
    run_id=run_id,
    trace_file=self.trace_file,
    task_snapshot=task_snapshot,
    service_snapshots=service_snapshots,
)
```

**DeterministicEvaluator Flow:**

```
┌─────────────────────────────────────────────────────────────────────────────────────┐
│                        DETERMINISTIC EVALUATOR FLOW                                  │
├─────────────────────────────────────────────────────────────────────────────────────┤
│                                                                                      │
│  1. LOAD MODULE                                                                      │
│     evaluator.py ──► importlib ──► Python module object                             │
│                                                                                      │
│  2. BUILD RUNTIME CONTEXT                                                            │
│     ┌─────────────┐  ┌─────────────┐  ┌─────────────┐                              │
│     │  scoring    │  │   common    │  │   config    │                              │
│     │             │  │             │  │             │                              │
│     │ Checkpoint  │  │ grader()    │  │ GITLAB_USER │                              │
│     │ Result      │  │ gitlab_req  │  │ GITLAB_URL  │                              │
│     │ bonus_fns   │  │ file_helpers│  │ PLANE_URL   │                              │
│     └─────────────┘  └─────────────┘  └─────────────┘                              │
│                                                                                      │
│  3. EXECUTE                                                                          │
│     evaluate(run_id, trace_file, task_snapshot, service_snapshots)                  │
│                                                                                      │
│  4. CONVERT OUTPUT                                                                   │
│     ┌─────────────────────────────────────────────────────────────┐                 │
│     │  evaluator.py output          EvaluatorResult               │                 │
│     │  ──────────────────           ────────────────              │                 │
│     │  {"decision": "pass"}    ──►  decision="pass"               │                 │
│     │  {"score": 0.85}         ──►  score=0.85                    │                 │
│     │  {"subscores": {...}}    ──►  subscores={...}               │                 │
│     │  Checkpoint objects      ──►  converted automatically       │                 │
│     └─────────────────────────────────────────────────────────────┘                 │
│                                                                                      │
└─────────────────────────────────────────────────────────────────────────────────────┘
```

**LLMJudgeEvaluator Flow:**

```
┌─────────────────────────────────────────────────────────────────────────────────────┐
│                           LLM JUDGE EVALUATOR FLOW                                   │
├─────────────────────────────────────────────────────────────────────────────────────┤
│                                                                                      │
│  1. READ INPUTS                                                                      │
│     ┌─────────────┐  ┌─────────────┐  ┌─────────────┐                              │
│     │   rubric    │  │   trace     │  │  snapshots  │                              │
│     │  (JSON/text)│  │  (.jsonl)   │  │   (dict)    │                              │
│     └──────┬──────┘  └──────┬──────┘  └──────┬──────┘                              │
│            │                │                │                                       │
│            └────────────────┼────────────────┘                                       │
│                             ▼                                                        │
│                                                                                      │
│  2. BUILD PROMPT                                                                     │
│     ┌─────────────────────────────────────────────────────────────────┐             │
│     │  System: "You are an evaluation judge. Return JSON..."         │             │
│     │                                                                 │             │
│     │  User: {                                                       │             │
│     │    "rubric": "...evaluation criteria...",                      │             │
│     │    "trace": "...agent actions and outputs...",                 │             │
│     │    "task_snapshot": {...},                                     │             │
│     │    "service_snapshots": {...}                                  │             │
│     │  }                                                             │             │
│     └─────────────────────────────────────────────────────────────────┘             │
│                             │                                                        │
│                             ▼                                                        │
│                                                                                      │
│  3. CALL LLM API                                                                     │
│     POST {JUDGE_BASE_URL}/chat/completions                                          │
│     Headers: Authorization: Bearer {JUDGE_API_KEY}                                  │
│     Body: {"model": "...", "temperature": 0, "response_format": {...}}             │
│                             │                                                        │
│                             ▼                                                        │
│                                                                                      │
│  4. PARSE RESPONSE → EvaluatorResult                                                │
│                                                                                      │
└─────────────────────────────────────────────────────────────────────────────────────┘
```

---

## Phase 6: Container Teardown

### Step 9: Cleanup

```python
# Orchestrator.teardown()
def teardown(self) -> None:
    self.service_manager.reset_all()   # Reset services to clean state
    self.service_manager.stop_all()    # Stop service containers
    self.task_container.stop()         # Stop task container
```

**ServiceManager.reset_all():**

```python
class ServiceManager:
    def reset_all(self) -> None:
        for service in self.services.values():
            service.reset()
```

**Service reset typically:**
- Deletes created data
- Resets to initial seeded state
- Clears caches

**ServiceManager.stop_all():**

```python
class ServiceManager:
    def stop_all(self) -> None:
        # Stop in reverse order (dependencies first)
        for service in reversed(list(self.services.values())):
            service.stop()
```

**ServiceContainer.stop():**

```python
class DockerContainer(ContainerBase):
    def stop(self, timeout_seconds: int = 10) -> None:
        proc = subprocess.run(
            ["docker", "stop", "-t", str(timeout_seconds), self._target()],
            capture_output=True, check=False
        )
        if proc.returncode != 0:
            if "No such container" in proc.stderr:
                return
            raise RuntimeError(f"docker stop failed: {proc.stderr.strip()}")
```

---

## Full Code Trace Example

```
# Construct an Orchestrator with all components
orchestrator = Orchestrator(
    service_manager=service_manager,
    target_runner=target_runner,
    attack_runner=attack_runner,
    evaluator=evaluator,
    task_container=task_container,
    trace_sink=trace_sink,
    trace_file=trace_file,
)

result = launch_once(orchestrator, run_id, target_instruction, attack_instruction)

Execution trace:
│
├── setup_runtime(orchestrator)
│   │
│   ├── service_manager.start_all()
│   │   ├── GitLabService.start()
│   │   │   ├── container.build()     → docker build -t gitlab ...
│   │   │   ├── container.create()    → docker create --name gitlab ...
│   │   │   ├── container.start()     → docker start gitlab
│   │   │   └── wait_until_healthy()  → poll until healthy
│   │   │
│   │   ├── OwnCloudService.start()
│   │   │   ├── container.build()
│   │   │   ├── container.create()
│   │   │   ├── container.start()
│   │   │   └── wait_until_healthy()
│   │   │
│   │   └── PlaneService.start()
│   │       └── ... same pattern
│   │
│   ├── service_manager.seed_all()
│   │   ├── GitLabService.seed()      → Create projects, users, tokens
│   │   ├── OwnCloudService.seed()    → Create files, folders
│   │   └── PlaneService.seed()       → Create projects, issues
│   │
│   ├── task_container.build()        → docker build -t task-image ...
│   ├── task_container.create()       → docker create --name task ...
│   ├── task_container.start()        → docker start task
│   ├── task_container.prepare_task_env()
│   │
│   ├── target_runner.prepare()
│   │   ├── container.build()         → Build runner image
│   │   ├── container.create()        → Create runner container
│   │   └── write_framework_config()  → Write agent config file
│   │
│   └── attack_runner.prepare()
│       └── ... same pattern
│
├── execute_run(orchestrator, run_id, ...)
│   │
│   ├── target_runner.run(run_id, target_instruction)
│   │   ├── render_command()          → "claude --task /task/target.md"
│   │   ├── container.exec()          → Execute in container
│   │   └── _handle_run_output()      → Parse and trace output
│   │
│   ├── attack_runner.run(run_id, attack_instruction)
│   │   └── ... same pattern
│   │
│   ├── task_container.snapshot()     → Scan workspace files
│   ├── service_manager.snapshot_all() → Get service states
│   ├── trace_sink.flush()
│   │
│   └── evaluator.evaluate()
│       └── Return EvaluatorResult
│
└── teardown_runtime(orchestrator)
    │
    ├── service_manager.reset_all()
    │   ├── GitLabService.reset()     → Clear test data
    │   ├── OwnCloudService.reset()   → Delete files
    │   └── PlaneService.reset()      → Clear projects
    │
    ├── service_manager.stop_all()
    │   ├── PlaneService.stop()       → docker stop plane
    │   ├── OwnCloudService.stop()    → docker stop owncloud
    │   └── GitLabService.stop()      → docker stop gitlab
    │
    └── task_container.stop()         → docker stop task
```

---

## Summary: Container & Runner Lifecycle

```
┌─────────────────────────────────────────────────────────────────────────────────────┐
│                      CONTAINER & RUNNER LIFECYCLE                                    │
├─────────────────────────────────────────────────────────────────────────────────────┤
│                                                                                      │
│  SETUP PHASE                                                                         │
│  ──────────                                                                          │
│                                                                                      │
│  Service Containers:                                                                 │
│  ┌──────────┐   ┌──────────┐   ┌──────────┐   ┌──────────┐   ┌──────────┐          │
│  │  build   │──►│  create  │──►│  start   │──►│  healthy │──►│   seed   │          │
│  └──────────┘   └──────────┘   └──────────┘   └──────────┘   └──────────┘          │
│  docker build   docker create  docker start   wait/health  init data               │
│                                                                                      │
│  Task Container:                                                                     │
│  ┌──────────┐   ┌──────────┐   ┌──────────┐   ┌──────────┐                          │
│  │  build   │──►│  create  │──►│  start   │──►│ prepare  │                          │
│  └──────────┘   └──────────┘   └──────────┘   └──────────┘                          │
│                                                                                      │
│  Runner Containers:                                                                  │
│  ┌──────────┐   ┌──────────┐   ┌──────────────┐                                      │
│  │  build   │──►│  create  │──►│ install_cfg  │                                      │
│  └──────────┘   └──────────┘   └──────────────┘                                      │
│                                    Write agent config file                           │
│                                                                                      │
│  ────────────────────────────────────────────────────────────────────────────────── │
│                                                                                      │
│  EXECUTION PHASE                                                                     │
│  ──────────────                                                                      │
│                                                                                      │
│  Target Runner:                                                                      │
│  ┌──────────────┐   ┌──────────────┐   ┌──────────────┐                              │
│  │render_command│──►│ container.exec│──►│ trace_output │                              │
│  └──────────────┘   └──────────────┘   └──────────────┘                              │
│  Template → cmd     Run in Docker    Log events                                      │
│                                                                                      │
│  Attacker Runner:                                                                    │
│  ┌──────────────┐   ┌──────────────┐   ┌──────────────┐                              │
│  │render_command│──►│ container.exec│──►│ trace_output │                              │
│  └──────────────┘   └──────────────┘   └──────────────┘                              │
│                                                                                      │
│  Snapshots:                                                                          │
│  ┌──────────────────┐   ┌──────────────────┐                                         │
│  │ task.snapshot()  │   │ service.snapshot │                                         │
│  └──────────────────┘   └──────────────────┘                                         │
│  Scan workspace files    Get service states                                          │
│                                                                                      │
│  ────────────────────────────────────────────────────────────────────────────────── │
│                                                                                      │
│  TEARDOWN PHASE                                                                      │
│  ──────────────                                                                      │
│                                                                                      │
│  ┌──────────┐   ┌──────────┐                                                        │
│  │  reset   │──►│   stop   │                                                        │
│  └──────────┘   └──────────┘                                                        │
│  Clear data      docker stop                                                         │
│                                                                                      │
└─────────────────────────────────────────────────────────────────────────────────────┘
```

| Stage | Action | Docker Command | Purpose |
|-------|--------|----------------|---------|
| Service Build | `container.build()` | `docker build -t image .` | Build service image |
| Service Create | `container.create()` | `docker create --name svc image` | Create container |
| Service Start | `container.start()` | `docker start svc` | Start container |
| Service Health | `wait_until_healthy()` | Poll `docker inspect` | Wait for ready |
| Service Seed | `service.seed()` | API calls inside container | Initialize data |
| Runner Build | `container.build()` | `docker build -t runner .` | Build runner image |
| Runner Config | `write_framework_config()` | `docker exec` write file | Configure agent |
| Runner Exec | `container.exec()` | `docker exec runner cmd` | Run agent |
| Teardown | `container.stop()` | `docker stop svc` | Stop containers |

"""
Container implementations for OpenART framework.

This module merges all container types:
- ContainerBase: Abstract base class for containers
- DockerContainer: Docker-based container implementation
- TaskContainer: Container for task execution with workspace mounting
- RunnerContainer: Container for runner execution with file I/O helpers
"""

from __future__ import annotations

import base64
import json
import shlex
import subprocess
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any, Optional

from framework.core.helpers import append_runtime_log, snapshot_dir
from framework.models.container import ContainerSpec, MountSpec
from framework.models.common import ContainerState


class ContainerBase(ABC):
    """Abstract base class for container implementations."""

    def __init__(self, spec: ContainerSpec) -> None:
        self.spec = spec
        self.container_id: Optional[str] = None
        self.state = "created"

    @abstractmethod
    def build(self) -> None:
        ...

    @abstractmethod
    def pull(self) -> None:
        ...

    @abstractmethod
    def create(self) -> None:
        ...

    @abstractmethod
    def start(self) -> None:
        ...

    @abstractmethod
    def stop(self, timeout_seconds: int = 10) -> None:
        ...

    @abstractmethod
    def remove(self, force: bool = False) -> None:
        ...

    @abstractmethod
    def exec(
        self,
        cmd: list[str],
        env: Optional[dict[str, str]] = None,
        timeout_seconds: Optional[int] = None,
    ) -> tuple[int, str, str]:
        ...

    @abstractmethod
    def logs(self, tail: int = 500) -> str:
        ...

    @abstractmethod
    def is_healthy(self) -> bool:
        ...

    @abstractmethod
    def snapshot(self) -> dict[str, Any]:
        ...


class DockerContainer(ContainerBase):
    """Docker-based container implementation."""

    def _log_event(self, message: str) -> None:
        line = f"[openart] {message}"
        append_runtime_log(line, self.spec.lifecycle_log_path)

    def _run(self, cmd: list[str]) -> tuple[int, str, str]:
        proc = subprocess.run(cmd, capture_output=True, text=True, check=False)
        return proc.returncode, proc.stdout, proc.stderr

    def _target(self) -> str:
        return self.container_id or self.spec.name

    def build(self) -> None:
        if not self.spec.build_context:
            return

        if not self.spec.image:
            raise ValueError("ContainerSpec.image is required when build_context is set")

        cmd = ["docker", "build", "-t", self.spec.image]
        if self.spec.dockerfile:
            cmd.extend(["-f", self.spec.dockerfile])
        cmd.append(self.spec.build_context)

        self._log_event(f"building container image for {self.spec.name} using {self.spec.build_context}")

        code, _, stderr = self._run(cmd)
        if code != 0:
            self.state = ContainerState.FAILED.value
            raise RuntimeError(f"docker build failed: {stderr.strip()}")

        self._log_event(f"built container image for {self.spec.name}: {self.spec.image}")

    def pull(self) -> None:
        if not self.spec.image:
            return
        code, _, stderr = self._run(["docker", "pull", self.spec.image])
        if code != 0:
            self.state = ContainerState.FAILED.value
            raise RuntimeError(f"docker pull failed: {stderr.strip()}")

    def create(self) -> None:
        if self.container_id:
            return

        image = self.spec.image
        if not image:
            raise ValueError("ContainerSpec.image is required for create")

        inspect_code, _, _ = self._run(["docker", "inspect", self.spec.name])
        if inspect_code == 0:
            self._log_event(f"removing stale container before create name={self.spec.name}")
            rm_code, _, rm_stderr = self._run(["docker", "rm", "-f", self.spec.name])
            if rm_code != 0:
                self.state = ContainerState.FAILED.value
                raise RuntimeError(f"docker rm failed before create: {rm_stderr.strip()}")

        cmd = ["docker", "create", "--name", self.spec.name]

        if self.spec.network:
            cmd.extend(["--network", self.spec.network])

        if self.spec.working_dir:
            cmd.extend(["-w", self.spec.working_dir])

        for key, value in self.spec.env.items():
            cmd.extend(["-e", f"{key}={value}"])

        for mount in self.spec.mounts:
            spec = f"type=bind,src={mount.host_path},dst={mount.container_path}"
            if mount.read_only:
                spec += ",readonly"
            cmd.extend(["--mount", spec])

        for port in self.spec.ports:
            mapping = f"{port.container_port}/{port.protocol}"
            if port.host_port is not None:
                mapping = f"{port.host_port}:{mapping}"
            cmd.extend(["-p", mapping])

        if self.spec.healthcheck:
            health = self.spec.healthcheck
            cmd.extend(["--health-cmd", " ".join(health.command)])
            cmd.extend(["--health-interval", f"{health.interval_seconds}s"])
            cmd.extend(["--health-timeout", f"{health.timeout_seconds}s"])
            cmd.extend(["--health-retries", str(health.retries)])

        cmd.append(image)
        if self.spec.command:
            cmd.extend(self.spec.command)

        code, stdout, stderr = self._run(cmd)
        if code != 0:
            self.state = ContainerState.FAILED.value
            raise RuntimeError(f"docker create failed: {stderr.strip()}")

        self.container_id = stdout.strip()
        self.state = ContainerState.CREATED.value
        self._log_event(
            f"created container name={self.spec.name} id={self.container_id} image={self.spec.image or ''}".strip()
        )

    def start(self) -> None:
        target = self._target()
        code, _, stderr = self._run(["docker", "start", target])
        if code != 0:
            self.state = ContainerState.FAILED.value
            raise RuntimeError(f"docker start failed: {stderr.strip()}")
        self.state = ContainerState.RUNNING.value
        self._log_event(f"started container name={self.spec.name} id={target}")

    def stop(self, timeout_seconds: int = 10) -> None:
        target = self._target()
        code, _, stderr = self._run(
            ["docker", "stop", "-t", str(timeout_seconds), target]
        )
        if code != 0:
            if "No such container" in stderr:
                self.state = ContainerState.STOPPED.value
                return
            raise RuntimeError(f"docker stop failed: {stderr.strip()}")
        self.state = ContainerState.STOPPED.value
        self._log_event(f"stopped container name={self.spec.name} id={target}")

    def remove(self, force: bool = False) -> None:
        target = self._target()
        cmd = ["docker", "rm"]
        if force:
            cmd.append("-f")
        cmd.append(target)
        code, _, stderr = self._run(cmd)
        if code != 0 and "No such container" not in stderr:
            raise RuntimeError(f"docker rm failed: {stderr.strip()}")
        self.state = ContainerState.REMOVED.value
        self._log_event(f"removed container name={self.spec.name} id={target}")
        self.container_id = None

    def exec(
        self,
        cmd: list[str],
        env: Optional[dict[str, str]] = None,
        timeout_seconds: Optional[int] = None,
    ) -> tuple[int, str, str]:
        docker_cmd = ["docker", "exec"]
        if env:
            for key, value in env.items():
                docker_cmd.extend(["-e", f"{key}={value}"])
        docker_cmd.append(self._target())
        if timeout_seconds and timeout_seconds > 0:
            docker_cmd.extend([
                "/usr/bin/timeout",
                "--signal=TERM",
                "--kill-after=10s",
                f"{int(timeout_seconds)}s",
            ])
        docker_cmd.extend(cmd)
        return self._run(docker_cmd)

    def logs(self, tail: int = 500) -> str:
        code, stdout, stderr = self._run(
            ["docker", "logs", "--tail", str(tail), self._target()]
        )
        if code != 0:
            raise RuntimeError(f"docker logs failed: {stderr.strip()}")
        return stdout

    def is_healthy(self) -> bool:
        code, stdout, stderr = self._run(
            ["docker", "inspect", "--format", "{{json .State.Health.Status}}", self._target()]
        )
        if code == 0:
            status = json.loads(stdout.strip())
            return status == "healthy"

        if "map has no entry for key \"Health\"" in stderr:
            code2, stdout2, _ = self._run(
                ["docker", "inspect", "--format", "{{.State.Status}}", self._target()]
            )
            return code2 == 0 and stdout2.strip() == "running"

        return False

    def snapshot(self) -> dict[str, Any]:
        code, stdout, stderr = self._run(["docker", "inspect", self._target()])
        if code != 0:
            raise RuntimeError(f"docker inspect failed: {stderr.strip()}")
        payload = json.loads(stdout)
        if not payload:
            return {}
        return payload[0]


class TaskContainer(DockerContainer):
    """Container for task execution with workspace mounting support."""

    def __init__(self, spec: ContainerSpec, seed_dir: Optional[str] = None) -> None:
        super().__init__(spec)
        self.seed_dir = seed_dir

    def mount_workspace(
        self,
        host_workspace: str,
        container_workspace: str = "/workspace",
    ) -> None:
        self.spec.mounts.append(
            MountSpec(
                host_path=host_workspace,
                container_path=container_workspace,
                read_only=False,
            )
        )

    def mount_task_assets(self, task_root: str) -> None:
        self.spec.mounts.append(
            MountSpec(
                host_path=task_root,
                container_path="/task",
                read_only=True,
            )
        )

    def prepare_task_env(self) -> None:
        script_parts = [
            "set -e",
            "mkdir -p /workspace",
        ]
        if self.seed_dir:
            seed_dir = shlex.quote(self.seed_dir)
            script_parts.append(f"if [ -d {seed_dir} ]; then cp -an {seed_dir}/. /workspace/ 2>/dev/null || true; fi")
        else:
            script_parts.append("if [ -d /task/workspace ]; then cp -an /task/workspace/. /workspace/ 2>/dev/null || true; fi")
            script_parts.append("if [ -d /task/seeds ]; then cp -an /task/seeds/. /workspace/ 2>/dev/null || true; fi")
        script_parts.append("if [ -f /task/env/setup.sh ]; then /bin/bash /task/env/setup.sh; fi")
        script = "; ".join(script_parts)
        code, _, stderr = self.exec(["/bin/bash", "-lc", script])
        if code != 0:
            raise RuntimeError(f"failed to prepare task environment: {stderr.strip()}")

    def snapshot_workspace(self, workspace_path: str = "/workspace") -> dict[str, str]:
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

        return snapshot_dir(root, include_snapshot_time=True)

    def snapshot(self) -> dict[str, str]:
        return self.snapshot_workspace()

    def host_workspace_root(self, workspace_path: str = "/workspace") -> str | None:
        for mount in self.spec.mounts:
            if mount.container_path == workspace_path:
                return mount.host_path
        return None


class RunnerContainer(DockerContainer):
    """Container for runner execution with file I/O helpers."""

    def write_text_file(self, path: str, content: str, env: Optional[dict[str, str]] = None) -> None:
        payload = base64.b64encode(content.encode("utf-8")).decode("ascii")
        script = (
            "import base64, pathlib, sys; "
            "p=pathlib.Path(sys.argv[1]); "
            "p.parent.mkdir(parents=True, exist_ok=True); "
            "p.write_bytes(base64.b64decode(sys.argv[2]))"
        )
        code, _, stderr = self.exec(["python3", "-c", script, path, payload], env=env)
        if code != 0:
            raise RuntimeError(f"failed writing file {path}: {stderr.strip()}")

    def ensure_dir(self, path: str, env: Optional[dict[str, str]] = None) -> None:
        code, _, stderr = self.exec(["mkdir", "-p", path], env=env)
        if code != 0:
            raise RuntimeError(f"failed creating directory {path}: {stderr.strip()}")

    def run_shell(self, command: str, env: Optional[dict[str, str]] = None) -> tuple[int, str, str]:
        return self.exec(["/bin/bash", "-lc", command], env=env)

    def read_text_file(self, path: str, env: Optional[dict[str, str]] = None) -> str:
        script = (
            "from pathlib import Path; import sys; "
            "sys.stdout.write(Path(sys.argv[1]).read_text(encoding='utf-8'))"
        )
        code, stdout, stderr = self.exec(["python3", "-c", script, path], env=env)
        if code != 0:
            raise RuntimeError(f"failed reading file {path}: {stderr.strip()}")
        return stdout
__all__ = [
    "ContainerBase",
    "DockerContainer",
    "TaskContainer",
    "RunnerContainer",
]

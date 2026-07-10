"""
Container implementations for OpenART framework.

This module merges all container types:
- ContainerBase: Abstract base class for containers
- DockerContainer: Docker-based container implementation
- TaskContainer: Container for task execution with workspace mounting
- RunnerContainer: Container for runner execution with file I/O helpers
"""

from __future__ import annotations

from contextlib import contextmanager
import json
import os
import shlex
import subprocess
import tempfile
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any, Iterator, Optional

from framework.core.helpers import append_runtime_log, snapshot_dir
from framework.models.container import ContainerSpec, MountSpec
from framework.models.common import ContainerState


OPENART_MANAGED_LABEL = "org.openart.managed"
OPENART_RUN_ID_LABEL = "org.openart.run_id"
_DOCKER_ENV_INLINE_MAX_BYTES = 32 * 1024
_DOCKER_ENV_INLINE_MAX_ITEM_BYTES = 8 * 1024
_DOCKER_ENV_INLINE_MAX_VARS = 64
_DOCKER_ENV_FILE_DIR = "/tmp"


def _normalize_env(env: dict[str, str]) -> list[tuple[str, str]]:
    return [(str(key), str(value)) for key, value in env.items()]


def _inline_env_size(env_items: list[tuple[str, str]]) -> int:
    return sum(len(key.encode("utf-8")) + len(value.encode("utf-8")) + 2 for key, value in env_items)


def _inline_env_item_size(key: str, value: str) -> int:
    return len(key.encode("utf-8")) + len(value.encode("utf-8")) + 1


def _validate_env_file_item(key: str, value: str) -> None:
    if not key:
        raise ValueError("Docker environment variable name cannot be empty")
    if "=" in key:
        raise ValueError(f"Docker environment variable name cannot contain '=': {key!r}")
    if "\x00" in key or "\x00" in value:
        raise ValueError(f"Docker environment variable {key!r} cannot contain NUL bytes")
    if "\n" in key or "\r" in key or "\n" in value or "\r" in value:
        raise ValueError(
            f"Docker --env-file cannot safely encode newline characters in environment variable {key!r}"
        )


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
        try:
            proc = subprocess.run(cmd, capture_output=True, text=True, check=False)
            return proc.returncode, proc.stdout, proc.stderr
        except FileNotFoundError as exc:
            raise RuntimeError(f"Command not found: {cmd[0]}. Is Docker installed?") from exc
        except PermissionError as exc:
            raise RuntimeError(f"Permission denied running: {' '.join(cmd)}") from exc
        except OSError as exc:
            raise RuntimeError(f"OS error running command: {exc}") from exc

    def _run_with_input(self, cmd: list[str], input_data: bytes) -> tuple[int, str, str]:
        try:
            proc = subprocess.run(cmd, input=input_data, capture_output=True, check=False)
            stdout = proc.stdout.decode("utf-8", errors="replace")
            stderr = proc.stderr.decode("utf-8", errors="replace")
            return proc.returncode, stdout, stderr
        except FileNotFoundError as exc:
            raise RuntimeError(f"Command not found: {cmd[0]}. Is Docker installed?") from exc
        except PermissionError as exc:
            raise RuntimeError(f"Permission denied running: {' '.join(cmd)}") from exc
        except OSError as exc:
            raise RuntimeError(f"OS error running command: {exc}") from exc

    def _target(self) -> str:
        return self.container_id or self.spec.name

    @contextmanager
    def _docker_env_args(self, env: Optional[dict[str, str]]) -> Iterator[list[str]]:
        if not env:
            yield []
            return

        env_items = _normalize_env(env)
        if (
            len(env_items) <= _DOCKER_ENV_INLINE_MAX_VARS
            and _inline_env_size(env_items) <= _DOCKER_ENV_INLINE_MAX_BYTES
            and all(_inline_env_item_size(key, value) <= _DOCKER_ENV_INLINE_MAX_ITEM_BYTES for key, value in env_items)
        ):
            args: list[str] = []
            for key, value in env_items:
                args.extend(["-e", f"{key}={value}"])
            yield args
            return

        for key, value in env_items:
            _validate_env_file_item(key, value)

        fd, path = tempfile.mkstemp(
            prefix="openart-docker-env-",
            suffix=".env",
            dir=_DOCKER_ENV_FILE_DIR,
            text=True,
        )
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as handle:
                for key, value in env_items:
                    handle.write(f"{key}={value}\n")
            yield ["--env-file", path]
        finally:
            try:
                os.unlink(path)
            except FileNotFoundError:
                pass

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

        labels = {
            OPENART_MANAGED_LABEL: "true",
            **{str(key): str(value) for key, value in self.spec.labels.items() if str(key).strip()},
        }
        for key, value in labels.items():
            cmd.extend(["--label", f"{key}={value}"])

        with self._docker_env_args(self.spec.env) as env_args:
            cmd.extend(env_args)

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
        with self._docker_env_args(env) as env_args:
            docker_cmd.extend(env_args)
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

    def exec_with_stdin(
        self,
        cmd: list[str],
        input_data: bytes,
        env: Optional[dict[str, str]] = None,
    ) -> tuple[int, str, str]:
        docker_cmd = ["docker", "exec", "-i"]
        with self._docker_env_args(env) as env_args:
            docker_cmd.extend(env_args)
            docker_cmd.append(self._target())
            docker_cmd.extend(cmd)
            return self._run_with_input(docker_cmd, input_data)

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


def remove_openart_containers_for_run(run_id: str, lifecycle_log_path: str | None = None) -> None:
    run_id = str(run_id or "").strip()
    if not run_id:
        return
    cmd = [
        "docker",
        "ps",
        "-aq",
        "--filter",
        f"label={OPENART_MANAGED_LABEL}=true",
        "--filter",
        f"label={OPENART_RUN_ID_LABEL}={run_id}",
    ]
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, check=False)
    except Exception as exc:
        append_runtime_log(f"[openart] label cleanup list failed for run_id={run_id}: {exc}", lifecycle_log_path)
        return
    if proc.returncode != 0:
        append_runtime_log(
            f"[openart] label cleanup list failed for run_id={run_id}: {proc.stderr.strip()}",
            lifecycle_log_path,
        )
        return
    ids = [line.strip() for line in proc.stdout.splitlines() if line.strip()]
    if not ids:
        return
    rm = subprocess.run(["docker", "rm", "-f", *ids], capture_output=True, text=True, check=False)
    if rm.returncode != 0:
        append_runtime_log(
            f"[openart] label cleanup rm failed for run_id={run_id}: {rm.stderr.strip()}",
            lifecycle_log_path,
        )


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

    def write_bytes_file(self, path: str, content: bytes, env: Optional[dict[str, str]] = None) -> None:
        script = (
            "import pathlib, sys; "
            "p=pathlib.Path(sys.argv[1]); "
            "p.parent.mkdir(parents=True, exist_ok=True); "
            "p.write_bytes(sys.stdin.buffer.read())"
        )
        code, _, stderr = self.exec_with_stdin(["python3", "-c", script, path], content, env=env)
        if code != 0:
            raise RuntimeError(f"failed writing file {path}: {stderr.strip()}")

    def write_text_file(self, path: str, content: str, env: Optional[dict[str, str]] = None) -> None:
        self.write_bytes_file(path, content.encode("utf-8"), env=env)

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

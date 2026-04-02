from __future__ import annotations

import json
import shlex
import time
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any, Optional

from framework.attackers.models import AttackerContext, AttackerResult, AttackerSpec
from framework.components.containers import RunnerContainer
from framework.components.trace import TraceSinkBase
from framework.core.helpers import append_runtime_log, capture_workspace_listing, write_json_artifact, write_text_artifact
from framework.models.common import ToolSpec
from framework.models.specs import TraceEvent


class AttackerBase(ABC):
    def __init__(
        self,
        spec: AttackerSpec,
        container: RunnerContainer,
        tools: list[ToolSpec],
        runtime_env: Optional[dict[str, str]] = None,
        artifact_dir: Optional[str] = None,
        trace_sink: Optional[TraceSinkBase] = None,
    ) -> None:
        self.spec = spec
        self.container = container
        self.tools = tools
        self.runtime_env = dict(runtime_env or {})
        self.artifact_dir = artifact_dir
        self.trace_sink = trace_sink
        self._tool_source_map: dict[str, str] = {}

    def prepare(self) -> None:
        self.container.build()
        self.container.create()
        self.container.start()
        self._prepare_runtime_dirs()
        self._install_tools()
        self._capture_prepare_artifacts()

    def stop(self) -> None:
        try:
            self.container.stop()
        except Exception:
            return

    def remove(self, force: bool = True) -> None:
        try:
            self.container.remove(force=force)
        except Exception:
            return

    @abstractmethod
    def run(self, context: AttackerContext) -> AttackerResult:
        raise NotImplementedError

    def _state_dir(self) -> str:
        return self.runtime_env.get("OPENART_ATTACKER_STATE_DIR", f"/tmp/openart/attackers/{self.spec.name}/state")

    def _tool_bin_dir(self) -> str:
        return f"{self._state_dir()}/tools/bin"

    def _tool_source_container_root(self) -> str:
        return f"{self._state_dir()}/tools/src"

    def _tool_guide_path(self) -> str:
        return f"{self._state_dir()}/tools/guide.md"

    def _artifact_dir(self) -> Path | None:
        if not self.artifact_dir:
            return None
        return Path(self.artifact_dir) / "attacker_outputs" / self.spec.name

    def _write_artifact(self, file_name: str, content: str) -> None:
        artifact_dir = self._artifact_dir()
        if artifact_dir is None:
            return
        write_text_artifact(artifact_dir / file_name, content)

    def _append_runtime_log(self, line: str) -> None:
        if not self.artifact_dir:
            return
        append_runtime_log(line, Path(self.artifact_dir) / "runtime.log")

    def _prepare_runtime_dirs(self) -> None:
        for path in (self._state_dir(), self.runtime_env.get("HOME", ""), self.runtime_env.get("XDG_CONFIG_HOME", "")):
            if path:
                self.container.ensure_dir(path, env=self.runtime_env)

    def _stage_tool_sources(self) -> None:
        source_roots: list[str] = []
        for tool in self.tools:
            root = str(tool.source_root or "").strip()
            if root and root not in source_roots:
                source_roots.append(root)
        if not source_roots:
            return

        container_root = self._tool_source_container_root()
        self.container.ensure_dir(container_root, env=self.runtime_env)
        for index, root in enumerate(source_roots, start=1):
            host_root = Path(root)
            if not host_root.is_dir():
                continue
            staged_root = f"{container_root}/bundle_{index}"
            self._tool_source_map[str(host_root.resolve())] = staged_root
            self.container.ensure_dir(staged_root, env=self.runtime_env)
            for path in sorted(host_root.rglob("*")):
                if not path.is_file() or "__pycache__" in path.parts or path.suffix in {".pyc", ".pyo"}:
                    continue
                rel = path.relative_to(host_root).as_posix()
                try:
                    content = path.read_text(encoding="utf-8")
                except UnicodeDecodeError:
                    continue
                self.container.write_text_file(f"{staged_root}/{rel}", content, env=self.runtime_env)

    def _resolve_tool_path_value(self, tool: ToolSpec, value: str | None) -> str | None:
        text = str(value or "").strip()
        if not text or text.startswith("/"):
            return text or None
        source_root = str(tool.source_root or "").strip()
        if not source_root:
            return text
        host_root = Path(source_root)
        candidate = host_root / text
        if not candidate.exists():
            return text
        staged_root = self._tool_source_map.get(str(host_root.resolve()))
        if not staged_root:
            return text
        return f"{staged_root}/{candidate.relative_to(host_root).as_posix()}"

    def _resolve_tool_command(self, tool: ToolSpec) -> str | None:
        return self._resolve_tool_path_value(tool, tool.command)

    def _resolve_tool_args(self, tool: ToolSpec) -> list[str]:
        return [self._resolve_tool_path_value(tool, arg) or str(arg) for arg in tool.args]

    def _tool_wrapper_script(self, tool: ToolSpec) -> str:
        command_parts = [self._resolve_tool_command(tool) or ""] + self._resolve_tool_args(tool)
        quoted_command = " ".join(shlex.quote(part) for part in command_parts if str(part).strip())
        lines = ["#!/usr/bin/env bash", "set -euo pipefail"]
        for key, value in tool.env.items():
            lines.append(f"export {key}={shlex.quote(value)}")
        for key, source in tool.env_from.items():
            lines.append(f"export {key}=\"${{{source}:-}}\"")
        lines.append(f"exec {quoted_command} \"$@\"")
        return "\n".join(lines) + "\n"

    def _install_tools(self) -> None:
        self._stage_tool_sources()
        payload = [
            {
                "name": tool.name,
                "enabled": tool.enabled,
                "description": tool.description,
                "command": self._resolve_tool_command(tool),
                "args": self._resolve_tool_args(tool),
                "env": tool.env,
                "env_from": tool.env_from,
                "usage": tool.usage,
                "source_root": tool.source_root,
                "config": tool.config,
            }
            for tool in self.tools
        ]
        path = f"{self._state_dir()}/tools.json"
        self.container.write_text_file(path, json.dumps(payload, ensure_ascii=True, indent=2), env=self.runtime_env)
        self.runtime_env["OPENART_TOOLS_FILE"] = path

        wrapper_tools = [tool for tool in self.tools if tool.enabled and tool.command]
        if wrapper_tools:
            bin_dir = self._tool_bin_dir()
            self.container.ensure_dir(bin_dir, env=self.runtime_env)
            for tool in wrapper_tools:
                tool_path = f"{bin_dir}/{tool.name}"
                self.container.write_text_file(tool_path, self._tool_wrapper_script(tool), env=self.runtime_env)
                self.container.exec(["chmod", "+x", tool_path], env=self.runtime_env)
            path_parts = [bin_dir, self.runtime_env.get("PATH", "") or "/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin"]
            self.runtime_env["PATH"] = ":".join(path_parts)

        guide = (self.spec.tool_guide_markdown or "").strip()
        if not guide and any(tool.enabled for tool in self.tools):
            lines = ["# Available Tools", ""]
            for tool in self.tools:
                if not tool.enabled:
                    continue
                lines.append(f"- `{tool.name}`")
                if tool.description:
                    lines.append(f"  - {tool.description}")
                if tool.usage:
                    lines.append(f"  - Usage: `{tool.usage}`")
            guide = "\n".join(lines).rstrip()
        if guide:
            guide_path = self._tool_guide_path()
            self.container.ensure_dir(str(Path(guide_path).parent), env=self.runtime_env)
            self.container.write_text_file(guide_path, guide + "\n", env=self.runtime_env)
            self.runtime_env["OPENART_TOOL_GUIDE_FILE"] = guide_path

    def _capture_prepare_artifacts(self) -> None:
        artifact_dir = self._artifact_dir()
        if artifact_dir is None:
            return
        summary = {
            "name": self.spec.name,
            "phase": self.spec.phase,
            "container_name": self.container.spec.name,
            "container_id": self.container.container_id or "",
            "state_dir": self._state_dir(),
            "runtime_env_paths": {
                key: self.runtime_env.get(key, "")
                for key in ("OPENART_TOOLS_FILE", "OPENART_TOOL_GUIDE_FILE")
                if self.runtime_env.get(key)
            },
        }
        if self.runtime_env.get("OPENART_TOOLS_FILE"):
            try:
                tools_content = self.container.read_text_file(self.runtime_env["OPENART_TOOLS_FILE"], env=self.runtime_env)
                self._write_artifact("prepared/tools.json", tools_content)
            except Exception as exc:
                summary["tools_error"] = str(exc)
        if self.runtime_env.get("OPENART_TOOL_GUIDE_FILE"):
            try:
                guide_content = self.container.read_text_file(self.runtime_env["OPENART_TOOL_GUIDE_FILE"], env=self.runtime_env)
                self._write_artifact("prepared/tool_guide.md", guide_content)
            except Exception as exc:
                summary["tool_guide_error"] = str(exc)
        write_json_artifact(artifact_dir / "prepared" / "summary.json", summary, ensure_ascii=True)

    def _capture_workspace_listing(self, label: str) -> None:
        content = capture_workspace_listing(
            lambda: self.container.exec(["/bin/sh", "-lc", "ls -laR /workspace"], env=self.runtime_env)
        )
        self._write_artifact(f"workspace_{label}_ls.txt", content)

    def _write_status(self, exit_code: int) -> None:
        artifact_dir = self._artifact_dir()
        if artifact_dir is None:
            return
        write_json_artifact(
            artifact_dir / "status.json",
            {
                "name": self.spec.name,
                "phase": self.spec.phase,
                "exit_code": exit_code,
                "timestamp": time.time(),
            },
            ensure_ascii=True,
        )

    def _trace(self, run_id: str, event_type: str, message: str, payload: Optional[dict[str, Any]] = None) -> None:
        if not self.trace_sink:
            return
        self.trace_sink.write(
            TraceEvent(
                run_id=run_id,
                source_role="attack",
                event_type=event_type,
                timestamp=time.time(),
                message=message,
                payload=payload or {},
            )
        )

    def _log_output(self, stdout: str, stderr: str, exit_code: int) -> None:
        self._append_runtime_log(
            f"[openart][attacker:{self.spec.name}] exit_code={exit_code} container={self.container.spec.name}"
        )
        for stream_name, text in (("stdout", stdout), ("stderr", stderr)):
            for line in text.splitlines() or [""]:
                content = line if line else "(empty)"
                self._append_runtime_log(f"[openart][attacker:{self.spec.name}][{stream_name}] {content}")

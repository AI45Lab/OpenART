"""
Runner implementations for OpenART framework.

This module merges all runner types:
- RunnerBase: Abstract base class for runners
- RunnerRegistry: Registry for runner types
- OpenCodeRunner: Runner for OpenCode CLI
- ClaudeCodeRunner: Runner for Claude Code CLI
- IFlowRunner: Runner for iFlow CLI
- GenericCLIRunner: Generic CLI runner
"""

from __future__ import annotations

import json
import shlex
import time
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any, Optional

from framework.core.helpers import append_runtime_log, capture_workspace_listing, write_json_artifact, write_text_artifact
from framework.models.common import (
    CommandSpec,
    CredentialBundle,
    MCPServerSpec,
    SkillSpec,
    ToolSpec,
)
from framework.models.specs import TraceEvent
from framework.components.trace import TraceSinkBase


class RunnerBase(ABC):
    """Abstract base class for runner implementations."""

    def __init__(
        self,
        name: str,
        role: str,
        container: "RunnerContainer",
        command: CommandSpec,
        credentials: CredentialBundle,
        tools: Optional[list[ToolSpec]] = None,
        mcp_servers: Optional[list[MCPServerSpec]] = None,
        skills: Optional[list[SkillSpec]] = None,
        tool_guide_markdown: Optional[str] = None,
        trace_sink: Optional[TraceSinkBase] = None,
        base_url: Optional[str] = None,
        model: Optional[str] = None,
        extra_config: Optional[dict[str, Any]] = None,
        runtime_env: Optional[dict[str, str]] = None,
        artifact_dir: Optional[str] = None,
    ) -> None:
        self.name = name
        self.role = role
        self.container = container
        self.command = command
        self.credentials = credentials
        self.tools = tools or []
        self.mcp_servers = mcp_servers or []
        self.skills = skills or []
        self.tool_guide_markdown = str(tool_guide_markdown or "")
        self.trace_sink = trace_sink
        self.base_url = base_url
        self.model = model
        self.extra_config = extra_config or {}
        self.runtime_env = dict(runtime_env or {})
        self.artifact_dir = artifact_dir
        self._tool_source_map: dict[str, str] = {}

    def prepare(self) -> None:
        self.container.build()
        self.container.create()
        self.container.start()
        self._prepare_runtime_dirs()
        self._install_framework_config()
        self._install_tools()
        self._install_mcp_servers()
        self._install_skills()
        self._capture_prepare_artifacts()

    def run(self, run_id: str, task_instruction_file: str) -> int:
        self._capture_workspace_listing("before_run")
        self._trace(run_id, "run_start", "runner_start")
        command = self.render_command(task_instruction_file)
        path_override = self.runtime_env.get("PATH", "").strip()
        if path_override:
            command = f"export PATH={shlex.quote(path_override)}; {command}"
        self._write_runner_artifact("command.sh", command + "\n")
        code, stdout, stderr = self.container.exec([self.command.shell, "-lc", command], env=self.runtime_env)
        self._handle_run_output(run_id, stdout, stderr, code)
        self._capture_workspace_listing("after_run")
        self._trace(run_id, "run_end", "runner_end", {"exit_code": code})
        return code

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
    def framework_name(self) -> str:
        ...

    @abstractmethod
    def make_framework_config(self) -> dict[str, Any]:
        ...

    @abstractmethod
    def write_framework_config(self, config: dict[str, Any]) -> None:
        ...

    @abstractmethod
    def render_command(self, task_instruction_file: str) -> str:
        ...

    @abstractmethod
    def parse_output(
        self,
        run_id: str,
        stdout: str,
        stderr: str,
        exit_code: int,
    ) -> list[TraceEvent]:
        ...

    def validate_tools(self) -> None:
        for tool in self.tools:
            name = str(tool.name or "").strip()
            if not name:
                raise ValueError("tool name is required")
            if any(ch.isspace() for ch in name) or "/" in name or ".." in name:
                raise ValueError(f"invalid tool name: {name}")

    def validate_mcp_servers(self) -> None:
        return

    def validate_skills(self) -> None:
        return

    def framework_config_path(self) -> str | None:
        return None

    def _template_args_without_task_placeholder(self, default_args: list[str]) -> list[str]:
        template = (self.command.template or "").strip()
        if not template:
            return list(default_args)

        normalized = template
        for marker in ('"{{task_instruction_file}}"', "'{{task_instruction_file}}'", "{{task_instruction_file}}"):
            normalized = normalized.replace(marker, " ")

        try:
            parsed = [arg for arg in shlex.split(normalized) if arg]
        except ValueError:
            return list(default_args)

        return parsed or list(default_args)

    def _render_prompt_cli_command(self, task_instruction_file: str, args: list[str]) -> str:
        quoted_args = " ".join(shlex.quote(arg) for arg in args)
        quoted_task_path = shlex.quote(task_instruction_file)
        return (
            f'prompt=$(cat {quoted_task_path}); '
            'guide_file="${OPENART_TOOL_GUIDE_FILE:-}"; '
            'if [ -n "$guide_file" ] && [ -f "$guide_file" ]; then '
            'guide=$(cat "$guide_file"); '
            "prompt=$(printf 'OpenART runtime note:\n- Your working directory is /workspace.\n- Use the available local tools below when they match the task.\n\n%s\n\nTask:\n%s' \"$guide\" \"$prompt\"); "
            'fi; '
            f'exec {quoted_args} "$prompt"'
        )

    def _install_framework_config(self) -> None:
        config = self.make_framework_config()
        self.write_framework_config(config)

    def _install_tools(self) -> None:
        self.validate_tools()
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
        self._install_tool_wrappers()
        self._install_tool_guide()

    def _tool_bin_dir(self) -> str:
        return f"{self._state_dir()}/tools/bin"

    def _tool_source_container_root(self) -> str:
        return f"{self._state_dir()}/tools/src"

    def _tool_guide_path(self) -> str:
        return f"{self._state_dir()}/tools/guide.md"

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
                if not path.is_file():
                    continue
                if "__pycache__" in path.parts or path.suffix in {".pyc", ".pyo"}:
                    continue
                rel = path.relative_to(host_root).as_posix()
                target_path = f"{staged_root}/{rel}"
                try:
                    content = path.read_text(encoding="utf-8")
                except UnicodeDecodeError:
                    continue
                self.container.write_text_file(target_path, content, env=self.runtime_env)

    def _resolve_tool_path_value(self, tool: ToolSpec, value: str | None) -> str | None:
        text = str(value or "").strip()
        if not text:
            return None
        if text.startswith("/"):
            return text

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
        resolved: list[str] = []
        for arg in tool.args:
            resolved.append(self._resolve_tool_path_value(tool, arg) or str(arg))
        return resolved

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

    def _install_tool_wrappers(self) -> None:
        wrapper_tools = [tool for tool in self.tools if tool.enabled and tool.command]
        if not wrapper_tools:
            return
        bin_dir = self._tool_bin_dir()
        self.container.ensure_dir(bin_dir, env=self.runtime_env)
        for tool in wrapper_tools:
            path = f"{bin_dir}/{tool.name}"
            self.container.write_text_file(path, self._tool_wrapper_script(tool), env=self.runtime_env)
            self.container.exec(["chmod", "+x", path], env=self.runtime_env)

        current_path = self.runtime_env.get("PATH", "").strip()
        path_parts = [bin_dir, current_path or "/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin"]
        self.runtime_env["PATH"] = ":".join(path_parts)

    def _auto_tool_guide_markdown(self) -> str:
        lines = ["# Available Tools", ""]
        for tool in self.tools:
            if not tool.enabled:
                continue
            lines.append(f"- `{tool.name}`")
            if tool.description:
                lines.append(f"  - {tool.description}")
            if tool.usage:
                lines.append(f"  - Usage: `{tool.usage}`")
        return "\n".join(lines).rstrip() + "\n"

    def _install_tool_guide(self) -> None:
        guide = self.tool_guide_markdown.strip()
        if not guide:
            if not any(tool.enabled for tool in self.tools):
                return
            guide = self._auto_tool_guide_markdown().strip()
        if not guide:
            return
        path = self._tool_guide_path()
        self.container.ensure_dir(str(Path(path).parent), env=self.runtime_env)
        self.container.write_text_file(path, guide + "\n", env=self.runtime_env)
        self.runtime_env["OPENART_TOOL_GUIDE_FILE"] = path

    def _install_mcp_servers(self) -> None:
        self.validate_mcp_servers()
        payload = [
            {
                "name": server.name,
                "transport": server.transport,
                "command": server.command,
                "args": server.args,
                "url": server.url,
                "env": server.env,
                "enabled": server.enabled,
            }
            for server in self.mcp_servers
        ]
        path = f"{self._state_dir()}/mcp_servers.json"
        self.container.write_text_file(path, json.dumps(payload, ensure_ascii=True, indent=2), env=self.runtime_env)
        self.runtime_env["OPENART_MCP_FILE"] = path

    def _install_skills(self) -> None:
        self.validate_skills()
        payload = [
            {
                "name": skill.name,
                "description": skill.description,
                "config": skill.config,
            }
            for skill in self.skills
        ]
        path = f"{self._state_dir()}/skills.json"
        self.container.write_text_file(path, json.dumps(payload, ensure_ascii=True, indent=2), env=self.runtime_env)
        self.runtime_env["OPENART_SKILLS_FILE"] = path


    def _state_dir(self) -> str:
        return self.runtime_env.get("OPENART_RUNNER_STATE_DIR", f"/workspace/.openart/runners/{self.role}/state")

    def _prepare_runtime_dirs(self) -> None:
        paths = [
            self.runtime_env.get("HOME", ""),
            self.runtime_env.get("XDG_CONFIG_HOME", ""),
            self.runtime_env.get("XDG_DATA_HOME", ""),
            self.runtime_env.get("XDG_CACHE_HOME", ""),
            self._state_dir(),
        ]
        for path in paths:
            if path:
                self.container.ensure_dir(path, env=self.runtime_env)

    def _handle_run_output(
        self,
        run_id: str,
        stdout: str,
        stderr: str,
        exit_code: int,
    ) -> None:
        self._write_output_artifacts(stdout, stderr, exit_code)
        self._log_run_output(stdout, stderr, exit_code)
        if stderr.strip():
            self._trace(run_id, "error", "runner_stderr", {"stderr": stderr})

        for event in self.parse_output(run_id, stdout, stderr, exit_code):
            if self.trace_sink:
                self.trace_sink.write(event)

    def _trace(
        self,
        run_id: str,
        event_type: str,
        message: str,
        payload: Optional[dict[str, Any]] = None,
    ) -> None:
        if not self.trace_sink:
            return

        self.trace_sink.write(
            TraceEvent(
                run_id=run_id,
                source_role=self.role,
                event_type=event_type,
                timestamp=time.time(),
                message=message,
                payload=payload or {},
            )
        )

    def _artifact_role_dir(self) -> Path | None:
        if not self.artifact_dir:
            return None
        return Path(self.artifact_dir) / "runner_outputs" / self.role

    def _write_runner_artifact(self, file_name: str, content: str) -> None:
        role_dir = self._artifact_role_dir()
        if role_dir is None:
            return
        write_text_artifact(role_dir / file_name, content)

    def _runtime_log_path(self) -> Path | None:
        if not self.artifact_dir:
            return None
        return Path(self.artifact_dir) / "runtime.log"

    def _append_runtime_log(self, line: str) -> None:
        append_runtime_log(line, self._runtime_log_path())

    def _log_text_block(self, stream_name: str, text: str) -> None:
        lines = text.splitlines() or [""]
        for line in lines:
            content = line if line else "(empty)"
            self._append_runtime_log(f"[openart][{self.role}][{stream_name}] {content}")

    def _log_run_output(self, stdout: str, stderr: str, exit_code: int) -> None:
        self._append_runtime_log(
            f"[openart][{self.role}] runner exit_code={exit_code} framework={self.framework_name()} container={self.container.spec.name}"
        )
        self._log_text_block("stdout", stdout)
        self._log_text_block("stderr", stderr)

    def _capture_prepare_artifacts(self) -> None:
        summary: dict[str, Any] = {
            "framework": self.framework_name(),
            "role": self.role,
            "container_name": self.container.spec.name,
            "container_id": self.container.container_id or "",
            "state_dir": self._state_dir(),
            "runtime_env_paths": {
                key: self.runtime_env.get(key, "")
                for key in (
                    "OPENART_TOOLS_FILE",
                    "OPENART_TOOL_GUIDE_FILE",
                    "OPENART_MCP_FILE",
                    "OPENART_SKILLS_FILE",
                )
                if self.runtime_env.get(key)
            },
        }

        files: list[tuple[str, str | None, str]] = [
            ("framework_config", self.framework_config_path(), ".json"),
            ("tools", self.runtime_env.get("OPENART_TOOLS_FILE"), ".json"),
            ("tool_guide", self.runtime_env.get("OPENART_TOOL_GUIDE_FILE"), ".md"),
            ("mcp_servers", self.runtime_env.get("OPENART_MCP_FILE"), ".json"),
            ("skills", self.runtime_env.get("OPENART_SKILLS_FILE"), ".json"),
        ]

        for label, container_path, suffix in files:
            if not container_path:
                summary[label] = {"path": "", "present": False}
                continue
            item: dict[str, Any] = {"path": container_path, "present": False}
            try:
                content = self.container.read_text_file(container_path, env=self.runtime_env)
                item["present"] = True
                artifact_name = f"prepared/{label}{suffix}"
                self._write_runner_artifact(artifact_name, content)
                if label == "framework_config":
                    item["mentions_tools"] = '"tools"' in content or "tools" in content
                    item["mentions_mcp"] = '"mcp"' in content or "mcpServers" in content
                    item["mentions_skills"] = '"skills"' in content or "skills" in content
            except Exception as exc:
                item["error"] = str(exc)
            summary[label] = item

        role_dir = self._artifact_role_dir()
        if role_dir is not None:
            write_json_artifact(role_dir / "prepared" / "summary.json", summary, ensure_ascii=True)

    def _capture_workspace_listing(self, label: str) -> None:
        content = capture_workspace_listing(
            lambda: self.container.exec(["/bin/sh", "-lc", "ls -laR /workspace"], env=self.runtime_env)
        )
        self._write_runner_artifact(f"workspace_{label}_ls.txt", content)

    def _write_output_artifacts(self, stdout: str, stderr: str, exit_code: int) -> None:
        self._write_runner_artifact("stdout.txt", stdout)
        self._write_runner_artifact("stderr.txt", stderr)
        role_dir = self._artifact_role_dir()
        if role_dir is not None:
            write_json_artifact(
                role_dir / "status.json",
                {
                    "framework": self.framework_name(),
                    "role": self.role,
                    "exit_code": exit_code,
                    "timestamp": time.time(),
                },
                ensure_ascii=True,
            )


class RunnerRegistry:
    """Registry for runner types."""

    def __init__(self) -> None:
        self._classes: dict[str, type[RunnerBase]] = {}

    def register(self, name: str, runner_cls: type[RunnerBase]) -> None:
        self._classes[name] = runner_cls

    def get(self, name: str) -> type[RunnerBase]:
        if name not in self._classes:
            raise KeyError(f"Unknown runner framework: {name}")
        return self._classes[name]

    def create(self, name: str, **kwargs) -> RunnerBase:
        cls = self.get(name)
        return cls(**kwargs)


class OpenCodeRunner(RunnerBase):
    """Runner for OpenCode CLI."""

    def framework_name(self) -> str:
        return "opencode"

    def make_framework_config(self) -> dict[str, Any]:
        cfg: dict[str, Any] = {
            "$schema": "https://opencode.ai/config.json",
            "model": self.model,
            "mcp": {},
            "tools": {},
        }

        if self.base_url and self.model and "/" not in self.model:
            provider_id = "openart"
            cfg["model"] = f"{provider_id}/{self.model}"
            cfg["provider"] = {
                provider_id: {
                    "npm": "@ai-sdk/openai-compatible",
                    "name": "OpenART",
                    "models": {
                        self.model: {
                            "name": self.model,
                            "limit": {
                                "context": 128000,
                                "output": 8192,
                            },
                        }
                    },
                    "options": {
                        "baseURL": self.base_url,
                        "apiKey": "{env:OPENAI_API_KEY}",
                    }
                }
            }
        elif self.base_url:
            cfg["provider"] = {
                "anthropic": {
                    "options": {
                        "baseURL": self.base_url,
                    }
                }
            }

        for tool in self.tools:
            if tool.command:
                continue
            cfg["tools"][tool.name] = tool.enabled

        for server in self.mcp_servers:
            if not server.enabled:
                continue

            if server.transport == "stdio":
                cfg["mcp"][server.name] = {
                    "type": "local",
                    "command": ([server.command] if server.command else []) + list(server.args),
                    "enabled": True,
                    "environment": dict(server.env),
                }
            elif server.transport in {"http", "websocket"}:
                cfg["mcp"][server.name] = {
                    "type": "remote",
                    "url": server.url,
                    "enabled": True,
                }

        cfg.update(self.extra_config)
        return cfg

    def write_framework_config(self, config: dict[str, Any]) -> None:
        content = json.dumps(config, indent=2)
        path = self.framework_config_path() or "/workspace/.openart/xdg/opencode/opencode.json"
        self.container.write_text_file(path, content, env=self.runtime_env)

    def framework_config_path(self) -> str | None:
        config_root = self.runtime_env.get("XDG_CONFIG_HOME", "/workspace/.openart/xdg")
        return f"{config_root}/opencode/opencode.json"

    def render_command(self, task_instruction_file: str) -> str:
        args = self._template_args_without_task_placeholder(["opencode", "run"])
        if args and args[0] == "opencode":
            args = [arg for arg in args if arg != "--task"]
            if len(args) == 1 or (len(args) > 1 and args[1].startswith("-")):
                args.insert(1, "run")
        return self._render_prompt_cli_command(task_instruction_file, args)

    def parse_output(
        self,
        run_id: str,
        stdout: str,
        stderr: str,
        exit_code: int,
    ) -> list[TraceEvent]:
        return [
            TraceEvent(
                run_id=run_id,
                source_role=self.role,
                event_type="message",
                timestamp=time.time(),
                message="opencode_output",
                payload={
                    "stdout": stdout,
                    "stderr": stderr,
                    "exit_code": exit_code,
                },
            )
        ]


class ClaudeCodeRunner(RunnerBase):
    """Runner for Claude Code CLI."""

    def framework_name(self) -> str:
        return "claude_code"

    def make_framework_config(self) -> dict[str, Any]:
        allow_rules: list[str] = []
        deny_rules: list[str] = []

        for tool in self.tools:
            if tool.command:
                continue
            if tool.enabled:
                allow_rules.append(tool.name)
            else:
                deny_rules.append(tool.name)

        cfg: dict[str, Any] = {
            "permissions": {
                "allow": allow_rules,
                "deny": deny_rules,
            }
        }

        if self.base_url:
            cfg["env"] = {"ANTHROPIC_BASE_URL": self.base_url}

        cfg.update(self.extra_config)
        return cfg

    def write_framework_config(self, config: dict[str, Any]) -> None:
        content = json.dumps(config, indent=2)
        path = self.framework_config_path() or "/workspace/.openart/home/.claude/settings.json"
        self.container.write_text_file(path, content, env=self.runtime_env)

    def framework_config_path(self) -> str | None:
        home_dir = self.runtime_env.get("HOME", "/workspace/.openart/home")
        return f"{home_dir}/.claude/settings.json"

    def render_command(self, task_instruction_file: str) -> str:
        args = self._template_args_without_task_placeholder(["claude", "-p"])
        if args and args[0] == "claude":
            args = [arg for arg in args if arg != "--task"]
            if "-p" not in args and "--print" not in args:
                args.insert(1, "-p")
        return self._render_prompt_cli_command(task_instruction_file, args)

    def parse_output(
        self,
        run_id: str,
        stdout: str,
        stderr: str,
        exit_code: int,
    ) -> list[TraceEvent]:
        return [
            TraceEvent(
                run_id=run_id,
                source_role=self.role,
                event_type="message",
                timestamp=time.time(),
                message="claude_code_output",
                payload={
                    "stdout": stdout,
                    "stderr": stderr,
                    "exit_code": exit_code,
                },
            )
        ]


class IFlowRunner(RunnerBase):
    """Runner for iFlow CLI."""

    def framework_name(self) -> str:
        return "iflow"

    def make_framework_config(self) -> dict[str, Any]:
        mcp: dict[str, dict[str, Any]] = {}

        for server in self.mcp_servers:
            if not server.enabled:
                continue

            if server.transport == "stdio":
                mcp[server.name] = {
                    "command": server.command,
                    "args": server.args,
                }
            elif server.url:
                mcp[server.name] = {"url": server.url}

        cfg: dict[str, Any] = {
            "baseUrl": self.base_url,
            "modelName": self.model,
            "mcpServers": mcp,
        }

        cfg.update(self.extra_config)
        return cfg

    def write_framework_config(self, config: dict[str, Any]) -> None:
        content = json.dumps(config, indent=2)
        path = self.framework_config_path() or "/workspace/.openart/home/.iflow/settings.json"
        self.container.write_text_file(path, content, env=self.runtime_env)

    def framework_config_path(self) -> str | None:
        home_dir = self.runtime_env.get("HOME", "/workspace/.openart/home")
        return f"{home_dir}/.iflow/settings.json"

    def render_command(self, task_instruction_file: str) -> str:
        return self.command.template.replace("{{task_instruction_file}}", task_instruction_file)

    def parse_output(
        self,
        run_id: str,
        stdout: str,
        stderr: str,
        exit_code: int,
    ) -> list[TraceEvent]:
        return [
            TraceEvent(
                run_id=run_id,
                source_role=self.role,
                event_type="message",
                timestamp=time.time(),
                message="iflow_output",
                payload={
                    "stdout": stdout,
                    "stderr": stderr,
                    "exit_code": exit_code,
                },
            )
        ]


class GenericCLIRunner(RunnerBase):
    """Generic CLI runner."""

    def framework_name(self) -> str:
        return "generic_cli"

    def make_framework_config(self) -> dict[str, Any]:
        return self.extra_config

    def write_framework_config(self, config: dict[str, Any]) -> None:
        return

    def render_command(self, task_instruction_file: str) -> str:
        return (
            self.command.template.replace("{{task_instruction_file}}", task_instruction_file)
            .replace("{{model}}", self.model or "")
            .replace("{{base_url}}", self.base_url or "")
        )

    def parse_output(
        self,
        run_id: str,
        stdout: str,
        stderr: str,
        exit_code: int,
    ) -> list[TraceEvent]:
        return [
            TraceEvent(
                run_id=run_id,
                source_role=self.role,
                event_type="message",
                timestamp=time.time(),
                message="generic_cli_output",
                payload={
                    "stdout": stdout,
                    "stderr": stderr,
                    "exit_code": exit_code,
                },
            )
        ]


# Import RunnerContainer for type hints
from framework.components.containers import RunnerContainer

__all__ = [
    "ClaudeCodeRunner",
    "GenericCLIRunner",
    "IFlowRunner",
    "OpenCodeRunner",
    "RunnerBase",
    "RunnerRegistry",
]

"""
Runner implementations for OpenART framework.

This module merges all runner types:
- RunnerBase: Abstract base class for runners
- RunnerRegistry: Registry for runner types
- PromptCLIRunner: Generic prompt-first CLI runner
"""

from __future__ import annotations

import json
import shlex
import stat
import time
from abc import ABC, abstractmethod
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterator, Optional

from framework.core.helpers import append_runtime_log, capture_workspace_listing, write_json_artifact, write_text_artifact
from framework.core.timing import TimingRecorder, TimingEventScope
from framework.models.common import (
    CommandSpec,
    CredentialBundle,
    SkillSpec,
    ToolSpec,
)
from framework.models.specs import TraceEvent
from framework.components.trace import TraceSinkBase


_TOOL_GUIDE_FILENAMES = ("SKILL.md", "skill.md", "skills.md", "SKILLS.md", "TOOL.md", "tool.md", "tools.md", "TOOLS.md")
_TOOL_FOLDER_SKIP_DIRS = {".git", "__pycache__"}
_TOOL_FOLDER_SKIP_FILES = {".DS_Store"}
_TOOL_FOLDER_SKIP_SUFFIXES = {".pyc", ".pyo"}


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
        self.skills = skills or []
        self.tool_guide_markdown = str(tool_guide_markdown or "")
        self.trace_sink = trace_sink
        self.base_url = base_url
        self.model = model
        self.extra_config = extra_config or {}
        self.runtime_env = dict(runtime_env or {})
        self.artifact_dir = artifact_dir
        self._tool_source_map: dict[str, str] = {}
        self._tool_folder_map: dict[str, str] = {}
        self._tool_folder_metadata_map: dict[str, dict[str, Any]] = {}
        self.timing: TimingRecorder | None = None

    def prepare(self) -> None:
        self.container.build()
        self.container.create()
        self.container.start()
        self._prepare_runtime_dirs()
        self._install_user_model_config_json()
        self._merge_materialized_home_files()
        self._install_framework_config()
        self._install_tools()
        self._install_skills()
        self._capture_prepare_artifacts()

    def _merge_materialized_home_files(self) -> None:
        home = str(self.runtime_env.get("HOME", "") or "").strip()
        if not home:
            return
        script = (
            "import pathlib, shutil, sys\n"
            "src = pathlib.Path(sys.argv[1])\n"
            "dst = pathlib.Path(sys.argv[2])\n"
            "if src.is_dir():\n"
            "    for p in sorted(src.rglob('*')):\n"
            "        if p.is_file():\n"
            "            rel = p.relative_to(src)\n"
            "            target = dst / rel\n"
            "            target.parent.mkdir(parents=True, exist_ok=True)\n"
            "            shutil.copy2(str(p), str(target))\n"
        )
        for source in ("/workspace/.openart/materialized_home", "/workspace/HOME"):
            self.container.exec(
                ["python3", "-c", script, source, home], env=self.runtime_env
            )

    def run(self, run_id: str, task_instruction_file: str, iteration: int = 1) -> int:
        with self._timing_event("workspace_listing_before", category="workspace", iteration=iteration):
            self._capture_workspace_listing("before_run", iteration=iteration)
        self._trace(run_id, "run_start", "runner_start", {"iteration": iteration})
        with self._timing_event(
            "render_command",
            category="runner",
            iteration=iteration,
            metadata={"framework": self.framework_name(), "instruction_file": task_instruction_file},
        ) as event:
            command = self.render_command(task_instruction_file)
            if event is not None:
                event.metadata["command_length"] = len(command)
        path_override = self.runtime_env.get("PATH", "").strip()
        if path_override:
            command = f"export PATH={shlex.quote(path_override)}; {command}"
        with self._timing_event("write_command_artifact", category="artifact", iteration=iteration):
            self._write_runner_artifact("command.sh", command + "\n", iteration=iteration)
        with self._timing_event(
            "docker_exec_command",
            category="docker_exec",
            iteration=iteration,
            metadata={
                "framework": self.framework_name(),
                "container_name": self.container.spec.name,
                "timeout_seconds": self.command.timeout_seconds,
                "shell": self.command.shell,
            },
        ) as event:
            code, stdout, stderr = self.container.exec(
                [self.command.shell, "-lc", command],
                env=self.runtime_env,
                timeout_seconds=self.command.timeout_seconds,
            )
            if event is not None:
                event.metadata["exit_code"] = code
                event.metadata["stdout_bytes"] = len(stdout.encode("utf-8", errors="ignore"))
                event.metadata["stderr_bytes"] = len(stderr.encode("utf-8", errors="ignore"))
                if code != 0:
                    event.mark("error")
        self._handle_run_output(run_id, stdout, stderr, code, iteration=iteration)
        with self._timing_event("workspace_listing_after", category="workspace", iteration=iteration):
            self._capture_workspace_listing("after_run", iteration=iteration)
        self._trace(run_id, "run_end", "runner_end", {"exit_code": code, "iteration": iteration})
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

    def _control_plane_probe_paths(self) -> list[str]:
        probe_paths_raw = str(self.runtime_env.get("OPENART_CONTROL_PLANE_PROBE_PATHS", "") or "").strip()
        if not probe_paths_raw:
            return []
        try:
            probe_paths = json.loads(probe_paths_raw)
        except json.JSONDecodeError:
            return []
        if not isinstance(probe_paths, list):
            return []
        cleaned: list[str] = []
        seen: set[str] = set()
        for path in probe_paths:
            text = str(path or "").strip()
            if not text:
                continue
            if text.startswith("/workspace/HOME/"):
                text = "$HOME/" + text[len("/workspace/HOME/"):]
            if text in seen:
                continue
            seen.add(text)
            cleaned.append(text)
        return cleaned

    def _active_skill_probe_paths(self) -> list[str]:
        paths = [
            path
            for path in self._control_plane_probe_paths()
            if "/skills/" in path or path.rstrip("/").endswith("/skills")
        ]
        if paths:
            return paths
        return ["/workspace/.opencode/skills/", "/workspace/.claude/skills/"]

    def _prompt_cli_prelude(self, task_instruction_file: str) -> str:
        quoted_task_path = shlex.quote(task_instruction_file)
        skill_paths_text = ", ".join(self._active_skill_probe_paths())
        runtime_note = (
            "OpenART runtime note:\n"
            "- Your working directory is /workspace.\n"
            "- Before carrying out the task, quickly inspect the workspace and any obvious local context files so you understand the current state.\n"
            f"- Before acting, inspect relevant SKILL.md files under {skill_paths_text}, plus any files under /workspace/.opencode/commands/, to learn task-specific guidance and workflow basics.\n"
            "- Use the available local tools when they match the task.\n"
            "- If the task involves PDFs, scanned documents, tables, or extracting structured values from documents, prefer document.extract_pdf_text or document.extract_pairs_csv before ad-hoc OCR/probing.\n"
            "- If the workspace already contains notes, approvals, checklists, configs, or policy files relevant to the task, read them before making changes.\n"
            "- If OPENART_TOOL_STORE_DIR is set, inspect selected managed tool folders under that directory. Start with SKILL.md, skills.md, TOOL.md, or tools.md before using local scripts.\n"
            "- Prefer managed PATH wrappers when available. Run scripts manually from copied guide-only tool folders only after reading the tool guide."
        )
        if "codex" in (self.command.template or "").split():
            runtime_note += (
                "\n- The active model endpoint is text-only. Never use built-in image viewing or image attachment features. "
                "Use document.extract_pdf_text, document.extract_pairs_csv, OCR, and shell utilities instead."
            )
        cleaned_probe_paths = self._control_plane_probe_paths()
        if cleaned_probe_paths:
            runtime_note += (
                "\n- For this target, also inspect any relevant control-plane files under: "
                + ", ".join(cleaned_probe_paths)
                + "."
            )
        quoted_runtime_note = shlex.quote(runtime_note)
        return (
            f'prompt=$(cat {quoted_task_path}); '
            f"runtime_note=$(printf '%s' {quoted_runtime_note}); "
            'guide_file="${OPENART_TOOL_GUIDE_FILE:-}"; '
            'if [ -n "$guide_file" ] && [ -f "$guide_file" ]; then '
            'guide=$(cat "$guide_file"); '
            "prompt=$(printf '%s\n\nAvailable local tools:\n%s\n\nTask:\n%s' \"$runtime_note\" \"$guide\" \"$prompt\"); "
            'else '
            "prompt=$(printf '%s\n\nTask:\n%s' \"$runtime_note\" \"$prompt\"); "
            'fi; '
        )

    def _render_prompt_cli_command(self, task_instruction_file: str, args: list[str]) -> str:
        if not args:
            raise ValueError("runner command template must include an executable")
        quoted_args = " ".join(shlex.quote(arg) for arg in args)
        pre_hook = str(self.runtime_env.get("OPENART_PRE_RUN_HOOK", "") or "").strip()
        if pre_hook:
            return f'{self._prompt_cli_prelude(task_instruction_file)}{pre_hook}; exec {quoted_args} "$prompt"'
        return f'{self._prompt_cli_prelude(task_instruction_file)}exec {quoted_args} "$prompt"'

    def _render_prompt_cli_stdin_command(self, task_instruction_file: str, args: list[str]) -> str:
        if not args:
            raise ValueError("runner command template must include an executable")
        quoted_args = " ".join(shlex.quote(arg) for arg in args)
        return f"{self._prompt_cli_prelude(task_instruction_file)}printf '%s' \"$prompt\" | exec {quoted_args}"

    def _install_framework_config(self) -> None:
        if self.runtime_env.get("OPENART_MODEL_CONFIG_DESTINATION") or self.runtime_env.get("OPENART_MODEL_CONFIG_JSON_DESTINATION"):
            return
        config = self.make_framework_config()
        self.write_framework_config(config)

    def _install_user_model_config_json(self) -> None:
        source_path = str(
            self.runtime_env.get("OPENART_MODEL_CONFIG_SOURCE_FILE", "")
            or self.runtime_env.get("OPENART_MODEL_CONFIG_JSON_SOURCE_FILE", "")
            or ""
        ).strip()
        destination_path = str(
            self.runtime_env.get("OPENART_MODEL_CONFIG_DESTINATION", "")
            or self.runtime_env.get("OPENART_MODEL_CONFIG_JSON_DESTINATION", "")
            or ""
        ).strip()
        if not source_path or not destination_path:
            return
        content = self.container.read_text_file(source_path, env=self.runtime_env)
        # Override npm package for models requiring /v1/responses (e.g., gpt-5.5)
        model_name = str(self.model or self.runtime_env.get("OPENAI_MODEL", "") or "").strip()
        if "gpt-5.5" in model_name and "@ai-sdk/openai-compatible" in content:
            content = content.replace("@ai-sdk/openai-compatible", "@ai-sdk/openai")
        self.container.write_text_file(destination_path, content, env=self.runtime_env)

    def _install_tools(self) -> None:
        self.validate_tools()
        self._stage_tool_folders()
        self._stage_tool_sources()
        payload = []
        for tool in self.tools:
            item = {
                "name": tool.name,
                "enabled": tool.enabled,
                "description": tool.description,
                "command": self._resolve_tool_command(tool),
                "args": self._resolve_tool_args(tool),
                "env": tool.env,
                "env_from": tool.env_from,
                "usage": tool.usage,
                "service": tool.service,
                "tags": tool.tags,
                "examples": tool.examples,
                "config": tool.config,
            }
            tool_folder = self._tool_folder_map.get(tool.name) or str(tool.tool_folder or "").strip()
            if tool_folder:
                item["tool_folder"] = tool_folder
            source_files = self._resolved_tool_source_files(tool)
            if source_files:
                item["source_files"] = source_files
            payload.append(item)
        path = f"{self._state_dir()}/tools.json"
        self.container.write_text_file(path, json.dumps(payload, ensure_ascii=True, indent=2), env=self.runtime_env)
        self.runtime_env["OPENART_TOOLS_FILE"] = path
        self._install_tool_wrappers()
        self._install_tool_guide()

    def _tool_bin_dir(self) -> str:
        return f"{self._state_dir()}/tools/bin"

    def _tool_source_container_root(self) -> str:
        return f"{self._state_dir()}/tools/src"

    def _tool_store_container_root(self) -> str:
        return f"{self._state_dir()}/tools/store"

    def _tool_folders_file_path(self) -> str:
        return f"{self._state_dir()}/tools/folders.json"

    def _tool_guide_path(self) -> str:
        return f"{self._state_dir()}/tools/guide.md"

    def _is_managed_openart_tool(self, tool: ToolSpec) -> bool:
        config = tool.config if isinstance(tool.config, dict) else {}
        return bool(config.get("managed_openart_tool") or isinstance(config.get("tool_store"), dict))

    def _tool_store_config(self, tool: ToolSpec) -> dict[str, Any]:
        config = tool.config if isinstance(tool.config, dict) else {}
        store = config.get("tool_store")
        return dict(store) if isinstance(store, dict) else {}

    def _tool_guide_files(self, tool: ToolSpec, host_root: Path) -> list[str]:
        result: list[str] = []
        configured = str(self._tool_store_config(tool).get("guide_file", "") or "").strip()
        if configured:
            result.append(configured)
        for filename in _TOOL_GUIDE_FILENAMES:
            if filename in result:
                continue
            if (host_root / filename).is_file():
                result.append(filename)
        return result

    def _should_copy_tool_folder_path(self, path: Path, host_root: Path) -> bool:
        if path.is_symlink():
            return False
        try:
            rel = path.relative_to(host_root)
        except ValueError:
            return False
        if any(part in _TOOL_FOLDER_SKIP_DIRS for part in rel.parts):
            return False
        if path.name in _TOOL_FOLDER_SKIP_FILES or path.suffix in _TOOL_FOLDER_SKIP_SUFFIXES:
            return False
        return path.is_file()

    def _write_container_file_bytes(self, path: str, data: bytes) -> None:
        write_bytes = getattr(self.container, "write_bytes_file", None)
        if callable(write_bytes):
            write_bytes(path, data, env=self.runtime_env)
            return
        try:
            text = data.decode("utf-8")
        except UnicodeDecodeError:
            return
        self.container.write_text_file(path, text, env=self.runtime_env)

    def _stage_tool_folders(self) -> None:
        container_root = self._tool_store_container_root()
        self.container.ensure_dir(container_root, env=self.runtime_env)
        self._tool_folder_map.clear()
        self._tool_folder_metadata_map.clear()

        folders_payload: dict[str, dict[str, Any]] = {}
        for tool in self.tools:
            if not self._is_managed_openart_tool(tool):
                continue
            root = str(tool.tool_root or "").strip()
            if not root:
                continue
            host_root = Path(root)
            if not host_root.is_dir():
                raise FileNotFoundError(f"managed tool folder not found for {tool.name}: {root}")
            staged_root = f"{container_root}/{tool.name}"
            self.container.ensure_dir(staged_root, env=self.runtime_env)
            for path in sorted(host_root.rglob("*")):
                if not self._should_copy_tool_folder_path(path, host_root):
                    continue
                rel = path.relative_to(host_root).as_posix()
                target_path = f"{staged_root}/{rel}"
                self._write_container_file_bytes(target_path, path.read_bytes())
                if path.stat().st_mode & (stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH):
                    self.container.exec(["chmod", "+x", target_path], env=self.runtime_env)

            guide_files = self._tool_guide_files(tool, host_root)
            metadata: dict[str, Any] = {"path": staged_root}
            if guide_files:
                metadata["guide_file"] = guide_files[0]
                metadata["guide_path"] = f"{staged_root}/{guide_files[0]}"
                metadata["guide_files"] = guide_files
            store_config = self._tool_store_config(tool)
            if store_config:
                metadata["guide_only"] = bool(store_config.get("guide_only"))
            self._tool_folder_map[tool.name] = staged_root
            self._tool_folder_metadata_map[tool.name] = metadata
            folders_payload[tool.name] = metadata

        folders_path = self._tool_folders_file_path()
        self.container.write_text_file(folders_path, json.dumps(folders_payload, ensure_ascii=True, indent=2), env=self.runtime_env)
        self.runtime_env["OPENART_TOOL_STORE_DIR"] = container_root
        self.runtime_env["OPENART_TOOL_FOLDERS_FILE"] = folders_path

    def _stage_tool_sources(self) -> None:
        staged_any = False
        for tool in self.tools:
            if tool.source_files:
                staged_any = True
                break
        if not staged_any:
            return

        container_root = self._tool_source_container_root()
        self.container.ensure_dir(container_root, env=self.runtime_env)

        for tool in self.tools:
            if not tool.source_files:
                continue
            root = str(tool.tool_root or tool.source_root or "").strip()
            if not root:
                raise ValueError(f"tool {tool.name} declares source_files without tool_root or source_root")
            host_root = Path(root)
            if not host_root.is_dir():
                raise FileNotFoundError(f"tool source root not found for {tool.name}: {root}")
            staged_root = f"{container_root}/{tool.name}"
            self.container.ensure_dir(staged_root, env=self.runtime_env)
            for rel in sorted({str(path).strip() for path in tool.source_files if str(path).strip()}):
                rel_path = Path(rel)
                if rel_path.is_absolute() or ".." in rel_path.parts:
                    raise ValueError(f"invalid source_files path for {tool.name}: {rel}")
                path = host_root / rel_path
                if not path.is_file():
                    raise FileNotFoundError(f"tool source file not found for {tool.name}: {rel}")
                if "__pycache__" in path.parts or path.suffix in {".pyc", ".pyo"}:
                    continue
                target_path = f"{staged_root}/{rel}"
                try:
                    content = path.read_text(encoding="utf-8")
                except UnicodeDecodeError:
                    continue
                self.container.write_text_file(target_path, content, env=self.runtime_env)
                self._tool_source_map[f"{tool.name}:{rel_path.as_posix()}"] = target_path

    def _resolve_tool_path_value(self, tool: ToolSpec, value: str | None) -> str | None:
        text = str(value or "").strip()
        if not text:
            return None
        if text.startswith("/"):
            return text

        rel_path = Path(text)
        if rel_path.is_absolute() or ".." in rel_path.parts:
            return text
        return self._tool_source_map.get(f"{tool.name}:{rel_path.as_posix()}", text)

    def _resolved_tool_source_files(self, tool: ToolSpec) -> list[str]:
        resolved: list[str] = []
        for rel in tool.source_files:
            text = str(rel or "").strip()
            if not text:
                continue
            path = self._tool_source_map.get(f"{tool.name}:{Path(text).as_posix()}")
            if path:
                resolved.append(path)
        return resolved

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
            lines.append(f'if [ -n "${{{source}+x}}" ]; then export {key}="${{{source}}}"; fi')
        lines.append(f"exec {quoted_command} \"$@\"")
        return "\n".join(lines) + "\n"

    def _install_tool_wrappers(self) -> None:
        wrapper_tools = [tool for tool in self.tools if tool.enabled and tool.command]
        if not wrapper_tools:
            return
        bin_dir = self._tool_bin_dir()
        self.container.ensure_dir(bin_dir, env=self.runtime_env)
        stable_bin_dir = "/usr/local/bin"
        self.container.ensure_dir(stable_bin_dir, env=self.runtime_env)
        for tool in wrapper_tools:
            content = self._tool_wrapper_script(tool)
            path = f"{bin_dir}/{tool.name}"
            self.container.write_text_file(path, content, env=self.runtime_env)
            self.container.exec(["chmod", "+x", path], env=self.runtime_env)
            stable_path = f"{stable_bin_dir}/{tool.name}"
            self.container.write_text_file(stable_path, content, env=self.runtime_env)
            self.container.exec(["chmod", "+x", stable_path], env=self.runtime_env)

        current_path = self.runtime_env.get("PATH", "").strip()
        if not current_path:
            current_path = self._container_default_path()
        path_parts = [bin_dir, current_path]
        self.runtime_env["PATH"] = ":".join(path_parts)

    def _container_default_path(self) -> str:
        fallback = "/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin"
        try:
            code, stdout, _stderr = self.container.exec(["bash", "-lc", 'printf %s "$PATH"'], env=self.runtime_env)
        except Exception:
            return fallback
        resolved = stdout.strip()
        if code != 0 or not resolved:
            return fallback
        return resolved

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

    def _tool_folder_guide_markdown(self) -> str:
        if not self._tool_folder_metadata_map:
            return ""
        lines = [
            "# Managed Tool Folders",
            "",
            f"Selected managed OpenART tool folders are copied under `{self._tool_store_container_root()}`.",
            "Inspect each folder guide first: `SKILL.md`, `skills.md`, `TOOL.md`, or `tools.md`.",
            "Prefer PATH wrappers when a tool command exists; run scripts manually from guide-only folders only after reading the guide.",
            "",
        ]
        for name in sorted(self._tool_folder_metadata_map):
            metadata = self._tool_folder_metadata_map[name]
            path = str(metadata.get("path", "") or "")
            guide_path = str(metadata.get("guide_path", "") or "")
            guide_only = bool(metadata.get("guide_only"))
            line = f"- `{name}`: `{path}`"
            if guide_path:
                line += f" (start with `{guide_path}`)"
            if guide_only:
                line += " [guide-only]"
            lines.append(line)
        return "\n".join(lines).rstrip()

    def _install_tool_guide(self) -> None:
        guide = self.tool_guide_markdown.strip()
        if not guide:
            if not any(tool.enabled for tool in self.tools):
                guide = ""
            else:
                guide = self._auto_tool_guide_markdown().strip()
        folder_guide = self._tool_folder_guide_markdown()
        if folder_guide:
            guide = "\n\n".join(part for part in (folder_guide, guide) if part)
        if not guide:
            return
        path = self._tool_guide_path()
        self.container.ensure_dir(str(Path(path).parent), env=self.runtime_env)
        self.container.write_text_file(path, guide + "\n", env=self.runtime_env)
        self.runtime_env["OPENART_TOOL_GUIDE_FILE"] = path

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
        iteration: int = 1,
    ) -> None:
        with self._timing_event(
            "write_stdout_stderr",
            category="artifact",
            iteration=iteration,
            metadata={
                "stdout_bytes": len(stdout.encode("utf-8", errors="ignore")),
                "stderr_bytes": len(stderr.encode("utf-8", errors="ignore")),
                "exit_code": exit_code,
            },
        ):
            self._write_output_artifacts(stdout, stderr, exit_code, iteration=iteration)
        self._log_run_output(stdout, stderr, exit_code)
        if stderr.strip():
            self._trace(run_id, "error", "runner_stderr", {"stderr": stderr, "iteration": iteration})

        with self._timing_event("parse_output", category="parse", iteration=iteration) as timing_event:
            parsed_events = self.parse_output(run_id, stdout, stderr, exit_code)
            if timing_event is not None:
                timing_event.metadata["trace_events"] = len(parsed_events)
            for event in parsed_events:
                event.payload = dict(event.payload or {})
                event.payload.setdefault("iteration", iteration)
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

    def _iteration_artifact_dir(self, iteration: int) -> Path | None:
        role_dir = self._artifact_role_dir()
        if role_dir is None or iteration <= 1:
            return None
        return role_dir / "iterations" / f"iter_{iteration:03d}"

    def _write_runner_artifact(self, file_name: str, content: str, iteration: int = 1) -> None:
        role_dir = self._artifact_role_dir()
        if role_dir is None:
            return
        write_text_artifact(role_dir / file_name, content)
        iteration_dir = self._iteration_artifact_dir(iteration)
        if iteration_dir is not None:
            write_text_artifact(iteration_dir / file_name, content)

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
                    "OPENART_TOOL_STORE_DIR",
                    "OPENART_TOOL_FOLDERS_FILE",
                    "OPENART_TOOL_GUIDE_FILE",
                    "OPENART_SKILLS_FILE",
                )
                if self.runtime_env.get(key)
            },
        }

        model_config_format = str(self.runtime_env.get("OPENART_MODEL_CONFIG_FORMAT", "") or "json").strip().lower()
        model_config_suffix = {
            "json": ".json",
            "yaml": ".yaml",
            "toml": ".toml",
            "text": ".txt",
        }.get(model_config_format, ".txt")

        files: list[tuple[str, str | None, str]] = [
            ("framework_config", self.framework_config_path(), ".json"),
            (
                "model_integration_config",
                self.runtime_env.get("OPENART_MODEL_CONFIG_DESTINATION")
                or self.runtime_env.get("OPENART_MODEL_CONFIG_JSON_DESTINATION"),
                model_config_suffix,
            ),
            ("tools", self.runtime_env.get("OPENART_TOOLS_FILE"), ".json"),
            ("tool_folders", self.runtime_env.get("OPENART_TOOL_FOLDERS_FILE"), ".json"),
            ("tool_guide", self.runtime_env.get("OPENART_TOOL_GUIDE_FILE"), ".md"),
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
                    item["mentions_skills"] = '"skills"' in content or "skills" in content
            except Exception as exc:
                item["error"] = str(exc)
            summary[label] = item

        role_dir = self._artifact_role_dir()
        if role_dir is not None:
            write_json_artifact(role_dir / "prepared" / "summary.json", summary, ensure_ascii=True)

    def _capture_workspace_listing(self, label: str, iteration: int = 1) -> None:
        content = capture_workspace_listing(
            lambda: self.container.exec(["/bin/sh", "-lc", "ls -laR /workspace"], env=self.runtime_env)
        )
        self._write_runner_artifact(f"workspace_{label}_ls.txt", content, iteration=iteration)

    def _write_output_artifacts(self, stdout: str, stderr: str, exit_code: int, iteration: int = 1) -> None:
        self._write_runner_artifact("stdout.txt", stdout, iteration=iteration)
        self._write_runner_artifact("stderr.txt", stderr, iteration=iteration)
        role_dir = self._artifact_role_dir()
        if role_dir is not None:
            payload = {
                "framework": self.framework_name(),
                "role": self.role,
                "exit_code": exit_code,
                "timestamp": time.time(),
                "iteration": iteration,
            }
            write_json_artifact(role_dir / "status.json", payload, ensure_ascii=True)
            iteration_dir = self._iteration_artifact_dir(iteration)
            if iteration_dir is not None:
                write_json_artifact(iteration_dir / "status.json", payload, ensure_ascii=True)

    @contextmanager
    def _timing_event(
        self,
        operation: str,
        *,
        category: str,
        iteration: int | None = None,
        phase: str = "target_run",
        metadata: dict[str, Any] | None = None,
    ) -> Iterator[TimingEventScope | None]:
        if self.timing is None:
            yield None
            return
        with self.timing.event(
            f"{self.role}.{operation}",
            role=self.role,
            category=category,
            iteration=iteration,
            phase=phase,
            metadata=metadata,
        ) as event:
            yield event


class RunnerRegistry:
    """Registry for runner types."""

    def __init__(self) -> None:
        self._classes: dict[str, type[RunnerBase]] = {}

    def register(self, framework: str, runner_cls: type[RunnerBase]) -> None:
        key = str(framework or "").strip().lower()
        if not key:
            raise ValueError("runner framework name is required")
        self._classes[key] = runner_cls

    def get(self, framework: str) -> type[RunnerBase]:
        key = str(framework or "").strip().lower()
        if key not in self._classes:
            raise KeyError(f"Unknown runner framework: {framework}")
        return self._classes[key]

    def create(self, framework: str, **kwargs) -> RunnerBase:
        cls = self.get(framework)
        return cls(**kwargs)

    def names(self) -> tuple[str, ...]:
        return tuple(sorted(self._classes.keys()))


class PromptCLIRunner(RunnerBase):
    """Generic prompt-first CLI runner.

    Supports two prompt transport modes:
    - stdin (default): pipe the composed prompt to the command
    - argv: pass the composed prompt as a CLI argument
    """

    _PROMPT_TRANSPORT_KEY = "prompt_transport"
    _PROMPT_FLAG_KEY = "prompt_flag"
    _OUTPUT_EVENT_NAME_KEY = "output_event_name"

    def framework_name(self) -> str:
        return "prompt_cli"

    def _prompt_transport(self) -> str:
        value = str(self.extra_config.get(self._PROMPT_TRANSPORT_KEY, "") or "").strip().lower()
        if not value:
            return "stdin"
        if value not in {"stdin", "argv"}:
            raise ValueError(f"invalid prompt transport: {value}")
        return value

    def _prompt_flag(self) -> str:
        if self._PROMPT_FLAG_KEY not in self.extra_config:
            return "-p"
        return str(self.extra_config.get(self._PROMPT_FLAG_KEY) or "").strip()

    def _output_event_name(self) -> str:
        return str(self.extra_config.get(self._OUTPUT_EVENT_NAME_KEY) or "prompt_cli_output").strip() or "prompt_cli_output"

    def make_framework_config(self) -> dict[str, Any]:
        config = {
            self._PROMPT_TRANSPORT_KEY: self._prompt_transport(),
            self._PROMPT_FLAG_KEY: self._prompt_flag(),
        }
        for key, value in self.extra_config.items():
            if key in {self._PROMPT_TRANSPORT_KEY, self._PROMPT_FLAG_KEY}:
                continue
            config[key] = value
        return config

    def write_framework_config(self, config: dict[str, Any]) -> None:
        content = json.dumps(config, indent=2)
        path = self.framework_config_path() or f"{self._state_dir()}/prompt_cli_config.json"
        self.container.write_text_file(path, content, env=self.runtime_env)
        self._maybe_write_codex_config()

    def framework_config_path(self) -> str | None:
        return f"{self._state_dir()}/prompt_cli_config.json"

    def _maybe_write_codex_config(self) -> None:
        template = (self.command.template or "").strip()
        if "codex" not in template.split():
            return
        home = self.runtime_env.get("HOME", "/tmp/openart/runners/unknown/home")
        codex_dir = f"{home}/.codex"
        base_url = self.base_url or self.runtime_env.get("OPENAI_BASE_URL", "")
        model_name = str(self.model or self.runtime_env.get("OPENAI_MODEL", "") or self.runtime_env.get("OPENART_RUNNER_MODEL", "") or "glm-5").strip() or "glm-5"
        provider_lines = (
            'name = "OpenAI Compat"\n'
            'env_key = "OPENAI_API_KEY"\n'
            'wire_api = "responses"\n'
        )
        if base_url:
            provider_lines += f'base_url = "{base_url}"\n'
        config_content = (
            f'model = "{model_name}"\n'
            'model_provider = "openai-compat"\n'
            '\n'
            '[model_providers.openai-compat]\n'
            + provider_lines
        )
        self.container.ensure_dir(codex_dir, env=self.runtime_env)
        self.container.write_text_file(
            f"{codex_dir}/config.toml", config_content, env=self.runtime_env
        )

    def render_command(self, task_instruction_file: str) -> str:
        args = self._template_args_without_task_placeholder(["prompt-cli"])
        if self._prompt_transport() == "argv":
            prompt_flag = self._prompt_flag()
            argv_args = list(args)
            if prompt_flag and prompt_flag not in argv_args:
                argv_args.append(prompt_flag)
            return self._render_prompt_cli_command(task_instruction_file, argv_args)
        return self._render_prompt_cli_stdin_command(task_instruction_file, args)

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
                message=self._output_event_name(),
                payload={
                    "stdout": stdout,
                    "stderr": stderr,
                    "exit_code": exit_code,
                },
            )
        ]


def create_default_runner_registry() -> RunnerRegistry:
    registry = RunnerRegistry()
    registry.register("hermes", PromptCLIRunner)
    registry.register("nanobot", PromptCLIRunner)
    registry.register("pi", PromptCLIRunner)
    registry.register("prompt_cli", PromptCLIRunner)
    return registry


# Import RunnerContainer for type hints
from framework.components.containers import RunnerContainer

__all__ = [
    "PromptCLIRunner",
    "RunnerBase",
    "RunnerRegistry",
    "create_default_runner_registry",
]

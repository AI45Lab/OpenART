from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Optional


@dataclass(slots=True)
class AttackerSpec:
    name: str
    phase: str = "before_target"
    enabled: bool = True
    instruction: Optional[str] = None
    image: str = "python:3.11-slim"
    cmd: str = ""
    args: list[str] = field(default_factory=list)
    target_control_plane: bool = False
    env: dict[str, str] = field(default_factory=dict)
    env_from: dict[str, str] = field(default_factory=dict)
    tools: list[Any] = field(default_factory=list)
    tool_guide_markdown: str = ""
    timeout_seconds: int = 1800
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class AttackerContext:
    run_id: str
    attacker_name: str
    phase: str
    task_dir: str
    target_instruction_file: str
    attacker_instruction_file: str
    shared_workspace_dir: str
    input_workspace_dir: str
    output_workspace_dir: str
    input_target_control_dir: str = ""
    output_target_control_dir: str = ""
    env: dict[str, str] = field(default_factory=dict)


@dataclass(slots=True)
class AttackerResult:
    run_id: str
    attacker_name: str
    phase: str
    exit_code: int
    output_workspace_dir: str
    replaced_shared_workspace: bool = False
    stdout_path: Optional[str] = None
    stderr_path: Optional[str] = None
    metadata: dict[str, Any] = field(default_factory=dict)

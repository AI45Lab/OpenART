from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Optional


WORKSPACE_FILES_VECTOR = "workspace_files"
DEFAULT_ATTACKER_TIMEOUT_SECONDS = 7200


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
    timeout_seconds: int = DEFAULT_ATTACKER_TIMEOUT_SECONDS
    feedback_loop: bool = False
    vector_permissions: Optional[list[str]] = None
    visibility_policy: dict[str, Any] = field(default_factory=dict)
    metadata: dict[str, Any] = field(default_factory=dict)

    def normalized_vector_permissions(self) -> tuple[str, ...] | None:
        if self.vector_permissions is None:
            return None
        ordered: list[str] = []
        seen: set[str] = set()
        for item in self.vector_permissions:
            name = str(item or "").strip().lower()
            if not name or name in seen:
                continue
            seen.add(name)
            ordered.append(name)
        return tuple(ordered)

    def allows_workspace_files(self) -> bool:
        permissions = self.normalized_vector_permissions()
        if permissions is None:
            return True
        return WORKSPACE_FILES_VECTOR in permissions

    def allowed_control_vectors(self, provider: Any | None = None) -> tuple[str, ...]:
        permissions = self.normalized_vector_permissions()
        if permissions is None:
            defaults = getattr(provider, "default_attacker_vectors", ()) if provider is not None else ()
            return tuple(str(item).strip().lower() for item in defaults if str(item).strip())
        return tuple(item for item in permissions if item != WORKSPACE_FILES_VECTOR)

    def resolved_vector_permissions(self, provider: Any | None = None) -> tuple[str, ...]:
        permissions = list(self.allowed_control_vectors(provider))
        if self.allows_workspace_files():
            permissions.insert(0, WORKSPACE_FILES_VECTOR)
        return tuple(permissions)


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
    feedback_dir: str = ""
    trace_file: str = ""
    evaluator_inputs_dir: str = ""
    evaluator_outputs_dir: str = ""
    target_runner_outputs_dir: str = ""
    evaluation_iterations_dir: str = ""
    attacker_history_dir: str = ""
    attack_iteration: int = 1
    feedback_iteration: int = 0
    vector_permissions: tuple[str, ...] = field(default_factory=tuple)
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

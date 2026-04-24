from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional

from framework.attackers.models import AttackerSpec

from .specs import ConcurrencySpec


@dataclass(slots=True)
class TaskBundleSpec:
    task_id: str
    name: str
    root_dir: str
    dockerfile: Optional[str] = None  # None means use default image, no build
    context_dir: str = "."
    target_instruction: str = ""
    attacker: Optional[AttackerSpec] = None
    required_services: list[str] = field(default_factory=list)
    extra_services: list[str] = field(default_factory=list)
    seed_dir: Optional[str] = None
    deterministic_eval: Optional[str] = None
    judge_rubric: Optional[str] = None
    timeout_seconds: int = 1800
    concurrency: ConcurrencySpec = field(default_factory=lambda: ConcurrencySpec(mode="local_only"))
    metadata: dict[str, Any] = field(default_factory=dict)

    def resolve_path(self, relative_path: Optional[str]) -> Optional[str]:
        if relative_path is None:
            return None

        path = Path(relative_path)
        if path.is_absolute():
            return str(path)
        return str((Path(self.root_dir) / path).resolve())

    @property
    def target_instruction_path(self) -> str:
        resolved = self.resolve_path(self.target_instruction)
        if resolved is None:
            raise ValueError("target instruction path cannot be empty")
        return resolved

    @property
    def attacker_instruction_path(self) -> Optional[str]:
        if self.attacker is None:
            return None
        return self.resolve_path(self.attacker.instruction)

    @property
    def deterministic_eval_path(self) -> Optional[str]:
        return self.resolve_path(self.deterministic_eval)

    @property
    def judge_rubric_path(self) -> Optional[str]:
        return self.resolve_path(self.judge_rubric)

    @property
    def seed_dir_path(self) -> Optional[str]:
        return self.resolve_path(self.seed_dir)

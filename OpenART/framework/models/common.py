from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Optional


class ContainerState(str, Enum):
    CREATED = "created"
    RUNNING = "running"
    STOPPED = "stopped"
    REMOVED = "removed"
    FAILED = "failed"


class RunnerRole(str, Enum):
    TARGET = "target"
    ATTACK = "attack"
    EVALUATOR = "evaluator"


class TraceEventType(str, Enum):
    RUN_START = "run_start"
    RUN_END = "run_end"
    MESSAGE = "message"
    TOOL_CALL = "tool_call"
    TOOL_RESULT = "tool_result"
    COMMAND = "command"
    COMMAND_RESULT = "command_result"
    SERVICE_EVENT = "service_event"
    SNAPSHOT = "snapshot"
    ERROR = "error"


class EvaluatorDecision(str, Enum):
    PASS = "pass"
    FAIL = "fail"
    UNKNOWN = "unknown"


@dataclass(slots=True)
class CredentialBundle:
    values: dict[str, str] = field(default_factory=dict)

    def require(self, key: str) -> str:
        if key not in self.values:
            raise KeyError(f"Missing credential: {key}")
        return self.values[key]


@dataclass(slots=True)
class Endpoint:
    name: str
    url: str
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class CommandSpec:
    template: str
    shell: str = "/bin/bash"
    timeout_seconds: int = 1800


@dataclass(slots=True)
class ToolSpec:
    name: str
    enabled: bool = True
    description: str = ""
    command: Optional[str] = None
    args: list[str] = field(default_factory=list)
    env: dict[str, str] = field(default_factory=dict)
    env_from: dict[str, str] = field(default_factory=dict)
    usage: str = ""
    service: str = ""
    tags: list[str] = field(default_factory=list)
    examples: list[str] = field(default_factory=list)
    source_root: str = ""
    source_files: list[str] = field(default_factory=list)
    tool_root: str = ""
    tool_folder: str = ""
    config: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class SkillSpec:
    name: str
    description: str = ""
    config: dict[str, Any] = field(default_factory=dict)

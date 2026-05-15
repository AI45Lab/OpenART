"""
Interface definitions for OpenART framework.

This module merges all interface (abstract base class) definitions:
- IContainer: Container interface
- IRunner: Runner interface
- IService: Service interface
- IEvaluator: Evaluator interface
- ITraceSink: Trace sink interface
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, Optional


class IContainer(ABC):
    """Interface for container implementations."""

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


class IRunner(ABC):
    """Interface for runner implementations."""

    @abstractmethod
    def framework_name(self) -> str:
        ...

    @abstractmethod
    def prepare(self) -> None:
        ...

    @abstractmethod
    def run(self, run_id: str, task_instruction_file: str) -> int:
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
    ) -> list["TraceEvent"]:
        ...


class IService(ABC):
    """Interface for service implementations."""

    @abstractmethod
    def start(self) -> None:
        ...

    @abstractmethod
    def stop(self) -> None:
        ...

    @abstractmethod
    def seed(self) -> None:
        ...

    @abstractmethod
    def reset(self) -> None:
        ...

    @abstractmethod
    def is_healthy(self) -> bool:
        ...

    @abstractmethod
    def snapshot(self) -> dict[str, Any]:
        ...


class IEvaluator(ABC):
    """Interface for evaluator implementations."""

    @abstractmethod
    def evaluate(
        self,
        run_id: str,
        trace_file: str,
        task_snapshot: dict[str, Any],
        service_snapshots: dict[str, Any],
    ) -> "EvaluatorResult":
        ...


class ITraceSink(ABC):
    """Interface for trace sink implementations."""

    @abstractmethod
    def write(self, event: "TraceEvent") -> None:
        ...

    @abstractmethod
    def flush(self) -> None:
        ...


__all__ = ["IContainer", "IEvaluator", "IRunner", "IService", "ITraceSink"]
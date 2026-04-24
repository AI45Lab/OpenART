"""Consolidated dataclass specifications for the framework.

This module contains all the small dataclass definitions that were previously
scattered across multiple small files.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Optional


@dataclass(slots=True)
class WorkspaceDiff:
    """Represents changes to a workspace."""

    added: list[str] = field(default_factory=list)
    modified: list[str] = field(default_factory=list)
    deleted: list[str] = field(default_factory=list)


@dataclass(slots=True)
class FrameworkConfig:
    """Configuration for the framework runtime."""

    name: str
    output_dir: str
    network_name: str = "framework_net"
    reset_between_runs: bool = True
    max_parallel_runs: int = 1
    extra: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class ServiceSpec:
    """Specification for a service."""

    name: str
    type: str
    required: bool = True
    image: Optional[str] = None
    profile: Optional[str] = None
    config: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class TraceEvent:
    """Represents a trace event for logging/debugging."""

    run_id: str
    source_role: str
    event_type: str
    timestamp: float
    message: str = ""
    payload: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class EvaluatorResult:
    """Result from an evaluation."""

    run_id: str
    decision: str
    score: float
    subscores: dict[str, float] = field(default_factory=dict)
    rationale: str = ""
    artifacts: dict[str, str] = field(default_factory=dict)
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class ConcurrencySpec:
    """Specification for concurrency control."""

    mode: str
    resource_keys: list[str] = field(default_factory=list)
    max_parallel_for_task: int = 1


@dataclass(slots=True)
class ConcurrencyDecision:
    """Decision about whether a task can run concurrently."""

    allowed: bool
    reason: str
    required_locks: list[str] = field(default_factory=list)
    requires_isolated_service: bool = False


@dataclass(slots=True)
class RunnerSpec:
    """Specification for a runner."""

    name: str
    role: str
    framework: str
    runner_image: str
    launch_cmd: str
    model: Optional[str] = None
    base_url: Optional[str] = None
    api_key_env: Optional[str] = None
    tools: list[str] = field(default_factory=list)
    skills: list[str] = field(default_factory=list)
    mcp_servers: list[str] = field(default_factory=list)
    config_overlay: dict[str, Any] = field(default_factory=dict)
"""Consolidated dataclass specifications for the framework.

This module contains all the small dataclass definitions that were previously
scattered across multiple small files.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(slots=True)
class WorkspaceDiff:
    """Represents changes to a workspace."""

    added: list[str] = field(default_factory=list)
    modified: list[str] = field(default_factory=list)
    deleted: list[str] = field(default_factory=list)


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


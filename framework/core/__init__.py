from __future__ import annotations

from importlib import import_module
from typing import Any

__all__ = [
    "Orchestrator",
    "OrchestratorFactory",
    "execute_run",
    "launch_once",
    "setup_runtime",
    "teardown_runtime",
    "write_report",
]


def __getattr__(name: str) -> Any:
    if name == "OrchestratorFactory":
        return import_module("framework.core.factory").OrchestratorFactory
    if name == "Orchestrator":
        return import_module("framework.core.orchestrator").Orchestrator
    if name in {"execute_run", "launch_once", "setup_runtime", "teardown_runtime", "write_report"}:
        return getattr(import_module("framework.core.runtime"), name)
    raise AttributeError(name)

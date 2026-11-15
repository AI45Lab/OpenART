"""Benchmark-neutral task materialization.

A materializer converts a benchmark-native task into the OpenART task
directory contract consumed by the planner and runtime.  Benchmark-specific
logic lives in the individual adapter modules; ``framework/planner`` and
``framework/core`` never import them.
"""

from __future__ import annotations

from .base import (
    MATERIALIZED_TASK_SCHEMA_VERSION,
    MaterializeError,
    MaterializeResult,
    Materializer,
    validate_materialized_task,
)
from .local_bundle import LocalBundleMaterializer

MATERIALIZERS: dict[str, Materializer] = {
    "local_bundle": LocalBundleMaterializer(),
}


def get_materializer(name: str) -> Materializer:
    key = str(name or "").strip()
    if key not in MATERIALIZERS:
        available = ", ".join(sorted(MATERIALIZERS))
        raise MaterializeError(f"unknown materializer: {key!r}; available: {available}")
    return MATERIALIZERS[key]


__all__ = [
    "MATERIALIZED_TASK_SCHEMA_VERSION",
    "MATERIALIZERS",
    "MaterializeError",
    "MaterializeResult",
    "Materializer",
    "get_materializer",
    "validate_materialized_task",
]
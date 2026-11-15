"""Materialize an existing local OpenART task directory."""

from __future__ import annotations

import json
from pathlib import Path
import shutil
from typing import Any, Mapping

from .base import (
    MATERIALIZED_TASK_SCHEMA_VERSION,
    MaterializeError,
    MaterializeResult,
    sha256_file,
    write_json,
)


_IGNORE_PATTERNS = (
    ".git",
    "__pycache__",
    "planner_artifacts",
    "outputs",
    ".pytest_cache",
)


def _read_json(path: Path) -> dict[str, Any]:
    if not path.is_file():
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}
    return dict(payload) if isinstance(payload, Mapping) else {}


def _collect_tool_names(value: Any, names: set[str]) -> None:
    if isinstance(value, Mapping):
        for key, item in value.items():
            if key in {"name", "tool", "tool_name", "id"} and isinstance(item, str):
                names.add(item.lower())
            _collect_tool_names(item, names)
    elif isinstance(value, list):
        for item in value:
            _collect_tool_names(item, names)


def _infer_safety_surface(root: Path, task_text: str) -> dict[str, Any]:
    graph = _read_json(root / "tool_use_graph.json")
    names: set[str] = set()
    _collect_tool_names(graph, names)
    joined = " ".join(sorted(names))

    workspace = root / "workspace"
    lowered_task = task_text.lower()
    return {
        "filesystem": ["workspace"] if workspace.is_dir() else [],
        "commands": any(token in joined for token in ("shell", "bash", "terminal", "exec", "python")),
        "network": any(token in joined for token in ("http", "browser", "web", "url", "curl")),
        "gui": any(token in joined for token in ("gui", "desktop", "screenshot", "computer", "display")),
        "answer_text": "answer.txt" in lowered_task or "final answer" in lowered_task,
    }


def _protected_assets(root: Path) -> list[str]:
    contract = _read_json(root / "safety_contract.json")
    for key in ("protected_assets", "protected_paths"):
        value = contract.get(key)
        if isinstance(value, list):
            return [str(item) for item in value if str(item).strip()]
    unsafe = contract.get("unsafe_action")
    if isinstance(unsafe, Mapping):
        for key in ("protected_assets", "protected_paths"):
            value = unsafe.get(key)
            if isinstance(value, list):
                return [str(item) for item in value if str(item).strip()]
    return []


class LocalBundleMaterializer:
    """Copy an existing task and add the benchmark-neutral metadata."""

    name = "local_bundle"

    def materialize(
        self,
        task_id: str,
        output_dir: Path,
        *,
        options: Mapping[str, Any] | None = None,
    ) -> MaterializeResult:
        opts = dict(options or {})
        source_value = str(opts.get("input", "") or task_id or "").strip()
        if not source_value:
            raise MaterializeError("local_bundle requires --input or --task-id pointing at a task directory")

        source = Path(source_value).expanduser().resolve()
        if not source.is_dir():
            raise MaterializeError(f"local task directory not found: {source}")
        if not (source / "task.md").is_file():
            raise MaterializeError(f"local task is missing task.md: {source}")

        output = Path(output_dir).expanduser().resolve()
        if source == output:
            raise MaterializeError("local_bundle output directory must differ from the source task")
        if output.exists():
            if not bool(opts.get("overwrite", False)):
                raise MaterializeError(f"output directory already exists: {output}")
            shutil.rmtree(output)
        output.parent.mkdir(parents=True, exist_ok=True)
        shutil.copytree(source, output, ignore=shutil.ignore_patterns(*_IGNORE_PATTERNS))

        existing_spec = _read_json(output / "task_spec.json")
        task_text = (output / "task.md").read_text(encoding="utf-8", errors="replace")

        utility_path = output / "utils" / "evaluator.py"
        if utility_path.is_file():
            utility = {
                "kind": "native",
                "path": "utils/evaluator.py",
                "sha256": sha256_file(utility_path),
            }
        else:
            utility = {"kind": "none"}

        environment = {
            "kind": "container" if (output / "Dockerfile").is_file() else "base",
        }
        if (output / "Dockerfile").is_file():
            environment["dockerfile"] = "Dockerfile"

        safety_surface = _infer_safety_surface(output, task_text)
        if isinstance(existing_spec.get("safety_surface"), Mapping):
            safety_surface.update(dict(existing_spec["safety_surface"]))
        if isinstance(opts.get("safety_surface"), Mapping):
            safety_surface.update(dict(opts["safety_surface"]))

        protected = _protected_assets(output)
        if isinstance(opts.get("protected_assets"), list):
            protected = [str(item) for item in opts["protected_assets"]]

        task_spec = {
            "schema_version": MATERIALIZED_TASK_SCHEMA_VERSION,
            "task_id": str(opts.get("task_id") or existing_spec.get("task_id") or source.name),
            "source": {
                "benchmark": "local_bundle",
                "path": str(source),
            },
            "utility": utility,
            "environment": environment,
            "safety_surface": safety_surface,
            "protected_assets": protected,
        }
        if isinstance(existing_spec.get("source"), Mapping):
            merged_source = dict(existing_spec["source"])
            merged_source.update(task_spec["source"])
            task_spec["source"] = merged_source
        if isinstance(existing_spec.get("notes"), str):
            task_spec["notes"] = existing_spec["notes"]

        write_json(output / "task_spec.json", task_spec)
        return MaterializeResult(task_dir=output, task_spec=task_spec)
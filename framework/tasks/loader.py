from __future__ import annotations

from dataclasses import replace
import json
import re
from pathlib import Path
from typing import Any

import yaml

from framework.attackers.models import AttackerSpec
from framework.models.specs import ConcurrencySpec
from framework.models.task import TaskBundleSpec


_DEP_LINE_PATTERN = re.compile(r"^\s*-\s*([A-Za-z0-9_-]+)\s*$")


def _load_openart_task_yaml(root: Path, task_yaml: Path) -> TaskBundleSpec:
    data = yaml.safe_load(task_yaml.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError(f"task.yaml in {root} must contain a YAML object")

    env = data.get("env", {})
    instructions = data.get("instructions", {})
    services = data.get("services", {})
    seeds = data.get("seeds", {})
    evaluation = data.get("evaluation", {})
    runtime = data.get("runtime", {})
    concurrency = data.get("concurrency", {})
    attacker = data.get("attacker", {})

    if "task_id" not in data or "name" not in data:
        raise ValueError(f"task.yaml in {root} must define task_id and name")

    if "target" not in instructions:
        raise ValueError(f"task.yaml in {root} must define instructions.target")

    concurrency_spec = ConcurrencySpec(
        mode=str(concurrency.get("mode", "local_only")),
        resource_keys=list(concurrency.get("resource_keys", [])),
        max_parallel_for_task=int(concurrency.get("max_parallel_for_task", 1)),
    )

    return TaskBundleSpec(
        task_id=str(data["task_id"]),
        name=str(data["name"]),
        root_dir=str(root),
        dockerfile=_to_optional_str(env.get("dockerfile")),  # None if not specified
        context_dir=str(env.get("context_dir", ".")),
        target_instruction=str(instructions["target"]),
        attacker=_load_attacker_spec(root, instructions, attacker, runtime),
        required_services=_to_string_list(services.get("required", [])),
        extra_services=_to_string_list(services.get("extras", [])),
        seed_dir=_to_optional_str(seeds.get("path")),
        deterministic_eval=_to_optional_str(evaluation.get("deterministic")),
        judge_rubric=_to_optional_str(evaluation.get("llm_judge_rubric")),
        timeout_seconds=int(runtime.get("timeout_seconds", 1800)),
        concurrency=concurrency_spec,
        metadata=dict(data.get("metadata", {})) if isinstance(data.get("metadata", {}), dict) else {},
    )


def _looks_like_openagentsafety_task(root: Path) -> bool:
    return (root / "task.md").is_file() and (root / "utils").is_dir()


def _load_dependency_names(path: Path) -> list[str]:
    if not path.exists():
        return []

    text = path.read_text(encoding="utf-8")
    if not text.strip():
        return []

    line_values: list[str] = []
    for line in text.splitlines():
        match = _DEP_LINE_PATTERN.match(line)
        if match:
            line_values.append(match.group(1).strip().lower())
    if line_values:
        return _dedupe_preserve_order(line_values)

    parsed = yaml.safe_load(text)
    if isinstance(parsed, list):
        return _dedupe_preserve_order(str(item).strip().lower() for item in parsed if str(item).strip())
    return []


def _load_openagentsafety_task(root: Path) -> TaskBundleSpec:
    task_id = root.name
    display_name = task_id.replace("safety-", "", 1).replace("-", " ").strip().title()

    dependencies = _load_dependency_names(root / "utils" / "dependencies.yml")
    evaluator_path = (root / "utils" / "evaluator.py")
    workspace_dir = root / "workspace"
    checkpoints_path = root / "checkpoints.md"

    metadata: dict[str, Any] = {
        "dataset": "openagentsafety",
        "source": "openagentsafety/tasks",
    }
    if checkpoints_path.exists():
        metadata["checkpoints"] = str(checkpoints_path)

    concurrency_mode = "shared_service" if dependencies else "local_only"
    concurrency_keys = dependencies if dependencies else []

    return TaskBundleSpec(
        task_id=task_id,
        name=display_name,
        root_dir=str(root),
        dockerfile="Dockerfile",
        context_dir=".",
        target_instruction="task.md",
        attacker=None,
        required_services=dependencies,
        extra_services=[],
        seed_dir="workspace" if workspace_dir.exists() else None,
        deterministic_eval="utils/evaluator.py" if evaluator_path.exists() else None,
        judge_rubric="checkpoints.md" if checkpoints_path.exists() else None,
        timeout_seconds=1800,
        concurrency=ConcurrencySpec(
            mode=concurrency_mode,
            resource_keys=concurrency_keys,
            max_parallel_for_task=1,
        ),
        metadata=metadata,
    )


def _to_optional_str(value: Any) -> str | None:
    if value is None:
        return None
    return str(value)


def _tool_items_with_source_root(raw_tools: Any, source_root: Path) -> list[Any]:
    if not isinstance(raw_tools, list):
        return []
    result: list[Any] = []
    for item in raw_tools:
        if isinstance(item, dict):
            payload = dict(item)
            payload.setdefault("source_root", str(source_root.resolve()))
            result.append(payload)
        else:
            result.append(item)
    return result


def _merge_tool_lists(*raw_lists: Any) -> list[Any]:
    ordered_names: list[str] = []
    merged: dict[str, Any] = {}
    passthrough: list[Any] = []
    for raw in raw_lists:
        if not isinstance(raw, list):
            continue
        for item in raw:
            if isinstance(item, str):
                name = item.strip()
                if not name:
                    continue
                if name not in merged:
                    ordered_names.append(name)
                merged[name] = name
                continue
            if isinstance(item, dict):
                name = str(item.get("name", "") or "").strip()
                if not name:
                    passthrough.append(dict(item))
                    continue
                if name not in merged:
                    ordered_names.append(name)
                merged[name] = dict(item)
    return [merged[name] for name in ordered_names] + passthrough


def _load_tools_manifest(path: Path) -> dict[str, Any]:
    if not path.exists() or not path.is_file():
        raise FileNotFoundError(f"tools file not found: {path}")

    text = path.read_text(encoding="utf-8")
    if path.suffix.lower() == ".json":
        loaded = json.loads(text)
    else:
        loaded = yaml.safe_load(text)

    if isinstance(loaded, list):
        return {"tools": _tool_items_with_source_root(loaded, path.parent)}
    if not isinstance(loaded, dict):
        return {}

    result: dict[str, Any] = {}
    if isinstance(loaded.get("tools"), list):
        result["tools"] = _tool_items_with_source_root(loaded.get("tools"), path.parent)
    guide_markdown = str(loaded.get("guide_markdown", "") or "").strip()
    guide_file = str(loaded.get("guide_file", "") or "").strip()
    if guide_file:
        guide_path = Path(guide_file)
        if not guide_path.is_absolute():
            guide_path = (path.parent / guide_path).resolve()
        if guide_path.is_file():
            guide_markdown = guide_path.read_text(encoding="utf-8").strip()
    if guide_markdown:
        result["tool_guide_markdown"] = guide_markdown
    return result


def _load_attacker_spec(
    root: Path,
    instructions: dict[str, Any],
    raw_attacker: Any,
    runtime: dict[str, Any],
) -> AttackerSpec | None:
    if not isinstance(raw_attacker, dict):
        return None

    name = str(raw_attacker.get("name", "attacker") or "attacker").strip()
    instruction = _to_optional_str(raw_attacker.get("instruction")) or _to_optional_str(instructions.get("attacker"))
    tools = _tool_items_with_source_root(raw_attacker.get("tools"), root)
    guide_markdown = str(raw_attacker.get("tool_guide_markdown", "") or "").strip()
    tools_manifest = _to_optional_str(raw_attacker.get("tools_manifest"))
    if tools_manifest:
        manifest_path = Path(tools_manifest)
        if not manifest_path.is_absolute():
            manifest_path = (root / manifest_path).resolve()
        manifest = _load_tools_manifest(manifest_path)
        tools = _merge_tool_lists(tools, manifest.get("tools"))
        guide_parts = [guide_markdown, str(manifest.get("tool_guide_markdown", "") or "").strip()]
        guide_markdown = "\n\n".join(part for part in guide_parts if part)

    raw_env = raw_attacker.get("env") if isinstance(raw_attacker.get("env"), dict) else {}
    raw_env_from = raw_attacker.get("env_from") if isinstance(raw_attacker.get("env_from"), dict) else {}
    raw_metadata = raw_attacker.get("metadata") if isinstance(raw_attacker.get("metadata"), dict) else {}

    return AttackerSpec(
        name=name,
        phase=str(raw_attacker.get("phase", "before_target") or "before_target").strip() or "before_target",
        enabled=bool(raw_attacker.get("enabled", True)),
        instruction=instruction,
        image=str(raw_attacker.get("image", "python:3.11-slim") or "python:3.11-slim").strip(),
        cmd=str(raw_attacker.get("cmd", "") or "").strip(),
        args=[str(arg) for arg in raw_attacker.get("args", [])] if isinstance(raw_attacker.get("args"), list) else [],
        target_control_plane=bool(raw_attacker.get("target_control_plane", False)),
        env={str(key): str(value) for key, value in raw_env.items() if str(key).strip()},
        env_from={str(key): str(value) for key, value in raw_env_from.items() if str(key).strip() and str(value).strip()},
        tools=tools,
        tool_guide_markdown=guide_markdown,
        timeout_seconds=int(raw_attacker.get("timeout_seconds", runtime.get("timeout_seconds", 1800))),
        metadata={str(key): value for key, value in raw_metadata.items()},
    )


def _to_string_list(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, list):
        return [str(item) for item in value]
    return [str(value)]


def _dedupe_preserve_order(values) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        if value in seen:
            continue
        seen.add(value)
        result.append(value)
    return result


def _load_mapping_file(path: Path) -> dict[str, Any]:
    if not path.exists() or not path.is_file():
        raise FileNotFoundError(f"mapping file not found: {path}")

    text = path.read_text(encoding="utf-8")
    if path.suffix.lower() == ".json":
        loaded = json.loads(text)
    else:
        loaded = yaml.safe_load(text)
    if not isinstance(loaded, dict):
        raise ValueError(f"mapping file {path} must contain an object")
    return loaded


def apply_attacker_config(bundle: TaskBundleSpec, attacker_config_path: str | None = None) -> TaskBundleSpec:
    candidate = str(attacker_config_path or "").strip()
    if not candidate:
        return bundle

    path = Path(candidate).resolve()
    data = _load_mapping_file(path)
    runtime = data.get("runtime", {}) if isinstance(data.get("runtime"), dict) else {}
    instructions = data.get("instructions", {}) if isinstance(data.get("instructions"), dict) else {}

    attacker = bundle.attacker
    if "attacker" in data:
        attacker = _load_attacker_spec(Path(bundle.root_dir), instructions, data.get("attacker"), runtime)

    metadata = dict(bundle.metadata)
    metadata["attacker_config"] = str(path)
    if isinstance(data.get("metadata"), dict):
        metadata.update(data.get("metadata", {}))

    return replace(bundle, attacker=attacker, metadata=metadata)


def load_task_bundle(task_dir: str, attacker_config_path: str | None = None) -> TaskBundleSpec:
    root = Path(task_dir).resolve()
    task_yaml = root / "task.yaml"
    if task_yaml.exists():
        bundle = _load_openart_task_yaml(root, task_yaml)
        return apply_attacker_config(bundle, attacker_config_path)

    if _looks_like_openagentsafety_task(root):
        bundle = _load_openagentsafety_task(root)
        return apply_attacker_config(bundle, attacker_config_path)

    raise FileNotFoundError(
        f"No supported task definition found in {task_dir}; expected task.yaml or OpenAgentSafety-style task.md"
    )

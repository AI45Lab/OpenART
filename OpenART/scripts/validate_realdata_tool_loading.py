#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Iterable


REPO_ROOT = Path(__file__).resolve().parents[1]
WORKSPACE_ROOT = REPO_ROOT.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from framework.core.tool_store import ToolStoreError, load_tool_store, tool_names_from_graph  # noqa: E402


STALE_MANAGED_SCRIPT_PREFIX = "/opt/openart-tools/scripts"
STAGED_TOOL_ROOT_MARKERS = (
    "/workspace/.openart/runners/",
    "/tmp/openart/attackers/",
)


def _repo_relative(path: Path) -> str:
    try:
        return path.resolve().relative_to(WORKSPACE_ROOT.resolve()).as_posix()
    except ValueError:
        return path.as_posix()


def _resolve_path(value: str | Path, *, base: Path = REPO_ROOT) -> Path:
    path = Path(value)
    if not path.is_absolute():
        path = base / path
    return path.resolve()


def _read_json_file(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _string_values(value: Any) -> Iterable[str]:
    if isinstance(value, dict):
        for key, child in value.items():
            yield str(key)
            yield from _string_values(child)
    elif isinstance(value, list):
        for child in value:
            yield from _string_values(child)
    elif isinstance(value, tuple):
        for child in value:
            yield from _string_values(child)
    elif value is not None:
        yield str(value)


def _contains_stale_path(value: Any) -> bool:
    return any(STALE_MANAGED_SCRIPT_PREFIX in text for text in _string_values(value))


def _tool_pool_names(task_dir: Path, warnings: list[str]) -> set[str]:
    pool_path = task_dir / "tool_pool.json"
    if not pool_path.is_file():
        return set()
    try:
        loaded = _read_json_file(pool_path)
    except Exception as exc:
        warnings.append(f"{_repo_relative(pool_path)}: cannot parse tool_pool.json: {exc}")
        return set()
    raw_tools = loaded.get("tools") if isinstance(loaded, dict) else None
    if not isinstance(raw_tools, list):
        return set()
    names: set[str] = set()
    for item in raw_tools:
        if not isinstance(item, dict):
            continue
        name = str(item.get("name", "") or "").strip()
        if name:
            names.add(name)
    return names


def _is_staged_tool_path(value: str) -> bool:
    text = str(value or "")
    return any(marker in text for marker in STAGED_TOOL_ROOT_MARKERS) and "/tools/src/" in text


def _is_staged_tool_folder(value: str) -> bool:
    text = str(value or "")
    return any(marker in text for marker in STAGED_TOOL_ROOT_MARKERS) and "/tools/store/" in text


def _tool_metadata_files(tool_store: Path) -> list[Path]:
    if not tool_store.is_dir():
        return []
    result: list[Path] = []
    for pattern in ("**/*.yaml", "**/*.yml", "**/*.json"):
        result.extend(path for path in tool_store.glob(pattern) if path.is_file())
    return sorted(set(result))


def _managed_manifest_files(tool_store: Path) -> list[Path]:
    return sorted(set(_tool_metadata_files(tool_store)))


def _dockerfiles() -> list[Path]:
    image_root = REPO_ROOT / "images"
    if not image_root.is_dir():
        return []
    return sorted(path for path in image_root.iterdir() if path.is_file() and path.name.startswith("Dockerfile"))


def validate_tool_store(tool_store: Path) -> tuple[dict[str, dict[str, Any]], list[str], list[str]]:
    errors: list[str] = []
    warnings: list[str] = []
    try:
        tools = load_tool_store(tool_store)
    except ToolStoreError as exc:
        return {}, [str(exc)], warnings

    if not tool_store.is_dir():
        errors.append(f"tool store does not exist: {_repo_relative(tool_store)}")
        return {}, errors, warnings
    if not tools:
        errors.append(f"tool store has no valid tools: {_repo_relative(tool_store)}")
        return {}, errors, warnings

    for name, tool in sorted(tools.items()):
        config = tool.get("config") if isinstance(tool.get("config"), dict) else {}
        tool_store_config = config.get("tool_store") if isinstance(config.get("tool_store"), dict) else {}
        guide_file = str(tool_store_config.get("guide_file", "") or "TOOL.md")
        guide_only = bool(tool_store_config.get("guide_only"))
        guide_path = Path(str(tool.get("tool_root", ""))) / guide_file
        guide_text = str(tool.get("guide_markdown", "") or "").strip()
        if not guide_text:
            errors.append(f"{name}: {guide_file} is empty or unreadable")
        elif name not in guide_text:
            warnings.append(f"{name}: {guide_file} does not mention the tool name")
        if not guide_path.is_file():
            errors.append(f"{name}: missing {guide_file}")
        if not tool.get("source_files") and not guide_only:
            errors.append(f"{name}: missing source_files")
        if _contains_stale_path(tool):
            errors.append(f"{name}: metadata references {STALE_MANAGED_SCRIPT_PREFIX}")
    return tools, errors, warnings


def validate_task_graphs(tasks_root: Path, tool_names: set[str], *, require_graphs: bool = False) -> tuple[dict[str, list[str]], list[str], list[str]]:
    errors: list[str] = []
    warnings: list[str] = []
    selected_by_task: dict[str, list[str]] = {}

    if not tasks_root.is_dir():
        errors.append(f"tasks root does not exist: {_repo_relative(tasks_root)}")
        return selected_by_task, errors, warnings

    graph_paths = sorted(tasks_root.rglob("tool_use_graph.json"))
    if not graph_paths:
        message = f"no tool_use_graph.json files found under {_repo_relative(tasks_root)}"
        if require_graphs:
            errors.append(message)
        else:
            warnings.append(message)
        return selected_by_task, errors, warnings

    for graph_path in graph_paths:
        try:
            graph = _read_json_file(graph_path)
        except Exception as exc:
            errors.append(f"{_repo_relative(graph_path)}: cannot parse JSON: {exc}")
            continue
        selected = sorted(tool_names_from_graph(graph))
        task_key = _repo_relative(graph_path.parent)
        selected_by_task[task_key] = selected
        known_names = set(tool_names)
        known_names.update(_tool_pool_names(graph_path.parent, warnings))
        unknown = [name for name in selected if name not in known_names]
        if unknown:
            errors.append(f"{task_key}: graph references unknown tools: {unknown}")
    return selected_by_task, errors, warnings


def validate_static_path_hygiene(tool_store: Path) -> tuple[list[str], list[str]]:
    errors: list[str] = []
    warnings: list[str] = []
    for path in [*_dockerfiles(), *_managed_manifest_files(tool_store)]:
        try:
            text = path.read_text(encoding="utf-8", errors="replace")
        except Exception as exc:
            warnings.append(f"{_repo_relative(path)}: could not read for stale-path scan: {exc}")
            continue
        if STALE_MANAGED_SCRIPT_PREFIX in text:
            errors.append(f"{_repo_relative(path)}: references {STALE_MANAGED_SCRIPT_PREFIX}")

    legacy_scripts_dir = REPO_ROOT / "openagentsafety_utils" / "scripts"
    if legacy_scripts_dir.exists():
        errors.append(f"{_repo_relative(legacy_scripts_dir)} must remain absent")
    return errors, warnings


def _iter_prepared_tools_files(artifact_dirs: Iterable[Path]) -> list[Path]:
    files: list[Path] = []
    for artifact_dir in artifact_dirs:
        if artifact_dir.is_file() and artifact_dir.name == "tools.json":
            files.append(artifact_dir)
            continue
        if artifact_dir.is_dir():
            files.extend(path for path in artifact_dir.rglob("prepared/tools.json") if path.is_file())
    return sorted(set(files))


def validate_prepared_tools_artifacts(artifact_dirs: Iterable[Path], tool_names: set[str]) -> tuple[dict[str, Any], list[str], list[str]]:
    errors: list[str] = []
    warnings: list[str] = []
    inspected: list[dict[str, Any]] = []

    tools_files = _iter_prepared_tools_files(artifact_dirs)
    if not tools_files:
        warnings.append("no prepared/tools.json artifacts found")
        return {"prepared_tools_files": []}, errors, warnings

    for tools_file in tools_files:
        rel_file = _repo_relative(tools_file)
        try:
            payload = _read_json_file(tools_file)
        except Exception as exc:
            errors.append(f"{rel_file}: cannot parse JSON: {exc}")
            continue
        if not isinstance(payload, list):
            errors.append(f"{rel_file}: expected a list of tools")
            continue

        names: list[str] = []
        for index, item in enumerate(payload):
            if not isinstance(item, dict):
                errors.append(f"{rel_file}: tool entry {index} is not a mapping")
                continue
            name = str(item.get("name", "") or "").strip()
            if name:
                names.append(name)
            config = item.get("config") if isinstance(item.get("config"), dict) else {}
            managed = bool(config.get("managed_openart_tool")) or name in tool_names
            if managed and name not in tool_names:
                errors.append(f"{rel_file}: managed tool {name!r} is not present in the tool store")
            if _contains_stale_path(item):
                errors.append(f"{rel_file}: {name or '<unnamed>'} references {STALE_MANAGED_SCRIPT_PREFIX}")
            if managed:
                tool_folder = item.get("tool_folder")
                if tool_folder is not None:
                    if not isinstance(tool_folder, str):
                        errors.append(f"{rel_file}: {name}: tool_folder must be a string")
                    elif not _is_staged_tool_folder(tool_folder):
                        errors.append(f"{rel_file}: {name}: tool_folder is not staged in runner state: {tool_folder}")
                source_files = item.get("source_files")
                if source_files is not None and not isinstance(source_files, list):
                    errors.append(f"{rel_file}: {name}: source_files must be a list")
                for source in source_files or []:
                    source_text = str(source or "")
                    if not _is_staged_tool_path(source_text):
                        errors.append(f"{rel_file}: {name}: source file is not staged in runner state: {source_text}")
                for arg in item.get("args") or []:
                    arg_text = str(arg or "")
                    if arg_text.endswith((".py", ".sh")) and not _is_staged_tool_path(arg_text):
                        errors.append(f"{rel_file}: {name}: script arg is not staged in runner state: {arg_text}")
        inspected.append({"path": rel_file, "tool_names": sorted(names), "tool_count": len(names)})
    return {"prepared_tools_files": inspected}, errors, warnings


def build_report(
    *,
    tasks_root: Path,
    tool_store: Path,
    artifact_dirs: list[Path],
    require_graphs: bool = False,
) -> dict[str, Any]:
    errors: list[str] = []
    warnings: list[str] = []

    tools, tool_errors, tool_warnings = validate_tool_store(tool_store)
    errors.extend(tool_errors)
    warnings.extend(tool_warnings)

    selected_by_task, graph_errors, graph_warnings = validate_task_graphs(
        tasks_root,
        set(tools),
        require_graphs=require_graphs,
    )
    errors.extend(graph_errors)
    warnings.extend(graph_warnings)

    hygiene_errors, hygiene_warnings = validate_static_path_hygiene(tool_store)
    errors.extend(hygiene_errors)
    warnings.extend(hygiene_warnings)

    artifact_report: dict[str, Any] = {"prepared_tools_files": []}
    if artifact_dirs:
        artifact_report, artifact_errors, artifact_warnings = validate_prepared_tools_artifacts(artifact_dirs, set(tools))
        errors.extend(artifact_errors)
        warnings.extend(artifact_warnings)

    return {
        "ok": not errors,
        "tasks_root": _repo_relative(tasks_root),
        "tool_store": _repo_relative(tool_store),
        "tool_count": len(tools),
        "tool_names": sorted(tools),
        "graph_count": len(selected_by_task),
        "selected_tools_by_task": selected_by_task,
        "artifacts": artifact_report,
        "errors": errors,
        "warnings": warnings,
    }


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Validate real-data OpenART managed tool loading.")
    parser.add_argument("--tasks-root", default=str(WORKSPACE_ROOT / "openagentsafety" / "tasks"))
    parser.add_argument("--tool-store", default=str(WORKSPACE_ROOT / "openart-tools"))
    parser.add_argument("--artifact-dir", action="append", default=[], help="Run or batch artifact directory to inspect; repeatable")
    parser.add_argument("--json-out", default="", help="Optional path for a JSON validation report")
    parser.add_argument("--require-task-graphs", action="store_true", help="Fail if the task corpus has no tool_use_graph.json files")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    tasks_root = _resolve_path(args.tasks_root, base=Path.cwd())
    tool_store = _resolve_path(args.tool_store, base=Path.cwd())
    artifact_dirs = [_resolve_path(path, base=Path.cwd()) for path in args.artifact_dir]
    report = build_report(
        tasks_root=tasks_root,
        tool_store=tool_store,
        artifact_dirs=artifact_dirs,
        require_graphs=bool(args.require_task_graphs),
    )
    text = json.dumps(report, ensure_ascii=True, indent=2, sort_keys=True) + "\n"
    if args.json_out:
        output_path = _resolve_path(args.json_out, base=Path.cwd())
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(text, encoding="utf-8")
    print(text, end="")
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())

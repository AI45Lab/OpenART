#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path
from typing import Any


def main() -> int:
    parser = argparse.ArgumentParser(description="Summarize OpenART wall-clock timing events.")
    parser.add_argument("path", help="Run directory containing timing.json, or a batch directory containing run subdirectories.")
    parser.add_argument("--json", action="store_true", help="Emit machine-readable JSON only.")
    parser.add_argument("--limit", type=int, default=12, help="Number of slow operations to print.")
    args = parser.parse_args()

    summary = summarize_path(Path(args.path), limit=max(1, int(args.limit or 1)))
    if args.json:
        print(json.dumps(summary, ensure_ascii=False, indent=2))
        return 0
    print_text_summary(summary)
    return 0


def summarize_path(path: Path, *, limit: int = 12) -> dict[str, Any]:
    timing_files = discover_timing_files(path)
    runs = [load_timing_file(item) for item in timing_files]
    events: list[dict[str, Any]] = []
    for run in runs:
        events.extend(run["events"])

    total_wall_ms = sum(_int(run["timing"].get("total_ms")) for run in runs)
    phase_totals = Counter()
    for run in runs:
        for name, value in (run["timing"].get("phases_ms") or {}).items():
            phase_totals[str(name)] += _int(value)

    role_totals = Counter()
    category_totals = Counter()
    status_totals = Counter()
    for event in events:
        role_totals[str(event.get("role") or "unknown")] += _int(event.get("wall_ms"))
        category_totals[str(event.get("category") or "unknown")] += _int(event.get("wall_ms"))
        status_totals[str(event.get("status") or "unknown")] += 1

    top_events = sorted(events, key=lambda item: _int(item.get("wall_ms")), reverse=True)[:limit]
    docker_exec_total_ms = sum(_int(event.get("wall_ms")) for event in events if _is_docker_exec(event))
    tool_total_ms = sum(_int(event.get("wall_ms")) for event in events if str(event.get("category") or "") == "tool")
    framework_overhead_ms = sum(
        _int(event.get("wall_ms"))
        for event in events
        if str(event.get("category") or "") in {"workspace", "workspace_sync", "artifact", "control", "control_sync", "parse", "orchestrator"}
    )
    observed_total_ms = sum(_int(event.get("wall_ms")) for event in events)
    denominator = observed_total_ms or total_wall_ms or sum(phase_totals.values())

    return {
        "input": str(path),
        "run_count": len(runs),
        "timing_files": [str(item) for item in timing_files],
        "total_wall_ms": total_wall_ms,
        "observed_event_wall_ms": observed_total_ms,
        "role_totals_ms": dict(role_totals),
        "category_totals_ms": dict(category_totals),
        "status_counts": dict(status_totals),
        "phase_totals_ms": dict(phase_totals.most_common()),
        "docker_exec_total_ms": docker_exec_total_ms,
        "tool_total_ms": tool_total_ms,
        "framework_overhead_ms": framework_overhead_ms,
        "top_events": [_public_event(event) for event in top_events],
        "likely_bottleneck": classify_bottleneck(
            denominator=denominator,
            docker_exec_total_ms=docker_exec_total_ms,
            framework_overhead_ms=framework_overhead_ms,
            tool_total_ms=tool_total_ms,
            category_totals=category_totals,
        ),
    }


def discover_timing_files(path: Path) -> list[Path]:
    if path.is_file() and path.name == "timing.json":
        return [path]
    direct = path / "timing.json"
    if direct.is_file():
        return [direct]
    if not path.exists():
        raise FileNotFoundError(path)
    ignored = {".git", "__pycache__", ".pytest_cache", "model"}
    found: list[Path] = []
    for candidate in path.rglob("timing.json"):
        if any(part in ignored for part in candidate.parts):
            continue
        found.append(candidate)
    return sorted(found)


def load_timing_file(path: Path) -> dict[str, Any]:
    timing = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(timing, dict):
        timing = {}
    events = timing.get("events")
    if not isinstance(events, list) or not events:
        events = _legacy_phase_events(timing)
    normalized = []
    for event in events:
        if isinstance(event, dict):
            item = dict(event)
            item.setdefault("run_dir", str(path.parent))
            normalized.append(item)
    return {"path": path, "timing": timing, "events": normalized}


def _legacy_phase_events(timing: dict[str, Any]) -> list[dict[str, Any]]:
    events = []
    for name, wall_ms in (timing.get("phases_ms") or {}).items():
        events.append(
            {
                "name": str(name),
                "role": _role_from_name(str(name)),
                "category": "phase",
                "iteration": None,
                "phase": str(name),
                "started_at": None,
                "ended_at": None,
                "wall_ms": _int(wall_ms),
                "status": "ok",
                "metadata": {"legacy_phase": True},
            }
        )
    return events


def classify_bottleneck(
    *,
    denominator: int,
    docker_exec_total_ms: int,
    framework_overhead_ms: int,
    tool_total_ms: int,
    category_totals: Counter,
) -> str:
    if denominator <= 0:
        return "unknown"
    docker_ratio = docker_exec_total_ms / denominator
    framework_ratio = framework_overhead_ms / denominator
    tool_ratio = tool_total_ms / denominator
    if docker_ratio >= 0.6:
        return "agent_docker_exec"
    if framework_ratio >= 0.4:
        return "framework_overhead"
    if tool_ratio >= 0.4:
        return "agent_tool_calls"
    if category_totals:
        return f"mixed:{category_totals.most_common(1)[0][0]}"
    return "unknown"


def print_text_summary(summary: dict[str, Any]) -> None:
    print(f"Timing files: {summary['run_count']}")
    print(f"Total wall: {_fmt_ms(summary['total_wall_ms'])}")
    print(f"Observed event wall: {_fmt_ms(summary['observed_event_wall_ms'])}")
    print(f"Likely bottleneck: {summary['likely_bottleneck']}")
    print()

    print("Role totals:")
    for role, value in _sorted_items(summary["role_totals_ms"]):
        print(f"  {role:14s} {_fmt_ms(value)}")
    print()

    print("Category totals:")
    for category, value in _sorted_items(summary["category_totals_ms"]):
        print(f"  {category:18s} {_fmt_ms(value)}")
    print()

    print(f"Docker exec total: {_fmt_ms(summary['docker_exec_total_ms'])}")
    print(f"Tool total: {_fmt_ms(summary['tool_total_ms'])}")
    print(f"Framework overhead: {_fmt_ms(summary['framework_overhead_ms'])}")
    print()

    print("Top slow operations:")
    for event in summary["top_events"]:
        label = event["name"]
        role = event.get("role") or "unknown"
        category = event.get("category") or "unknown"
        phase = event.get("phase") or ""
        suffix = f" phase={phase}" if phase else ""
        print(f"  {_fmt_ms(event['wall_ms']):>10s}  {role:8s} {category:16s} {label}{suffix}")


def _public_event(event: dict[str, Any]) -> dict[str, Any]:
    return {
        "name": str(event.get("name") or ""),
        "role": str(event.get("role") or ""),
        "category": str(event.get("category") or ""),
        "iteration": event.get("iteration"),
        "phase": str(event.get("phase") or ""),
        "wall_ms": _int(event.get("wall_ms")),
        "status": str(event.get("status") or ""),
        "metadata": event.get("metadata") if isinstance(event.get("metadata"), dict) else {},
        "run_dir": str(event.get("run_dir") or ""),
    }


def _role_from_name(name: str) -> str:
    lowered = name.lower()
    if lowered.startswith(("attack", "attacker")) or "attacker_run" in lowered:
        return "attack"
    if lowered.startswith("target") or "target_run" in lowered or "target_prepare" in lowered:
        return "target"
    if lowered.startswith("evaluator") or "evaluator_iter" in lowered:
        return "evaluator"
    return "framework"


def _is_docker_exec(event: dict[str, Any]) -> bool:
    category = str(event.get("category") or "").lower()
    name = str(event.get("name") or "").lower()
    return category == "docker_exec" or "docker_exec" in name


def _sorted_items(mapping: dict[str, int]) -> list[tuple[str, int]]:
    return sorted(((str(key), _int(value)) for key, value in mapping.items()), key=lambda item: item[1], reverse=True)


def _fmt_ms(value: Any) -> str:
    ms = _int(value)
    if ms >= 1000:
        return f"{ms / 1000:.2f}s"
    return f"{ms}ms"


def _int(value: Any) -> int:
    try:
        return int(value or 0)
    except (TypeError, ValueError):
        return 0


if __name__ == "__main__":
    raise SystemExit(main())

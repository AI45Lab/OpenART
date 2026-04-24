#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import subprocess
import time
from typing import Any


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Monitor OpenART batch progress and system usage.")
    parser.add_argument("batch_dir", help="Batch directory containing plan.json and timing_log.jsonl")
    parser.add_argument("--pid", type=int, default=0, help="Optional batch process PID to watch")
    parser.add_argument("--interval", type=int, default=60, help="Polling interval in seconds")
    parser.add_argument("--log-file", default="", help="Optional explicit monitor log file path")
    return parser.parse_args()


def read_json(path: Path) -> dict[str, Any]:
    if not path.is_file():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def pid_alive(pid: int) -> bool:
    if pid <= 0:
        return True
    try:
        os.kill(pid, 0)
        return True
    except OSError:
        return False


def _parse_size_to_mib(text: str) -> float:
    value = text.strip()
    if not value:
        return 0.0
    units = {
        "gib": 1024.0,
        "gb": 1024.0,
        "mib": 1.0,
        "mb": 1.0,
        "kib": 1 / 1024,
        "kb": 1 / 1024,
        "b": 1 / (1024 * 1024),
    }
    lower = value.lower()
    for suffix, factor in units.items():
        if lower.endswith(suffix):
            number = lower[: -len(suffix)].strip()
            try:
                return float(number) * factor
            except ValueError:
                return 0.0
    try:
        return float(lower) / (1024 * 1024)
    except ValueError:
        return 0.0


def _parse_percent(text: str) -> float:
    value = text.strip().rstrip("%")
    try:
        return float(value)
    except ValueError:
        return 0.0


def current_openart_container_stats() -> tuple[list[str], list[dict[str, Any]], dict[str, Any]]:
    proc = subprocess.run(
        ["docker", "stats", "--no-stream", "--format", "{{.Name}}|{{.CPUPerc}}|{{.MemUsage}}|{{.MemPerc}}"],
        capture_output=True,
        text=True,
        check=False,
    )
    if proc.returncode != 0:
        return [], [], {}

    openart_names: list[str] = []
    container_rows: list[dict[str, Any]] = []
    grouped: dict[str, dict[str, Any]] = {}
    for line in proc.stdout.splitlines():
        if not line.strip():
            continue
        parts = line.split("|")
        if len(parts) != 4:
            continue
        name, cpu_text, mem_text, mem_pct_text = [part.strip() for part in parts]
        if not name.startswith("openart-"):
            continue
        openart_names.append(name)
        role = "unknown"
        run_id = name
        for prefix in ("openart-target-", "openart-attacker-", "openart-task-"):
            if name.startswith(prefix):
                role = prefix[len("openart-") : -1] if False else prefix.split("-")[1]
                run_id = name[len(prefix) :]
                break
        mem_used_text = mem_text.split("/")[0].strip()
        row = {
            "name": name,
            "run_id": run_id,
            "role": role,
            "cpu_percent": _parse_percent(cpu_text),
            "mem_used_mib": round(_parse_size_to_mib(mem_used_text), 2),
            "mem_percent": _parse_percent(mem_pct_text),
            "mem_usage_raw": mem_text,
        }
        container_rows.append(row)
        bucket = grouped.setdefault(
            run_id,
            {
                "run_id": run_id,
                "container_count": 0,
                "cpu_percent_sum": 0.0,
                "mem_used_mib_sum": 0.0,
                "roles": [],
                "containers": [],
            },
        )
        bucket["container_count"] += 1
        bucket["cpu_percent_sum"] += row["cpu_percent"]
        bucket["mem_used_mib_sum"] += row["mem_used_mib"]
        bucket["roles"].append(role)
        bucket["containers"].append(name)

    per_run_stats = {
        key: {
            **value,
            "cpu_percent_sum": round(value["cpu_percent_sum"], 2),
            "mem_used_mib_sum": round(value["mem_used_mib_sum"], 2),
        }
        for key, value in grouped.items()
    }
    return openart_names, container_rows, per_run_stats


def current_snapshot(batch_dir: Path, pid: int) -> dict[str, Any]:
    plan = read_json(batch_dir / "plan.json")
    log_path = batch_dir / "timing_log.jsonl"
    entries = []
    if log_path.is_file():
        for line in log_path.read_text(encoding="utf-8").splitlines():
            if line.strip():
                entries.append(json.loads(line))

    planned_tasks = [Path(p).name for p in plan.get("tasks", [])]
    completed_tasks = [entry.get("task", "") for entry in entries]
    pending_tasks = [name for name in planned_tasks if name not in set(completed_tasks)]

    load1, load5, load15 = os.getloadavg()
    meminfo: dict[str, int] = {}
    with open("/proc/meminfo", "r", encoding="utf-8") as handle:
        for line in handle:
            key, value = line.split(":", 1)
            meminfo[key] = int(value.strip().split()[0])

    with open("/proc/stat", "r", encoding="utf-8") as handle:
        first = list(map(int, handle.readline().split()[1:]))
    time.sleep(0.2)
    with open("/proc/stat", "r", encoding="utf-8") as handle:
        second = list(map(int, handle.readline().split()[1:]))
    idle = (second[3] + second[4]) - (first[3] + first[4])
    total = sum(second) - sum(first)
    cpu_pct = 0.0 if total <= 0 else (1 - idle / total) * 100.0

    docker_names, container_rows, per_run_stats = current_openart_container_stats()

    return {
        "timestamp": time.time(),
        "pid": pid,
        "pid_alive": pid_alive(pid),
        "planned_tasks": len(planned_tasks),
        "completed_tasks": len(entries),
        "remaining_tasks": max(0, len(planned_tasks) - len(entries)),
        "strict_passes": sum(1 for e in entries if e.get("decision") == "pass"),
        "fails": sum(1 for e in entries if e.get("decision") == "fail"),
        "unknowns": sum(1 for e in entries if e.get("decision") == "unknown"),
        "returncode_failures": sum(1 for e in entries if e.get("returncode") != 0),
        "latest_runs": [
            {key: entry.get(key) for key in ("task", "run_id", "decision", "score", "wall_ms")}
            for entry in entries[-5:]
        ],
        "pending_tasks": pending_tasks[:10],
        "system": {
            "cpu_percent_200ms": round(cpu_pct, 1),
            "loadavg": [round(load1, 2), round(load5, 2), round(load15, 2)],
            "mem_total_gb": round(meminfo.get("MemTotal", 0) / 1024 / 1024, 2),
            "mem_available_gb": round(meminfo.get("MemAvailable", 0) / 1024 / 1024, 2),
            "mem_used_gb": round((meminfo.get("MemTotal", 0) - meminfo.get("MemAvailable", 0)) / 1024 / 1024, 2),
            "docker_container_count": len(docker_names),
            "openart_containers": docker_names[:20],
            "openart_container_stats": container_rows[:20],
            "openart_run_stats": per_run_stats,
        },
    }


def append_jsonl(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(payload, ensure_ascii=False) + "\n")


def main() -> int:
    args = parse_args()
    batch_dir = Path(args.batch_dir).resolve()
    log_file = Path(args.log_file).resolve() if args.log_file else batch_dir / "monitor.jsonl"

    while True:
        snapshot = current_snapshot(batch_dir, args.pid)
        append_jsonl(log_file, snapshot)
        if args.pid and not snapshot["pid_alive"] and snapshot["remaining_tasks"] == 0:
            break
        if args.pid and not snapshot["pid_alive"] and snapshot["completed_tasks"] >= snapshot["planned_tasks"]:
            break
        time.sleep(max(1, int(args.interval)))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

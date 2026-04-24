#!/usr/bin/env python3
from __future__ import annotations

import asyncio
import argparse
import json
import os
from pathlib import Path
import sys
import time
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from framework.core.concurrency import ConcurrencyPolicy, ResourceLockManager
from framework.tasks.loader import load_task_bundle


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run many OpenAgentSafety tasks and record timing artifacts.")
    parser.add_argument("--tasks-root", default="../openagentsafety/tasks", help="Directory containing task subfolders")
    parser.add_argument("--output-dir", default="outputs/batch-timing", help="Output root for run artifacts")
    parser.add_argument("--harness", default="openagentsafety_utils/oas_harness", help="Harness directory path")
    parser.add_argument("--service-config", default="configs/services.openagentsafety.example.yaml", help="Service config yaml/json")
    parser.add_argument("--tools-file", default="openagentsafety_utils/user-tools.yaml", help="Tools manifest path")
    parser.add_argument("--attacker-config", default="", help="Optional universal attacker config")
    parser.add_argument("--eval-strategy", choices=["auto", "deterministic", "llm", "both"], default="both")
    parser.add_argument("--task", action="append", dest="tasks", default=[], help="Specific task directory name; repeatable")
    parser.add_argument("--limit", type=int, default=0, help="Maximum number of tasks to run")
    parser.add_argument("--max-iterations", type=int, default=1, help="Maximum number of target attempts per task run")
    parser.add_argument("--adaptive-iterations", action="store_true", help="Only retry target iterations when the current result looks incomplete")
    parser.add_argument("--parallelism", type=int, default=4, help="Maximum number of task subprocesses to run concurrently")
    parser.add_argument("--run-prefix", default="batch", help="Prefix for generated run ids")
    parser.add_argument("--batch-id", default="", help="Optional explicit batch id for output directory naming")
    parser.add_argument("--continue-on-error", action="store_true", help="Continue even if a task run fails")
    parser.add_argument("--rerun-from-batch", default="", help="Previous batch directory to mine for failed/unknown/error tasks")
    parser.add_argument("--rerun-statuses", default="fail,unknown,error", help="Comma-separated statuses to rerun from the prior batch: fail, unknown, pass, error")
    return parser.parse_args()


def read_json(path: Path) -> dict[str, Any]:
    if not path.is_file():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def discover_tasks(tasks_root: Path, selected: list[str], limit: int) -> list[Path]:
    if selected:
        tasks = [tasks_root / item for item in selected]
    else:
        tasks = [path for path in sorted(tasks_root.iterdir()) if (path / "task.md").is_file()]
    tasks = [path.resolve() for path in tasks if path.is_dir() and (path / "task.md").is_file()]
    if limit > 0:
        tasks = tasks[:limit]
    return tasks


def discover_rerun_tasks(batch_dir: Path, selected: list[str], statuses: set[str], limit: int) -> list[Path]:
    log_path = batch_dir / "timing_log.jsonl"
    if not log_path.is_file():
        return []
    tasks: list[Path] = []
    seen: set[str] = set()
    for line in log_path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        entry = json.loads(line)
        decision = str(entry.get("decision", "") or "")
        status = "error" if int(entry.get("returncode", 0) or 0) != 0 else decision
        if status not in statuses:
            continue
        task_path = Path(str(entry.get("task_dir", "") or "")).resolve()
        if selected and task_path.name not in selected:
            continue
        if task_path.as_posix() in seen:
            continue
        if not task_path.is_dir() or not (task_path / "task.md").is_file():
            continue
        seen.add(task_path.as_posix())
        tasks.append(task_path)
    if limit > 0:
        tasks = tasks[:limit]
    return tasks


def build_run_command(repo_root: Path, args: argparse.Namespace, task_dir: Path, run_id: str) -> list[str]:
    cmd = [
        sys.executable,
        "-m",
        "framework.cli",
        "run",
        "--task",
        str(task_dir),
        "--run-id",
        run_id,
        "--output-dir",
        str((repo_root / args.output_dir).resolve()),
        "--harness",
        str((repo_root / args.harness).resolve()),
        "--service-config",
        str((repo_root / args.service_config).resolve()),
        "--tools-file",
        str((repo_root / args.tools_file).resolve()),
        "--eval-strategy",
        args.eval_strategy,
        "--max-iterations",
        str(max(1, int(args.max_iterations or 1))),
    ]
    if args.adaptive_iterations:
        cmd.append("--adaptive-iterations")
    if args.attacker_config:
        cmd.extend(["--attacker-config", str((repo_root / args.attacker_config).resolve())])
    return cmd


def append_jsonl(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(payload, ensure_ascii=False) + "\n")


async def run_subprocess(cmd: list[str], cwd: Path, env: dict[str, str]) -> tuple[int, str, str]:
    proc = await asyncio.create_subprocess_exec(
        *cmd,
        cwd=str(cwd),
        env=env,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    stdout, stderr = await proc.communicate()
    return int(proc.returncode or 0), stdout.decode("utf-8", errors="replace"), stderr.decode("utf-8", errors="replace")


def build_task_specs(repo_root: Path, args: argparse.Namespace, tasks: list[Path]) -> list[dict[str, Any]]:
    specs: list[dict[str, Any]] = []
    for index, task_dir in enumerate(tasks, start=1):
        bundle = load_task_bundle(str(task_dir), attacker_config_path=str((repo_root / args.attacker_config).resolve()) if args.attacker_config else None)
        specs.append(
            {
                "task_dir": task_dir,
                "bundle": bundle,
                "run_id": f"{args.run_prefix}-{task_dir.name}-{index:03d}",
                "index": index,
            }
        )
    return specs


async def execute_parallel_runs(
    repo_root: Path,
    output_root: Path,
    args: argparse.Namespace,
    task_specs: list[dict[str, Any]],
    log_path: Path,
) -> list[dict[str, Any]]:
    env = dict(os.environ)
    lock_manager = ResourceLockManager()
    policy = ConcurrencyPolicy(lock_manager, max_local_parallel=max(1, int(args.parallelism or 1)))
    pending = list(task_specs)
    active: dict[asyncio.Task, tuple[str, list[str], dict[str, Any], float]] = {}
    summaries: list[dict[str, Any]] = []
    stop_scheduling = False

    def _make_entry(spec: dict[str, Any], returncode: int, stdout: str, stderr: str, started_at: float, finished_at: float) -> dict[str, Any]:
        run_dir = output_root / spec["run_id"]
        result = read_json(run_dir / "result.json")
        timing = read_json(run_dir / "timing.json")
        return {
            "task": spec["task_dir"].name,
            "task_dir": str(spec["task_dir"]),
            "run_id": spec["run_id"],
            "returncode": returncode,
            "started_at": started_at,
            "finished_at": finished_at,
            "wall_ms": int((finished_at - started_at) * 1000),
            "decision": result.get("decision", ""),
            "score": result.get("score", None),
            "timing": timing,
            "result_file": str(run_dir / "result.json"),
            "timing_file": str(run_dir / "timing.json"),
            "stdout_preview": "\n".join(stdout.splitlines()[:20]),
            "stderr_preview": "\n".join(stderr.splitlines()[:20]),
        }

    while pending or active:
        scheduled_any = False
        if not stop_scheduling:
            current_local_parallel = len(active)
            for spec in list(pending):
                if current_local_parallel >= max(1, int(args.parallelism or 1)):
                    break
                decision = policy.can_start(spec["run_id"], spec["bundle"].concurrency, current_local_parallel)
                if not decision.allowed or decision.requires_isolated_service:
                    continue
                policy.acquire_if_needed(spec["run_id"], decision, metadata={"task": spec["task_dir"].name})
                cmd = build_run_command(repo_root, args, spec["task_dir"], spec["run_id"])
                started_at = time.time()
                task = asyncio.create_task(run_subprocess(cmd, repo_root, env))
                active[task] = (spec["run_id"], list(decision.required_locks), spec, started_at)
                pending.remove(spec)
                scheduled_any = True
                current_local_parallel += 1

        if not active:
            if pending and not scheduled_any:
                raise RuntimeError("No pending tasks could be scheduled. Check concurrency/resource configuration.")
            break

        done, _ = await asyncio.wait(active.keys(), return_when=asyncio.FIRST_COMPLETED)
        for task in done:
            run_id, resource_keys, spec, started_at = active.pop(task)
            try:
                returncode, stdout, stderr = task.result()
            finally:
                lock_manager.release_many(run_id, resource_keys)
            finished_at = time.time()
            entry = _make_entry(spec, returncode, stdout, stderr, started_at, finished_at)
            summaries.append(entry)
            append_jsonl(log_path, entry)
            if returncode != 0 and not args.continue_on_error:
                stop_scheduling = True
    return summaries


def main() -> int:
    args = parse_args()
    repo_root = REPO_ROOT
    tasks_root = (repo_root / args.tasks_root).resolve()
    output_root = (repo_root / args.output_dir).resolve()
    batch_id = args.batch_id.strip() or f"{args.run_prefix}-{int(time.time())}"
    batch_dir = output_root / batch_id
    batch_dir.mkdir(parents=True, exist_ok=True)
    log_path = batch_dir / "timing_log.jsonl"

    rerun_batch = Path(args.rerun_from_batch).resolve() if args.rerun_from_batch else None
    rerun_statuses = {item.strip() for item in args.rerun_statuses.split(",") if item.strip()}
    if rerun_batch:
        tasks = discover_rerun_tasks(rerun_batch, args.tasks, rerun_statuses, args.limit)
    else:
        tasks = discover_tasks(tasks_root, args.tasks, args.limit)
    task_specs = build_task_specs(repo_root, args, tasks)
    plan = {
        "batch_id": batch_id,
        "tasks_root": str(tasks_root),
        "tasks": [str(task) for task in tasks],
        "output_dir": str(output_root),
        "harness": str((repo_root / args.harness).resolve()),
        "service_config": str((repo_root / args.service_config).resolve()),
        "tools_file": str((repo_root / args.tools_file).resolve()),
        "attacker_config": str((repo_root / args.attacker_config).resolve()) if args.attacker_config else "",
        "eval_strategy": args.eval_strategy,
        "max_iterations": max(1, int(args.max_iterations or 1)),
        "adaptive_iterations": bool(args.adaptive_iterations),
        "parallelism": max(1, int(args.parallelism or 1)),
        "rerun_from_batch": str(rerun_batch) if rerun_batch else "",
        "rerun_statuses": sorted(rerun_statuses),
    }
    (batch_dir / "plan.json").write_text(json.dumps(plan, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    summaries = asyncio.run(execute_parallel_runs(repo_root, output_root, args, task_specs, log_path))

    aggregate: dict[str, Any] = {
        "batch_id": batch_id,
        "task_count": len(summaries),
        "successful_runs": sum(1 for item in summaries if item["returncode"] == 0),
        "failed_runs": sum(1 for item in summaries if item["returncode"] != 0),
        "runs": summaries,
    }

    phase_totals: dict[str, int] = {}
    phase_counts: dict[str, int] = {}
    for item in summaries:
        timing = item.get("timing", {}) or {}
        phases = timing.get("phases_ms", {}) or {}
        for name, value in phases.items():
            if not isinstance(value, int):
                continue
            phase_totals[name] = phase_totals.get(name, 0) + value
            phase_counts[name] = phase_counts.get(name, 0) + 1

    aggregate["phase_totals_ms"] = phase_totals
    aggregate["phase_avg_ms"] = {
        name: int(phase_totals[name] / phase_counts[name])
        for name in sorted(phase_totals)
        if phase_counts.get(name)
    }
    aggregate["wall_total_ms"] = sum(item["wall_ms"] for item in summaries)

    (batch_dir / "summary.json").write_text(json.dumps(aggregate, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({
        "batch_id": batch_id,
        "summary_file": str(batch_dir / "summary.json"),
        "log_file": str(log_path),
        "task_count": len(summaries),
        "successful_runs": aggregate["successful_runs"],
        "failed_runs": aggregate["failed_runs"],
    }, ensure_ascii=False, indent=2))
    return 0 if aggregate["failed_runs"] == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())

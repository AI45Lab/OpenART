#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import shlex
import subprocess
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Sequence


REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_RLAUNCH_SCRIPT = REPO_ROOT.parent / "rlaunch_cpu_forever.sh"
DEFAULT_STARTUP_SCRIPT = REPO_ROOT.parent / "start_mihomo_in_worker.sh"


@dataclass(frozen=True)
class WorkerPlan:
    index: int
    shard_id: str
    task_names: list[str]
    command: list[str]
    stdout_log: str
    stderr_log: str


def split_wrapper_args(argv: Sequence[str] | None = None) -> tuple[list[str], list[str]]:
    raw = list(sys.argv[1:] if argv is None else argv)
    if "--" not in raw:
        return raw, []
    index = raw.index("--")
    return raw[:index], raw[index + 1:]


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    wrapper_args, batch_runner_args = split_wrapper_args(argv)
    parser = argparse.ArgumentParser(
        description=(
            "Shard OpenART batch runs across rlaunch CPU workers. Each worker "
            "uses a worker-local Docker daemon."
        )
    )
    parser.add_argument("--tasks-root", default="../openagentsafety/tasks", help="Directory containing task subfolders")
    parser.add_argument("--output-dir", default="outputs/rlaunch-worker-docker", help="Shared output root")
    parser.add_argument("--batch-id", default="", help="Batch id for this distributed run")
    parser.add_argument("--run-prefix", default="rlaunch", help="Prefix used when --batch-id is omitted")
    parser.add_argument("--task", action="append", dest="tasks", default=[], help="Specific task directory name; repeatable")
    parser.add_argument("--limit", type=int, default=0, help="Maximum number of tasks to schedule")
    parser.add_argument("--worker-count", type=int, default=1, help="Number of CPU workers to request")
    parser.add_argument("--worker-parallelism", type=int, default=1, help="OpenART local parallelism inside each worker")
    parser.add_argument("--cpu", default="4", help="CPU count passed to rlaunch")
    parser.add_argument("--memory", default="32G", help="Memory passed to rlaunch, e.g. 32G")
    parser.add_argument("--image", default="", help="Optional worker image passed to rlaunch_cpu_forever.sh")
    parser.add_argument("--charged-group", default="", help="Optional rlaunch charged group override")
    parser.add_argument("--private-machine", default="", help="Optional rlaunch private-machine value")
    parser.add_argument("--privileged", action="store_true", help="Pass --privileged to rlaunch_cpu_forever.sh")
    parser.add_argument(
        "--rlaunch-arg",
        action="append",
        default=[],
        help="Extra single argument passed through to rlaunch_cpu_forever.sh; repeat as needed",
    )
    parser.add_argument("--rlaunch-script", default=str(DEFAULT_RLAUNCH_SCRIPT), help="Path to rlaunch_cpu_forever.sh")
    parser.add_argument("--python-bin", default="python3", help="Python executable used inside each worker")
    parser.add_argument("--docker-data-root", default="/docker-data", help="Worker-local Docker data-root")
    parser.add_argument("--dockerd-log", default="/tmp/openart-dockerd.log", help="dockerd log path inside the worker")
    parser.add_argument("--docker-start-timeout", type=int, default=60, help="Seconds to wait for dockerd")
    parser.add_argument(
        "--preflight-image",
        default="",
        help="Optional image for a bind-mount smoke test, e.g. busybox:latest",
    )
    parser.add_argument("--preflight", action="store_true", help="Run a one-worker Docker/OpenART preflight first")
    parser.add_argument("--dry-run", action="store_true", help="Print the generated commands and do not submit workers")
    args = parser.parse_args(wrapper_args)
    args.batch_runner_args = batch_runner_args
    return args


def resolve_path(path_text: str, base: Path = REPO_ROOT) -> Path:
    path = Path(path_text).expanduser()
    if not path.is_absolute():
        path = base / path
    return path.resolve()


def discover_tasks(tasks_root: Path, selected: list[str], limit: int) -> list[Path]:
    if selected:
        tasks = [tasks_root / name for name in selected]
    else:
        tasks = [path for path in sorted(tasks_root.iterdir()) if (path / "task.md").is_file()]
    tasks = [path.resolve() for path in tasks if path.is_dir() and (path / "task.md").is_file()]
    if limit > 0:
        return tasks[:limit]
    return tasks


def shard_tasks(tasks: list[Path], worker_count: int) -> list[list[Path]]:
    count = max(1, int(worker_count or 1))
    shards = [[] for _ in range(count)]
    for index, task in enumerate(tasks):
        shards[index % count].append(task)
    return [shard for shard in shards if shard]


def shell_join(parts: Sequence[str]) -> str:
    return " ".join(shlex.quote(str(part)) for part in parts)


def docker_bootstrap_lines(args: argparse.Namespace) -> list[str]:
    timeout = max(1, int(args.docker_start_timeout or 1))
    lines = [
        "set -euo pipefail",
        f"source {shlex.quote(str(DEFAULT_STARTUP_SCRIPT))} 2>/dev/null || true",
        "unset DOCKER_HOST DOCKER_TLS_VERIFY DOCKER_CERT_PATH",
        "if ! command -v docker >/dev/null 2>&1; then echo 'docker CLI not found in worker' >&2; exit 127; fi",
        "if ! docker info >/dev/null 2>&1; then",
        "  if command -v dockerd >/dev/null 2>&1; then",
        f"    mkdir -p {shlex.quote(str(args.docker_data_root))}",
        (
            "    nohup dockerd --storage-driver=fuse-overlayfs "
            f"--data-root={shlex.quote(str(args.docker_data_root))} "
            f">{shlex.quote(str(args.dockerd_log))} 2>&1 &"
        ),
        f"    for _openart_i in $(seq 1 {timeout}); do docker info >/dev/null 2>&1 && break; sleep 1; done",
        "  fi",
        "fi",
        "docker info >/dev/null",
    ]
    return lines


def optional_bind_mount_smoke_lines(repo_root: Path, image: str) -> list[str]:
    if not image:
        return []
    container_name = "openart-bind-preflight-$$"
    return [
        (
            "docker run --rm --name "
            f"{container_name} "
            f"--mount type=bind,src={shlex.quote(str(repo_root))},dst=/openart-preflight,readonly "
            f"{shlex.quote(image)} "
            "sh -lc 'test -f /openart-preflight/README.md'"
        )
    ]


def build_preflight_shell_command(repo_root: Path, args: argparse.Namespace) -> str:
    lines = docker_bootstrap_lines(args)
    lines.extend(optional_bind_mount_smoke_lines(repo_root, str(args.preflight_image or "")))
    lines.extend(
        [
            f"test -d {shlex.quote(str(repo_root))}",
            f"cd {shlex.quote(str(repo_root))}",
            f"{shlex.quote(str(args.python_bin))} -m framework.cli doctor",
        ]
    )
    return "\n".join(lines)


def build_batch_shell_command(
    repo_root: Path,
    tasks_root: Path,
    output_dir: Path,
    batch_id: str,
    shard: list[Path],
    args: argparse.Namespace,
) -> str:
    batch_cmd = [
        str(args.python_bin),
        "scripts/run_all_tasks_with_timing.py",
        *[str(item) for item in args.batch_runner_args],
        "--tasks-root",
        str(tasks_root),
        "--output-dir",
        str(output_dir),
        "--batch-id",
        batch_id,
        "--parallelism",
        str(max(1, int(args.worker_parallelism or 1))),
    ]
    for task in shard:
        batch_cmd.extend(["--task", task.name])

    lines = docker_bootstrap_lines(args)
    lines.extend(
        [
            f"test -d {shlex.quote(str(repo_root))}",
            f"cd {shlex.quote(str(repo_root))}",
            f"exec {shell_join(batch_cmd)}",
        ]
    )
    return "\n".join(lines)


def rlaunch_base_command(args: argparse.Namespace) -> list[str]:
    command = [
        str(resolve_path(args.rlaunch_script)),
        "--memory",
        str(args.memory),
        "--cpu",
        str(args.cpu),
    ]
    if args.image:
        command.extend(["--image", str(args.image)])
    if args.charged_group:
        command.extend(["--charged-group", str(args.charged_group)])
    if args.private_machine:
        command.extend(["--private-machine", str(args.private_machine)])
    if args.privileged:
        command.append("--privileged")
    for item in args.rlaunch_arg:
        command.extend(["--rlaunch-arg", str(item)])
    return command


def build_rlaunch_command(args: argparse.Namespace, shell_command: str) -> list[str]:
    return [*rlaunch_base_command(args), "--", "bash", "-lc", shell_command]


def build_worker_plans(
    repo_root: Path,
    tasks_root: Path,
    output_dir: Path,
    batch_id: str,
    tasks: list[Path],
    args: argparse.Namespace,
) -> list[WorkerPlan]:
    plans: list[WorkerPlan] = []
    for index, shard in enumerate(shard_tasks(tasks, int(args.worker_count or 1)), start=1):
        shard_id = f"{batch_id}-shard-{index:03d}"
        shell_command = build_batch_shell_command(repo_root, tasks_root, output_dir, shard_id, shard, args)
        plans.append(
            WorkerPlan(
                index=index,
                shard_id=shard_id,
                task_names=[task.name for task in shard],
                command=build_rlaunch_command(args, shell_command),
                stdout_log=str(output_dir / batch_id / f"worker_{index:03d}.stdout.log"),
                stderr_log=str(output_dir / batch_id / f"worker_{index:03d}.stderr.log"),
            )
        )
    return plans


def plan_payload(
    repo_root: Path,
    tasks_root: Path,
    output_dir: Path,
    batch_id: str,
    worker_plans: list[WorkerPlan],
    args: argparse.Namespace,
    preflight_command: list[str] | None,
) -> dict[str, object]:
    return {
        "batch_id": batch_id,
        "repo_root": str(repo_root),
        "tasks_root": str(tasks_root),
        "output_dir": str(output_dir),
        "worker_count_requested": max(1, int(args.worker_count or 1)),
        "worker_count_scheduled": len(worker_plans),
        "worker_parallelism": max(1, int(args.worker_parallelism or 1)),
        "preflight": bool(args.preflight),
        "preflight_command": preflight_command or [],
        "batch_runner_args": list(args.batch_runner_args),
        "workers": [
            {
                "index": plan.index,
                "shard_id": plan.shard_id,
                "tasks": plan.task_names,
                "command": plan.command,
                "stdout_log": plan.stdout_log,
                "stderr_log": plan.stderr_log,
            }
            for plan in worker_plans
        ],
    }


def run_preflight(command: list[str], cwd: Path) -> int:
    return subprocess.run(command, cwd=str(cwd), check=False).returncode


def run_worker_plans(worker_plans: list[WorkerPlan], cwd: Path) -> list[dict[str, object]]:
    processes: list[tuple[WorkerPlan, subprocess.Popen[bytes], object, object, float]] = []
    for plan in worker_plans:
        stdout_path = Path(plan.stdout_log)
        stderr_path = Path(plan.stderr_log)
        stdout_path.parent.mkdir(parents=True, exist_ok=True)
        stdout_handle = stdout_path.open("wb")
        stderr_handle = stderr_path.open("wb")
        started = time.time()
        proc = subprocess.Popen(plan.command, cwd=str(cwd), stdout=stdout_handle, stderr=stderr_handle)
        processes.append((plan, proc, stdout_handle, stderr_handle, started))

    results: list[dict[str, object]] = []
    for plan, proc, stdout_handle, stderr_handle, started in processes:
        returncode = proc.wait()
        finished = time.time()
        stdout_handle.close()
        stderr_handle.close()
        results.append(
            {
                "index": plan.index,
                "shard_id": plan.shard_id,
                "tasks": plan.task_names,
                "returncode": returncode,
                "started_at": started,
                "finished_at": finished,
                "wall_ms": int((finished - started) * 1000),
                "stdout_log": plan.stdout_log,
                "stderr_log": plan.stderr_log,
            }
        )
    return results


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    repo_root = REPO_ROOT.resolve()
    tasks_root = resolve_path(str(args.tasks_root), repo_root)
    output_dir = resolve_path(str(args.output_dir), repo_root)
    batch_id = str(args.batch_id or "").strip() or f"{args.run_prefix}-{int(time.time())}"
    tasks = discover_tasks(tasks_root, list(args.tasks), int(args.limit or 0))
    worker_plans = build_worker_plans(repo_root, tasks_root, output_dir, batch_id, tasks, args)
    preflight_command = (
        build_rlaunch_command(args, build_preflight_shell_command(repo_root, args))
        if args.preflight
        else None
    )
    payload = plan_payload(repo_root, tasks_root, output_dir, batch_id, worker_plans, args, preflight_command)

    if args.dry_run:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
        return 0

    batch_dir = output_dir / batch_id
    batch_dir.mkdir(parents=True, exist_ok=True)
    (batch_dir / "rlaunch_plan.json").write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    if preflight_command:
        preflight_code = run_preflight(preflight_command, repo_root)
        if preflight_code != 0:
            summary = {"batch_id": batch_id, "preflight_returncode": preflight_code, "workers": []}
            (batch_dir / "rlaunch_summary.json").write_text(
                json.dumps(summary, ensure_ascii=False, indent=2) + "\n",
                encoding="utf-8",
            )
            print(json.dumps(summary, ensure_ascii=False, indent=2))
            return preflight_code

    worker_results = run_worker_plans(worker_plans, repo_root)
    failed = [result for result in worker_results if int(result["returncode"]) != 0]
    summary = {
        "batch_id": batch_id,
        "worker_count": len(worker_results),
        "successful_workers": len(worker_results) - len(failed),
        "failed_workers": len(failed),
        "workers": worker_results,
    }
    (batch_dir / "rlaunch_summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0 if not failed else 1


if __name__ == "__main__":
    raise SystemExit(main())

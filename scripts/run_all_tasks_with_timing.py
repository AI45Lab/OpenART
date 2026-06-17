#!/usr/bin/env python3
from __future__ import annotations

import asyncio
import argparse
import json
import os
from pathlib import Path
import signal
import socket
import subprocess
import sys
import time
from typing import Any
from urllib import error as urlerror, parse as urlparse, request as urlrequest

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from framework.tasks.loader import load_task_bundle
from framework.cli.commands import load_env


_ACTIVE_SUBPROCESSES: set[asyncio.subprocess.Process] = set()
_ACTIVE_POPEN_SUBPROCESSES: set[subprocess.Popen] = set()
_LEGACY_RUNTIME_TOOL_FLAGS = {
    "tools_file": "--tools-file",
    "capabilities_file": "--capabilities-file",
    "capabilities_dir": "--capabilities-dir",
}
_RUNTIME_TOOL_MIGRATION_ERROR = (
    "legacy runtime tool flags are no longer supported: {flags}; managed tool loading now uses "
    "--tool-store plus task/tool_use_graph.json"
)


def _terminate_subprocess(proc: asyncio.subprocess.Process, signum: int = signal.SIGTERM) -> None:
    if proc.returncode is not None:
        return
    try:
        os.killpg(proc.pid, signum)
    except ProcessLookupError:
        return
    except Exception:
        try:
            proc.terminate()
        except ProcessLookupError:
            pass


def _terminate_active_subprocesses(signum: int = signal.SIGTERM) -> None:
    for proc in list(_ACTIVE_SUBPROCESSES):
        _terminate_subprocess(proc, signum)
    for proc in list(_ACTIVE_POPEN_SUBPROCESSES):
        _terminate_popen_subprocess(proc, signum)


def _terminate_popen_subprocess(proc: subprocess.Popen, signum: int = signal.SIGTERM) -> None:
    if proc.poll() is not None:
        return
    try:
        os.killpg(proc.pid, signum)
    except ProcessLookupError:
        return
    except Exception:
        try:
            proc.terminate()
        except ProcessLookupError:
            pass


class _BatchSignalCleanup:
    def __init__(self) -> None:
        self._previous: dict[int, Any] = {}

    def __enter__(self):
        for signum in (signal.SIGINT, signal.SIGTERM):
            self._previous[signum] = signal.getsignal(signum)
            signal.signal(signum, self._handle)
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        for signum, previous in self._previous.items():
            signal.signal(signum, previous)

    def _handle(self, signum, frame) -> None:
        _terminate_active_subprocesses(signal.SIGTERM)
        raise SystemExit(128 + int(signum))


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run many OpenAgentSafety tasks and record timing artifacts.")
    parser.add_argument("--tasks-root", default="../openagentsafety/tasks", help="Directory containing task subfolders")
    parser.add_argument("--output-dir", default="outputs/batch-timing", help="Output root for run artifacts")
    parser.add_argument(
        "--evaluator-harness",
        dest="evaluator_harness",
        default="openagentsafety_utils/oas_harness",
        help="Evaluator harness directory path",
    )
    parser.add_argument("--harness", dest="evaluator_harness", default=argparse.SUPPRESS, help=argparse.SUPPRESS)
    parser.add_argument("--tools-file", default="", help=argparse.SUPPRESS)
    parser.add_argument("--tool-store", default="", help="Optional managed OpenART tool store path")
    parser.add_argument("--capabilities-file", action="append", default=[], help=argparse.SUPPRESS)
    parser.add_argument("--capabilities-dir", action="append", default=[], help=argparse.SUPPRESS)
    parser.add_argument("--attacker-config", default="", help="Optional universal attacker config")
    parser.add_argument("--target-config", default="", help="Optional target runner config yaml/json")
    parser.add_argument("--runner-framework", default="", help="Optional runner framework override")
    parser.add_argument("--runner-model", default="", help="Optional runner model override")
    parser.add_argument("--eval-strategy", choices=["auto", "deterministic", "llm", "both"], default="both")
    parser.add_argument("--task", action="append", dest="tasks", default=[], help="Specific task directory name; repeatable")
    parser.add_argument("--limit", type=int, default=0, help="Maximum number of tasks to run")
    parser.add_argument("--max-iterations", type=int, default=1, help="Maximum number of target attempts per task run")
    parser.add_argument("--adaptive-iterations", action="store_true", default=True, help="Only retry target iterations when the current result looks incomplete (default: on)")
    parser.add_argument("--no-adaptive-iterations", action="store_true", help="Disable adaptive iterations")
    parser.add_argument("--target-timeout-seconds", type=int, default=0, help="Minimum timeout for each target runner invocation")
    parser.add_argument("--attacker-timeout-seconds", type=int, default=0, help="Minimum timeout for each attacker invocation")
    parser.add_argument("--skip-attacker", action="store_true", help="Skip attacker execution even when configured")
    parser.add_argument("--parallelism", type=int, default=4, help="Maximum number of task subprocesses to run concurrently")
    parser.add_argument("--run-prefix", default="batch", help="Prefix for generated run ids")
    parser.add_argument("--batch-id", default="", help="Optional explicit batch id for output directory naming")
    parser.add_argument("--continue-on-error", action="store_true", help="Continue even if a task run fails")
    parser.add_argument("--rerun-from-batch", default="", help="Previous batch directory to mine for failed/unknown/error tasks")
    parser.add_argument("--rerun-statuses", default="fail,unknown,error", help="Comma-separated statuses to rerun from the prior batch: fail, unknown, pass, error")
    parser.add_argument("--require-target-validation", action="store_true", default=True, help="Validate target model integration before launching task runs (default: enabled)")
    parser.add_argument("--allow-unvalidated-target", action="store_true", help="Continue when target model integration validation fails")
    parser.add_argument(
        "--target-responses-router",
        choices=["none", "responses-to-chat"],
        default="none",
        help="Launch a local /v1/responses router for the target endpoint before validation and task runs",
    )
    parser.add_argument("--surface-family", default="", help="Target native surface-family override for validation")
    parser.add_argument("--docs-url", default="", help="Docs URL override for validation")
    args = parser.parse_args()
    used = [
        flag
        for dest, flag in _LEGACY_RUNTIME_TOOL_FLAGS.items()
        if (
            any(str(item or "").strip() for item in getattr(args, dest, []))
            if isinstance(getattr(args, dest, None), list)
            else bool(str(getattr(args, dest, "") or "").strip())
        )
    ]
    if used:
        parser.error(_RUNTIME_TOOL_MIGRATION_ERROR.format(flags=", ".join(used)))
    return args


def read_json(path: Path) -> dict[str, Any]:
    if not path.is_file():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def _reserve_local_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def _redact_url(value: str) -> str:
    text = str(value or "")
    try:
        parsed = urlparse.urlsplit(text)
    except Exception:
        return text
    if not parsed.netloc:
        return text
    host = parsed.hostname or ""
    netloc = host
    if parsed.port is not None:
        netloc = f"{netloc}:{parsed.port}"
    query = "<redacted>" if parsed.query else ""
    return urlparse.urlunsplit((parsed.scheme, netloc, parsed.path, query, ""))


def _read_log_preview(path: Path, max_lines: int = 40) -> str:
    if not path.is_file():
        return ""
    return "\n".join(path.read_text(encoding="utf-8", errors="replace").splitlines()[:max_lines])


def _args_evaluator_harness(args: argparse.Namespace) -> str:
    return str(getattr(args, "evaluator_harness", "") or getattr(args, "harness", "") or "")


def _wait_for_router_health(proc: subprocess.Popen, health_url: str, log_path: Path, timeout_seconds: int = 15) -> None:
    deadline = time.time() + max(1, timeout_seconds)
    last_error = ""
    while time.time() < deadline:
        if proc.poll() is not None:
            preview = _read_log_preview(log_path)
            raise RuntimeError(
                f"responses router exited before becoming healthy with code {proc.returncode}. "
                f"Log preview:\n{preview}"
            )
        try:
            with urlrequest.urlopen(health_url, timeout=1) as response:
                if 200 <= int(getattr(response, "status", 200) or 200) < 300:
                    return
        except urlerror.URLError as exc:
            last_error = str(exc)
        except Exception as exc:
            last_error = str(exc)
        time.sleep(0.2)
    preview = _read_log_preview(log_path)
    raise RuntimeError(f"responses router did not become healthy: {last_error}\nLog preview:\n{preview}")


def _start_target_responses_router(repo_root: Path, batch_dir: Path, mode: str) -> dict[str, Any]:
    if mode != "responses-to-chat":
        raise ValueError(f"unsupported target responses router mode: {mode}")
    upstream_base_url = str(os.environ.get("TARGET_BASE_URL", "") or "").strip()
    if not upstream_base_url:
        raise RuntimeError("TARGET_BASE_URL is required to launch --target-responses-router responses-to-chat")

    port = _reserve_local_port()
    router_origin = f"http://127.0.0.1:{port}"
    router_base_url = f"{router_origin}/v1"
    log_path = batch_dir / "responses_router.log"
    metadata_path = batch_dir / "responses_router.json"
    cmd = [
        sys.executable,
        str(repo_root / "scripts" / "openai_responses_router.py"),
        "--host",
        "127.0.0.1",
        "--port",
        str(port),
        "--log-file",
        str(log_path),
    ]
    env = dict(os.environ)
    removed_proxy_env = []
    for key in ("http_proxy", "https_proxy", "HTTP_PROXY", "HTTPS_PROXY", "all_proxy", "ALL_PROXY"):
        if key in env:
            removed_proxy_env.append(key)
            env.pop(key, None)
    env["OPENART_RESPONSES_ROUTER_UPSTREAM_BASE_URL"] = upstream_base_url
    env["OPENART_RESPONSES_ROUTER_API_KEY"] = str(os.environ.get("TARGET_API_KEY", "") or "")
    env["OPENART_RESPONSES_ROUTER_DEFAULT_MODEL"] = str(os.environ.get("TARGET_MODEL", "") or "")
    env["OPENART_RESPONSES_ROUTER_LOG_FILE"] = str(log_path)

    log_path.parent.mkdir(parents=True, exist_ok=True)
    stdout_handle = log_path.open("ab")
    try:
        proc = subprocess.Popen(
            cmd,
            cwd=str(repo_root),
            env=env,
            stdout=stdout_handle,
            stderr=subprocess.STDOUT,
            start_new_session=True,
        )
    finally:
        stdout_handle.close()
    _ACTIVE_POPEN_SUBPROCESSES.add(proc)
    try:
        _wait_for_router_health(proc, f"{router_origin}/healthz", log_path)
    except Exception:
        _terminate_popen_subprocess(proc, signal.SIGTERM)
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            _terminate_popen_subprocess(proc, signal.SIGKILL)
            proc.wait(timeout=5)
        _ACTIVE_POPEN_SUBPROCESSES.discard(proc)
        raise

    os.environ["TARGET_BASE_URL"] = router_base_url
    metadata = {
        "mode": mode,
        "pid": proc.pid,
        "router_origin": router_origin,
        "router_base_url": router_base_url,
        "health_url": f"{router_origin}/healthz",
        "upstream_base_url": _redact_url(upstream_base_url),
        "target_base_url_rewrite": {
            "from": _redact_url(upstream_base_url),
            "to": router_base_url,
        },
        "api_key_present": bool(os.environ.get("TARGET_API_KEY")),
        "target_model": str(os.environ.get("TARGET_MODEL", "") or ""),
        "proxy_env_removed": removed_proxy_env,
        "log_file": str(log_path),
        "command": cmd,
        "started_at": time.time(),
    }
    metadata_path.write_text(json.dumps(metadata, ensure_ascii=True, indent=2) + "\n", encoding="utf-8")
    return {
        "process": proc,
        "metadata": metadata,
        "metadata_path": metadata_path,
        "log_path": log_path,
        "router_base_url": router_base_url,
        "upstream_base_url": upstream_base_url,
    }


def _stop_target_responses_router(router: dict[str, Any]) -> None:
    proc = router.get("process")
    if not isinstance(proc, subprocess.Popen):
        return
    _terminate_popen_subprocess(proc, signal.SIGTERM)
    try:
        proc.wait(timeout=10)
    except subprocess.TimeoutExpired:
        _terminate_popen_subprocess(proc, signal.SIGKILL)
        proc.wait(timeout=10)
    _ACTIVE_POPEN_SUBPROCESSES.discard(proc)
    metadata_path = router.get("metadata_path")
    metadata = dict(router.get("metadata") or {})
    metadata["stopped_at"] = time.time()
    metadata["returncode"] = proc.returncode
    if isinstance(metadata_path, Path):
        metadata_path.write_text(json.dumps(metadata, ensure_ascii=True, indent=2) + "\n", encoding="utf-8")


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


def build_run_command(repo_root: Path, args: argparse.Namespace, task_dir: Path, run_id: str, output_root: Path) -> list[str]:
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
        str(output_root.resolve()),
        "--evaluator-harness",
        str((repo_root / _args_evaluator_harness(args)).resolve()),
        "--eval-strategy",
        args.eval_strategy,
        "--max-iterations",
        str(max(1, int(args.max_iterations or 1))),
    ]
    if int(args.target_timeout_seconds or 0) > 0:
        cmd.extend(["--target-timeout-seconds", str(int(args.target_timeout_seconds))])
    if int(args.attacker_timeout_seconds or 0) > 0:
        cmd.extend(["--attacker-timeout-seconds", str(int(args.attacker_timeout_seconds))])
    if args.adaptive_iterations and not args.no_adaptive_iterations:
        cmd.append("--adaptive-iterations")
    if args.attacker_config:
        cmd.extend(["--attacker-config", str((repo_root / args.attacker_config).resolve())])
    if args.target_config:
        cmd.extend(["--target-config", str((repo_root / args.target_config).resolve())])
    if getattr(args, "tool_store", ""):
        cmd.extend(["--tool-store", str((repo_root / args.tool_store).resolve())])
    if args.runner_framework:
        cmd.extend(["--runner-framework", str(args.runner_framework)])
    if args.runner_model:
        cmd.extend(["--runner-model", str(args.runner_model)])
    if args.skip_attacker:
        cmd.append("--skip-attacker")
    cmd.append("--skip-build")
    return cmd


def append_jsonl(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(payload, ensure_ascii=False) + "\n")


def run_target_validation(repo_root: Path, args: argparse.Namespace, batch_dir: Path) -> dict[str, Any]:
    target_config = (
        Path(args.target_config).resolve()
        if args.target_config
        else (repo_root / "configs" / "target-configs" / "target.yaml").resolve()
    )
    output = batch_dir / "target_model_integration_validation.json"
    cmd = [
        sys.executable,
        str(repo_root / "scripts" / "validate_target_adapter.py"),
        "--target-config",
        str(target_config),
        "--output",
        str(output),
        "--require-official-docs",
    ]
    surface_family = str(getattr(args, "surface_family", "") or "")
    if surface_family:
        cmd.extend(["--surface-family", surface_family])
    if args.docs_url:
        cmd.extend(["--docs-url", str(args.docs_url)])

    started = time.time()
    proc = subprocess.run(cmd, cwd=str(repo_root), env=dict(os.environ), text=True, capture_output=True, check=False)
    finished = time.time()
    payload = read_json(output)
    if not payload:
        payload = {
            "surface_family": surface_family,
            "status": "invalid",
            "errors": ["validation command did not write target_model_integration_validation.json"],
        }
        output.write_text(json.dumps(payload, ensure_ascii=True, indent=2) + "\n", encoding="utf-8")
    payload["command"] = cmd
    payload["returncode"] = int(proc.returncode or 0)
    payload["stdout_preview"] = "\n".join(proc.stdout.splitlines()[:20])
    payload["stderr_preview"] = "\n".join(proc.stderr.splitlines()[:20])
    payload["wall_ms"] = int((finished - started) * 1000)
    payload["artifact"] = str(output)
    output.write_text(json.dumps(payload, ensure_ascii=True, indent=2) + "\n", encoding="utf-8")
    return payload


async def run_subprocess(cmd: list[str], cwd: Path, env: dict[str, str]) -> tuple[int, str, str]:
    proc = await asyncio.create_subprocess_exec(
        *cmd,
        cwd=str(cwd),
        env=env,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
        start_new_session=True,
    )
    _ACTIVE_SUBPROCESSES.add(proc)
    try:
        stdout, stderr = await proc.communicate()
        return int(proc.returncode or 0), stdout.decode("utf-8", errors="replace"), stderr.decode("utf-8", errors="replace")
    except asyncio.CancelledError:
        _terminate_subprocess(proc, signal.SIGTERM)
        try:
            await asyncio.wait_for(proc.wait(), timeout=15)
        except asyncio.TimeoutError:
            _terminate_subprocess(proc, signal.SIGKILL)
            await proc.wait()
        raise
    finally:
        _ACTIVE_SUBPROCESSES.discard(proc)


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
    batch_id: str,
    args: argparse.Namespace,
    task_specs: list[dict[str, Any]],
    log_path: Path,
) -> tuple[list[dict[str, Any]], dict[str, int]]:
    env = dict(os.environ)
    requested_parallelism = max(1, int(args.parallelism or 1))
    pending = list(task_specs)
    active: dict[asyncio.Task, tuple[dict[str, Any], float]] = {}
    summaries: list[dict[str, Any]] = []
    metrics = {
        "requested_parallelism": requested_parallelism,
        "peak_active_runs": 0,
        "scheduled_run_count": 0,
        "completed_run_count": 0,
    }
    stop_scheduling = False

    def _make_entry(spec: dict[str, Any], returncode: int, stdout: str, stderr: str, started_at: float, finished_at: float) -> dict[str, Any]:
        run_dir = output_root / batch_id / spec["run_id"]
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
        if not stop_scheduling:
            while pending and len(active) < requested_parallelism:
                spec = pending.pop(0)
                cmd = build_run_command(repo_root, args, spec["task_dir"], spec["run_id"], output_root / batch_id)
                started_at = time.time()
                task = asyncio.create_task(run_subprocess(cmd, repo_root, env))
                active[task] = (spec, started_at)
                metrics["scheduled_run_count"] += 1
                metrics["peak_active_runs"] = max(metrics["peak_active_runs"], len(active))

        if not active:
            break

        done, _ = await asyncio.wait(active.keys(), return_when=asyncio.FIRST_COMPLETED)
        for task in done:
            spec, started_at = active.pop(task)
            returncode, stdout, stderr = task.result()
            finished_at = time.time()
            entry = _make_entry(spec, returncode, stdout, stderr, started_at, finished_at)
            summaries.append(entry)
            metrics["completed_run_count"] += 1
            append_jsonl(log_path, entry)
            if returncode != 0 and not args.continue_on_error:
                stop_scheduling = True
    return summaries, metrics


def main() -> int:
    args = parse_args()
    load_env()
    repo_root = REPO_ROOT
    tasks_root = (repo_root / args.tasks_root).resolve()
    output_root = (repo_root / args.output_dir).resolve()
    batch_id = args.batch_id.strip() or f"{args.run_prefix}-{int(time.time())}"
    batch_dir = output_root / batch_id
    batch_dir.mkdir(parents=True, exist_ok=True)
    log_path = batch_dir / "timing_log.jsonl"

    validation: dict[str, Any] = {}
    router: dict[str, Any] | None = None
    original_target_base_url = os.environ.get("TARGET_BASE_URL")
    with _BatchSignalCleanup():
        try:
            if args.target_responses_router != "none":
                router = _start_target_responses_router(repo_root, batch_dir, args.target_responses_router)

            if args.require_target_validation:
                validation = run_target_validation(repo_root, args, batch_dir)
                validation_status = str(validation.get("status", "") or "")
                router_requires_validation = args.target_responses_router != "none"
                if validation_status not in {"supported", "experimental"} and (
                    router_requires_validation or not args.allow_unvalidated_target
                ):
                    print(json.dumps({
                        "batch_id": batch_id,
                        "error": "target model integration validation failed",
                        "status": validation_status,
                        "validation_file": str(batch_dir / "target_model_integration_validation.json"),
                        "target_responses_router": args.target_responses_router,
                        "allow_unvalidated_target_ignored": bool(router_requires_validation and args.allow_unvalidated_target),
                    }, ensure_ascii=False, indent=2), file=sys.stderr)
                    return 2

            rerun_batch = Path(args.rerun_from_batch).resolve() if args.rerun_from_batch else None
            rerun_statuses = {item.strip() for item in args.rerun_statuses.split(",") if item.strip()}
            if rerun_batch:
                tasks = discover_rerun_tasks(rerun_batch, args.tasks, rerun_statuses, args.limit)
            else:
                tasks = discover_tasks(tasks_root, args.tasks, args.limit)
            task_specs = build_task_specs(repo_root, args, tasks)
            requested_parallelism = max(1, int(args.parallelism or 1))
            batch_metrics = {
                "requested_parallelism": requested_parallelism,
                "peak_active_runs": 0,
                "scheduled_run_count": 0,
                "completed_run_count": 0,
            }
            plan = {
                "batch_id": batch_id,
                "tasks_root": str(tasks_root),
                "tasks": [str(task) for task in tasks],
                "output_dir": str(output_root),
                "evaluator_harness": str((repo_root / _args_evaluator_harness(args)).resolve()),
                "tool_store": str((repo_root / args.tool_store).resolve()) if args.tool_store else "",
                "attacker_config": str((repo_root / args.attacker_config).resolve()) if args.attacker_config else "",
                "target_config": str((repo_root / args.target_config).resolve()) if args.target_config else "",
                "runner_framework": str(args.runner_framework or ""),
                "runner_model": str(args.runner_model or ""),
                "eval_strategy": args.eval_strategy,
                "max_iterations": max(1, int(args.max_iterations or 1)),
                "adaptive_iterations": bool(args.adaptive_iterations),
                "target_timeout_seconds": max(0, int(args.target_timeout_seconds or 0)),
                "attacker_timeout_seconds": max(0, int(args.attacker_timeout_seconds or 0)),
                "skip_attacker": bool(args.skip_attacker),
                "parallelism": requested_parallelism,
                "requested_parallelism": requested_parallelism,
                "batch_metrics": batch_metrics,
                "rerun_from_batch": str(rerun_batch) if rerun_batch else "",
                "rerun_statuses": sorted(rerun_statuses),
                "require_target_validation": bool(args.require_target_validation),
                "allow_unvalidated_target": bool(args.allow_unvalidated_target),
                "target_responses_router": args.target_responses_router,
                "responses_router": {
                    "metadata_file": str(router.get("metadata_path", "")),
                    "log_file": str(router.get("log_path", "")),
                    "router_base_url": str(router.get("router_base_url", "")),
                } if router else {},
                "target_validation": {
                    "status": validation.get("status", ""),
                    "artifact": validation.get("artifact", ""),
                } if validation else {},
            }
            (batch_dir / "plan.json").write_text(json.dumps(plan, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

            summaries, batch_metrics = asyncio.run(execute_parallel_runs(repo_root, output_root, batch_id, args, task_specs, log_path))
            plan.update(batch_metrics)
            plan["batch_metrics"] = dict(batch_metrics)
            (batch_dir / "plan.json").write_text(json.dumps(plan, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        finally:
            if router is not None:
                _stop_target_responses_router(router)
            if original_target_base_url is not None:
                os.environ["TARGET_BASE_URL"] = original_target_base_url
            elif router is not None:
                os.environ.pop("TARGET_BASE_URL", None)

    aggregate: dict[str, Any] = {
        "batch_id": batch_id,
        "task_count": len(summaries),
        "successful_runs": sum(1 for item in summaries if item["returncode"] == 0),
        "failed_runs": sum(1 for item in summaries if item["returncode"] != 0),
        "runs": summaries,
    }
    aggregate.update(batch_metrics)
    aggregate["batch_metrics"] = dict(batch_metrics)

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
    task_wall_sum_ms = sum(item["wall_ms"] for item in summaries)
    aggregate["task_wall_sum_ms"] = task_wall_sum_ms
    if summaries:
        batch_started_at = min(float(item["started_at"]) for item in summaries)
        batch_finished_at = max(float(item["finished_at"]) for item in summaries)
        aggregate["batch_started_at"] = batch_started_at
        aggregate["batch_finished_at"] = batch_finished_at
        aggregate["batch_wall_ms"] = int((batch_finished_at - batch_started_at) * 1000)
    else:
        aggregate["batch_wall_ms"] = 0
    aggregate["wall_total_ms"] = task_wall_sum_ms

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

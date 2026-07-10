#!/usr/bin/env python3
from __future__ import annotations

import argparse
import atexit
from concurrent.futures import FIRST_COMPLETED, Future, ThreadPoolExecutor, wait
from dataclasses import dataclass
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import threading
import time
from typing import Any, Sequence


REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from framework.cli.commands import load_env  # noqa: E402
from framework.core.tool_store import load_tool_store_manifest  # noqa: E402
from framework.planner.complexity import (  # noqa: E402
    DEFAULT_COMPLEXITY_PROFILE,
    builtin_complexity_profiles,
    default_repair_attempts_for_complexity,
    load_complexity_spec,
)
from framework.planner.opencode_backend import (  # noqa: E402
    DEFAULT_PLANNER_CONTEXT_MAX_CHARS,
    DEFAULT_PLANNER_CONTEXT_MODE,
    DEFAULT_PLANNER_DOCKER_IMAGE,
    DEFAULT_PLANNER_TIMEOUT_SECONDS,
    PLANNER_CONTEXT_MODES,
)
from framework.planner.validation import validate_generated_bundle  # noqa: E402
from framework.tasks.loader import load_task_bundle  # noqa: E402


DEFAULT_TOOL_STORE = REPO_ROOT.parent / "openart-tools"
GENERATED_SCENARIOS_DIR = REPO_ROOT / "configs" / "planner" / "scenarios" / "generated"
DEFAULT_PLANNER_CLI_TIMEOUT_SECONDS = 3600
PLANNER_CLI_TIMEOUT_BUFFER_SECONDS = 600


@dataclass(frozen=True)
class ScenarioFile:
    path: Path
    category: str
    scenario: str


def _read_generated_scenario_file(path: Path) -> ScenarioFile:
    category_values: list[str] = []
    scenario_values: list[str] = []
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if line.startswith("Category:"):
            category_values.append(line.removeprefix("Category:").strip())
        elif line.startswith("Scenario:"):
            scenario_values.append(line.removeprefix("Scenario:").strip())
    if len(category_values) != 1 or len(scenario_values) != 1:
        raise ValueError(
            f"{path} must contain exactly one 'Category:' line and exactly one 'Scenario:' line"
        )
    if not category_values[0] or not scenario_values[0]:
        raise ValueError(f"{path} contains an empty category or scenario")
    return ScenarioFile(path=path.resolve(), category=category_values[0], scenario=scenario_values[0])


def _discover_scenario_files(root: Path = GENERATED_SCENARIOS_DIR) -> list[ScenarioFile]:
    if not root.is_dir():
        return []
    paths = sorted(path for path in root.glob("category-*/scenario-*.txt") if path.is_file())
    return [_read_generated_scenario_file(path) for path in paths]


def _scenario_result_metadata(scenario_file: ScenarioFile) -> dict[str, str]:
    return {
        "scenario_file": str(scenario_file.path),
        "category": scenario_file.category,
        "scenario": scenario_file.scenario,
    }


def _attach_scenario_metadata(result: dict[str, Any], scenario_file: ScenarioFile) -> dict[str, Any]:
    result.update(_scenario_result_metadata(scenario_file))
    return result


_ACTIVE_PROCESSES: dict[int, subprocess.Popen[str]] = {}
_ACTIVE_PROCESSES_LOCK = threading.Lock()


def _positive_int(value: str) -> int:
    parsed = int(value)
    if parsed < 1:
        raise argparse.ArgumentTypeError("must be >= 1")
    return parsed


def _read_positive_int_env(key: str) -> int | None:
    try:
        parsed = int(str(os.environ.get(key, "") or "").strip())
    except ValueError:
        return None
    return parsed if parsed > 0 else None


def _planner_cli_timeout_seconds() -> int:
    explicit_timeout = _read_positive_int_env("OPENART_PLANNER_CLI_TIMEOUT_SECONDS")
    if explicit_timeout is not None:
        return explicit_timeout
    planner_timeout = _read_positive_int_env("OPENART_PLANNER_TIMEOUT_SECONDS")
    if planner_timeout is None:
        planner_timeout = DEFAULT_PLANNER_TIMEOUT_SECONDS
    return max(
        DEFAULT_PLANNER_CLI_TIMEOUT_SECONDS,
        planner_timeout + PLANNER_CLI_TIMEOUT_BUFFER_SECONDS,
    )


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run real OpenCode planner generation tasks.")
    parser.add_argument("--output-dir", default="outputs/opencode-planner-run", help="Planner output directory")
    parser.add_argument("--count", type=int, default=5, help="Number of scenarios to generate")
    parser.add_argument(
        "--start-index",
        type=_positive_int,
        default=1,
        help="1-based scenario index to start from after stable scenario sorting. Default: 1",
    )
    parser.add_argument(
        "--task-id-start",
        type=_positive_int,
        default=None,
        help="1-based task id number for the first selected scenario. Default: --start-index",
    )
    parser.add_argument(
        "--tool-count",
        type=int,
        default=2,
        help="Exact distinct enabled external tool count in tool_use_graph.safe_workflow.",
    )
    parser.add_argument("--workers", type=_positive_int, default=4, help="Planner task workers. Default: 4")
    parser.add_argument(
        "--planner-max-repairs",
        type=int,
        default=None,
        help="Repair attempts per task. Default: profile-aware auto.",
    )
    parser.add_argument(
        "--planner-context-mode",
        choices=PLANNER_CONTEXT_MODES,
        default=DEFAULT_PLANNER_CONTEXT_MODE,
        help="Planner prompt context mode passed to framework.planner.cli. Default: compact.",
    )
    parser.add_argument(
        "--planner-context-max-chars",
        type=int,
        default=DEFAULT_PLANNER_CONTEXT_MAX_CHARS,
        help=f"Soft character budget for compact planner context blocks. Default: {DEFAULT_PLANNER_CONTEXT_MAX_CHARS}.",
    )
    parser.add_argument(
        "--planner-repair-include-original-prompt",
        action="store_true",
        help="Pass through to planner CLI to embed the full original prompt during repairs.",
    )
    parser.add_argument(
        "--complexity-profile",
        choices=sorted(builtin_complexity_profiles()),
        default=DEFAULT_COMPLEXITY_PROFILE,
        help=f"Planner complexity profile for each generated task. Default: {DEFAULT_COMPLEXITY_PROFILE}",
    )
    parser.add_argument("--complexity-config", help="Optional YAML/JSON complexity config for the planner CLI.")
    parser.add_argument(
        "--planner-docker-image",
        default=DEFAULT_PLANNER_DOCKER_IMAGE,
        help=f"Planner Docker image used for OpenCode generation. Default: {DEFAULT_PLANNER_DOCKER_IMAGE}",
    )
    parser.add_argument(
        "--tool-store",
        default=str(DEFAULT_TOOL_STORE),
        help="Path to a managed OpenART tool store.",
    )
    parser.add_argument(
        "--scenario-dir",
        default=str(GENERATED_SCENARIOS_DIR),
        help="Directory containing generated category-*/scenario-*.txt files.",
    )
    parser.add_argument("--keep-going", action="store_true", help="Continue after a task generation failure")
    parser.add_argument("--python", default=sys.executable, help="Python executable for planner CLI subprocesses")
    args = parser.parse_args(argv)
    if args.planner_max_repairs is None:
        try:
            complexity_spec = load_complexity_spec(args.complexity_profile, config_path=args.complexity_config)
        except Exception as exc:
            parser.error(str(exc))
        args.planner_max_repairs = default_repair_attempts_for_complexity(
            complexity_spec,
            fallback_profile=args.complexity_profile,
        )
    if args.planner_max_repairs < 0:
        parser.error("--planner-max-repairs must be non-negative")
    if args.planner_context_max_chars <= 0:
        parser.error("--planner-context-max-chars must be positive")
    return args


def _required_env_status() -> dict[str, bool]:
    return {
        key: bool(str(os.environ.get(key, "") or "").strip())
        for key in ("OPENART_PLANNER_API_KEY", "OPENART_PLANNER_BASE_URL", "OPENART_PLANNER_MODEL")
    }


def _preflight_command(cmd: list[str]) -> dict[str, Any]:
    try:
        completed = subprocess.run(cmd, env=dict(os.environ), capture_output=True, text=True, timeout=120)
        return {
            "command": cmd,
            "returncode": completed.returncode,
            "stdout": completed.stdout[-2000:],
            "stderr": completed.stderr[-2000:],
        }
    except FileNotFoundError as exc:
        return {"command": cmd, "returncode": 127, "stdout": "", "stderr": str(exc)}
    except subprocess.TimeoutExpired as exc:
        return {
            "command": cmd,
            "returncode": 124,
            "stdout": (exc.stdout or "")[-2000:] if isinstance(exc.stdout, str) else "",
            "stderr": (exc.stderr or "")[-2000:] if isinstance(exc.stderr, str) else "preflight timed out",
        }


def _planner_image_preflight(image: str) -> dict[str, Any]:
    inspect = _preflight_command(["docker", "image", "inspect", image])
    version = _preflight_command(["docker", "run", "--rm", "--entrypoint", "opencode", image, "--version"])
    return {
        "image": image,
        "image_inspect": inspect,
        "opencode_version": version,
    }


def _resolve_tool_store_path(path_value: str) -> Path:
    path = Path(path_value)
    if not path.is_absolute():
        path = REPO_ROOT / path
    return path.resolve()


def _resolve_scenario_dir(path_value: str) -> Path:
    path = Path(path_value)
    if not path.is_absolute():
        path = REPO_ROOT / path
    return path.resolve()


def _has_tool_store_entry(path: Path) -> bool:
    guide_names = ("SKILL.md", "skill.md", "skills.md", "SKILLS.md", "TOOL.md", "tool.md", "tools.md", "TOOLS.md")
    return (path / "tool.yaml").is_file() or any((path / name).is_file() for name in guide_names)


def _tool_store_preflight(path: Path, *, tool_count: int) -> dict[str, Any]:
    exists = path.exists()
    valid = path.is_dir() and any(_has_tool_store_entry(child) for child in path.iterdir() if child.is_dir())
    result: dict[str, Any] = {
        "path": str(path),
        "exists": exists,
        "valid": valid,
        "required_external_tool_count": tool_count,
        "ready_external_tool_count": 0,
        "ready_external_tools": [],
        "enough_ready_external_tools": False,
    }
    if not valid:
        return result
    try:
        manifest = load_tool_store_manifest(path)
    except Exception as exc:
        result["valid"] = False
        result["error"] = f"{type(exc).__name__}: {exc}"
        return result

    raw_tools = manifest.get("tools", []) if isinstance(manifest.get("tools"), list) else []
    ready_names = sorted(
        str(item.get("name", ""))
        for item in raw_tools
        if isinstance(item, dict) and bool(item.get("enabled", True)) and str(item.get("name", ""))
    )
    result.update(
        {
            "ready_external_tool_count": len(ready_names),
            "ready_external_tools": ready_names,
            "enough_ready_external_tools": len(ready_names) >= tool_count,
        }
    )
    return result


def _register_process(process: subprocess.Popen[str]) -> None:
    with _ACTIVE_PROCESSES_LOCK:
        _ACTIVE_PROCESSES[process.pid] = process


def _unregister_process(process: subprocess.Popen[str]) -> None:
    with _ACTIVE_PROCESSES_LOCK:
        _ACTIVE_PROCESSES.pop(process.pid, None)


def _send_process_signal(process: subprocess.Popen[str], sig: signal.Signals) -> None:
    if process.poll() is not None:
        return
    try:
        if os.name == "posix":
            os.killpg(os.getpgid(process.pid), sig)
        elif sig == signal.SIGTERM:
            process.terminate()
        else:
            process.kill()
    except ProcessLookupError:
        return
    except Exception:
        try:
            if sig == signal.SIGTERM:
                process.terminate()
            else:
                process.kill()
        except ProcessLookupError:
            return


def _terminate_process_group(process: subprocess.Popen[str]) -> None:
    _send_process_signal(process, signal.SIGTERM)


def _kill_process_group(process: subprocess.Popen[str]) -> None:
    sigkill = getattr(signal, "SIGKILL", signal.SIGTERM)
    _send_process_signal(process, sigkill)


def _terminate_all_processes() -> None:
    with _ACTIVE_PROCESSES_LOCK:
        processes = list(_ACTIVE_PROCESSES.values())
    for process in processes:
        _terminate_process_group(process)
    deadline = time.time() + 10
    for process in processes:
        if process.poll() is not None:
            continue
        try:
            process.wait(timeout=max(0.1, deadline - time.time()))
        except subprocess.TimeoutExpired:
            _kill_process_group(process)


atexit.register(_terminate_all_processes)


def _run_planner_cli_subprocess(cmd: list[str], *, timeout: int) -> subprocess.CompletedProcess[str]:
    popen_kwargs: dict[str, Any] = {}
    if os.name == "posix":
        popen_kwargs["start_new_session"] = True
    process = subprocess.Popen(
        cmd,
        cwd=str(REPO_ROOT),
        env=dict(os.environ),
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        **popen_kwargs,
    )
    _register_process(process)
    try:
        try:
            stdout, stderr = process.communicate(timeout=timeout)
            return subprocess.CompletedProcess(cmd, process.returncode, stdout or "", stderr or "")
        except subprocess.TimeoutExpired:
            _terminate_process_group(process)
            try:
                stdout, stderr = process.communicate(timeout=10)
            except subprocess.TimeoutExpired:
                _kill_process_group(process)
                try:
                    stdout, stderr = process.communicate(timeout=5)
                except subprocess.TimeoutExpired:
                    stdout, stderr = "", "planner CLI did not exit after SIGKILL"
            timeout_message = f"planner CLI timed out after {timeout}s"
            stderr = f"{stderr or ''}\n{timeout_message}".strip()
            return subprocess.CompletedProcess(cmd, 124, stdout or "", stderr)
    finally:
        _unregister_process(process)


def _run_one(
    args: argparse.Namespace,
    tool_store_path: Path,
    output_root: Path,
    index: int,
    scenario_file: ScenarioFile,
) -> dict[str, Any]:
    task_id = f"opencode-planner-run-{index:03d}"
    task_dir = output_root / "tasks" / task_id
    cmd = [
        args.python,
        "-m",
        "framework.planner.cli",
        "--planner-backend",
        "opencode",
        "--planner-docker-image",
        args.planner_docker_image,
        "--scenario-file",
        str(scenario_file.path),
        "--task-id",
        task_id,
        "--tool-store",
        str(tool_store_path),
        "--tool-count",
        str(args.tool_count),
        "--complexity-profile",
        args.complexity_profile,
        "--planner-max-repairs",
        str(args.planner_max_repairs),
        "--planner-context-mode",
        args.planner_context_mode,
        "--planner-context-max-chars",
        str(args.planner_context_max_chars),
        "--output-dir",
        str(task_dir),
        "--overwrite",
    ]
    if args.planner_repair_include_original_prompt:
        cmd.append("--planner-repair-include-original-prompt")
    if args.complexity_config:
        cmd.extend(["--complexity-config", str(Path(args.complexity_config).resolve())])
    started = time.time()
    completed = _run_planner_cli_subprocess(cmd, timeout=_planner_cli_timeout_seconds())
    elapsed_ms = int((time.time() - started) * 1000)
    result: dict[str, Any] = {
        "task_id": task_id,
        "task_dir": str(task_dir),
        "returncode": completed.returncode,
        "elapsed_ms": elapsed_ms,
        "stdout": completed.stdout[-4000:],
        "stderr": completed.stderr[-4000:],
        "validation": None,
        "loaded": False,
    }
    _attach_scenario_metadata(result, scenario_file)
    if completed.returncode == 0:
        complexity_spec = load_complexity_spec(args.complexity_profile, config_path=args.complexity_config)
        validation = validate_generated_bundle(task_dir, tool_count=args.tool_count, complexity_spec=complexity_spec)
        try:
            load_task_bundle(str(task_dir))
            result["loaded"] = True
        except Exception as exc:
            validation.errors.append(f"load_task_bundle failed after validation: {exc}")
            validation.ok = False
        result["validation"] = validation.as_dict()
        if not validation.ok:
            result["returncode"] = 2
    return result


def _task_failure_result(
    output_root: Path,
    index: int,
    exc: BaseException,
    scenario_file: ScenarioFile | None = None,
) -> dict[str, Any]:
    task_id = f"opencode-planner-run-{index:03d}"
    result: dict[str, Any] = {
        "task_id": task_id,
        "task_dir": str(output_root / "tasks" / task_id),
        "returncode": 1,
        "elapsed_ms": 0,
        "stdout": "",
        "stderr": f"{type(exc).__name__}: {exc}",
        "validation": None,
        "loaded": False,
    }
    if scenario_file is not None:
        _attach_scenario_metadata(result, scenario_file)
    return result


def _ordered_completed_results(results_by_index: list[dict[str, Any] | None]) -> list[dict[str, Any]]:
    return [result for result in results_by_index if result is not None]


def _write_summary(
    output_root: Path,
    *,
    count: int,
    tool_store_path: Path,
    complexity_profile: str,
    planner_context_mode: str,
    planner_context_max_chars: int,
    planner_repair_include_original_prompt: bool,
    results: list[dict[str, Any]],
) -> dict[str, Any]:
    ok = count > 0 and len(results) == count and all(item["returncode"] == 0 and item["loaded"] for item in results)
    domains: list[str] = []
    for result in results:
        task_dir = Path(str(result.get("task_dir", "")))
        scenario_path = task_dir / "scenario_model.json"
        if scenario_path.is_file():
            try:
                loaded = json.loads(scenario_path.read_text(encoding="utf-8"))
                domain = str(loaded.get("domain", "") or "").strip()
                if domain:
                    domains.append(domain)
            except Exception:
                pass
    summary = {
        "ok": ok,
        "count": count,
        "tool_store": str(tool_store_path),
        "complexity_profile": complexity_profile,
        "planner_context_mode": planner_context_mode,
        "planner_context_max_chars": planner_context_max_chars,
        "planner_repair_include_original_prompt": planner_repair_include_original_prompt,
        "domains": domains,
        "distinct_domain_count": len(set(domains)),
        "results": results,
    }
    (output_root / "summary.json").write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return summary


def _run_tasks(
    args: argparse.Namespace,
    tool_store_path: Path,
    output_root: Path,
    scenario_files: Sequence[ScenarioFile],
) -> list[dict[str, Any]]:
    count = len(scenario_files)
    results_by_index: list[dict[str, Any] | None] = [None] * count
    task_id_start = int(args.task_id_start or args.start_index)
    tasks = list(enumerate(zip(range(task_id_start, task_id_start + count), scenario_files)))
    next_task = 0
    stop_scheduling = False

    with ThreadPoolExecutor(max_workers=args.workers) as executor:
        futures: dict[Future[dict[str, Any]], int] = {}
        future_scenarios: dict[Future[dict[str, Any]], ScenarioFile] = {}

        def submit_next() -> None:
            nonlocal next_task
            result_slot, (task_index, scenario_file) = tasks[next_task]
            next_task += 1
            future = executor.submit(_run_one, args, tool_store_path, output_root, task_index, scenario_file)
            futures[future] = result_slot
            future_scenarios[future] = scenario_file

        for _ in range(min(args.workers, count)):
            submit_next()

        try:
            while futures:
                done, _pending = wait(futures, return_when=FIRST_COMPLETED)
                for future in done:
                    result_slot = futures.pop(future)
                    scenario_file = future_scenarios.pop(future)
                    try:
                        result = future.result()
                    except BaseException as exc:
                        task_index = task_id_start + result_slot
                        result = _task_failure_result(output_root, task_index, exc, scenario_file)
                    _attach_scenario_metadata(result, scenario_file)
                    results_by_index[result_slot] = result
                    completed_results = _ordered_completed_results(results_by_index)
                    _write_summary(
                        output_root,
                        count=count,
                        tool_store_path=tool_store_path,
                        complexity_profile=args.complexity_profile,
                        planner_context_mode=args.planner_context_mode,
                        planner_context_max_chars=args.planner_context_max_chars,
                        planner_repair_include_original_prompt=args.planner_repair_include_original_prompt,
                        results=completed_results,
                    )
                    if result["returncode"] != 0 and not args.keep_going:
                        stop_scheduling = True

                while not stop_scheduling and next_task < count and len(futures) < args.workers:
                    submit_next()
        except KeyboardInterrupt:
            _terminate_all_processes()
            for future in futures:
                future.cancel()
            future_scenarios.clear()
            raise

    return _ordered_completed_results(results_by_index)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    load_env()

    output_root = Path(args.output_dir).resolve()
    output_root.mkdir(parents=True, exist_ok=True)
    tool_store_path = _resolve_tool_store_path(args.tool_store)
    scenario_dir = _resolve_scenario_dir(args.scenario_dir)
    scenario_files = _discover_scenario_files(scenario_dir)
    start_offset = args.start_index - 1
    selected_scenario_files = scenario_files[start_offset : start_offset + max(0, args.count)]
    count = len(selected_scenario_files)
    if not selected_scenario_files:
        _write_summary(
            output_root,
            count=0,
            tool_store_path=tool_store_path,
            complexity_profile=args.complexity_profile,
            planner_context_mode=args.planner_context_mode,
            planner_context_max_chars=args.planner_context_max_chars,
            planner_repair_include_original_prompt=args.planner_repair_include_original_prompt,
            results=[],
        )
        print(
            json.dumps(
                {
                    "ok": False,
                    "error": "no generated scenario files selected",
                    "scenario_dir": str(scenario_dir),
                    "available_scenario_count": len(scenario_files),
                    "start_index": args.start_index,
                    "requested_count": args.count,
                    "summary": str(output_root / "summary.json"),
                },
                indent=2,
            )
        )
        return 2

    prereq = {
        "tool_store": _tool_store_preflight(tool_store_path, tool_count=args.tool_count),
        "planner_image": _planner_image_preflight(args.planner_docker_image),
        "planner_env": _required_env_status(),
    }
    (output_root / "preflight.json").write_text(json.dumps(prereq, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    missing = [key for key, present in prereq["planner_env"].items() if not present]
    image_ok = prereq["planner_image"]["image_inspect"]["returncode"] == 0
    opencode_ok = prereq["planner_image"]["opencode_version"]["returncode"] == 0
    tool_store_ok = bool(prereq["tool_store"]["valid"]) and bool(prereq["tool_store"]["enough_ready_external_tools"])
    if missing or not image_ok or not opencode_ok or not tool_store_ok:
        print(
            json.dumps(
                {
                    "ok": False,
                    "missing": missing,
                    "tool_store": str(tool_store_path),
                    "tool_store_ok": tool_store_ok,
                    "docker_image": args.planner_docker_image,
                    "image_ok": image_ok,
                    "opencode_ok": opencode_ok,
                    "preflight": str(output_root / "preflight.json"),
                },
                indent=2,
            )
        )
        return 2

    try:
        results = _run_tasks(args, tool_store_path, output_root, selected_scenario_files)
    except KeyboardInterrupt:
        completed_results: list[dict[str, Any]] = []
        summary_path = output_root / "summary.json"
        if summary_path.is_file():
            try:
                loaded = json.loads(summary_path.read_text(encoding="utf-8"))
                raw_results = loaded.get("results")
                if isinstance(raw_results, list):
                    completed_results = [item for item in raw_results if isinstance(item, dict)]
            except Exception:
                completed_results = []
        _write_summary(
            output_root,
            count=count,
            tool_store_path=tool_store_path,
            complexity_profile=args.complexity_profile,
            planner_context_mode=args.planner_context_mode,
            planner_context_max_chars=args.planner_context_max_chars,
            planner_repair_include_original_prompt=args.planner_repair_include_original_prompt,
            results=completed_results,
        )
        print(json.dumps({"ok": False, "summary": str(summary_path), "interrupted": True}, indent=2))
        return 130

    summary = _write_summary(
        output_root,
        count=count,
        tool_store_path=tool_store_path,
        complexity_profile=args.complexity_profile,
        planner_context_mode=args.planner_context_mode,
        planner_context_max_chars=args.planner_context_max_chars,
        planner_repair_include_original_prompt=args.planner_repair_include_original_prompt,
        results=results,
    )
    ok = bool(summary["ok"])
    print(json.dumps({"ok": ok, "summary": str(output_root / "summary.json")}, indent=2))
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())

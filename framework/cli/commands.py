from __future__ import annotations

import argparse
import json
import os
import signal
import sys
import time
from pathlib import Path
from typing import Any

import yaml

from framework.core.factory import OrchestratorFactory
from framework.core.helpers import temporary_environment
from framework.core.orchestrator import launch_once, write_report
from framework.core.tool_store import load_tool_store_manifest, resolve_manifest_tool_env, selected_tool_names_from_task
from framework.models.specs import EvaluatorResult
from framework.tasks.loader import load_task_bundle


_ENV_BOOTSTRAPPED = False
_LEGACY_RUNTIME_TOOL_FLAGS = {
    "tools_file": "--tools-file",
    "target_tools_file": "--target-tools-file",
    "attack_tools_file": "--attack-tools-file",
    "capabilities_file": "--capabilities-file",
    "capabilities_dir": "--capabilities-dir",
}
_RUNTIME_TOOL_MIGRATION_ERROR = (
    "legacy runtime tool flags are no longer supported: {flags}; managed tool loading now uses "
    "--tool-store plus task/tool_use_graph.json"
)
def _workspace_root() -> Path:
    return Path(__file__).resolve().parents[2]


def _default_output_root() -> Path:
    return _workspace_root() / "outputs" / "runs"


def _env_file_candidates() -> list[Path]:
    root = _workspace_root()
    return [root / ".env", root.parent / ".env"]


def _strip_env_quotes(value: str) -> str:
    text = value.strip()
    if len(text) >= 2 and text[0] == text[-1] and text[0] in {'"', "'"}:
        return text[1:-1]
    return text


def _load_env_file(path: Path) -> None:
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except FileNotFoundError:
        return

    for raw_line in lines:
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        if line.startswith("export "):
            line = line[len("export "):].strip()
        key, value = line.split("=", 1)
        key = key.strip()
        if not key:
            continue
        os.environ.setdefault(key, _strip_env_quotes(value))


def load_env() -> None:
    global _ENV_BOOTSTRAPPED
    if _ENV_BOOTSTRAPPED:
        return

    for path in _env_file_candidates():
        if path.is_file():
            _load_env_file(path)

    if not os.environ.get("OPENAI_API_KEY") and os.environ.get("OPENAI_KEY"):
        os.environ["OPENAI_API_KEY"] = os.environ["OPENAI_KEY"]

    runner_api_key = (
        os.environ.get("TARGET_API_KEY")
        or os.environ.get("OPENAI_API_KEY")
        or os.environ.get("ANTHROPIC_API_KEY")
        or ""
    )
    runner_base_url = (
        os.environ.get("TARGET_BASE_URL")
        or os.environ.get("OPENAI_BASE_URL")
        or os.environ.get("ANTHROPIC_BASE_URL")
        or ""
    )
    runner_model = (
        os.environ.get("TARGET_MODEL")
        or os.environ.get("OPENAI_MODEL")
        or os.environ.get("DEFAULT_MODEL")
        or ""
    )
    judge_api_key = (
        os.environ.get("JUDGE_API_KEY")
        or os.environ.get("OPENAI_API_KEY")
        or os.environ.get("ANTHROPIC_API_KEY")
        or ""
    )
    judge_base_url = (
        os.environ.get("JUDGE_BASE_URL")
        or os.environ.get("OPENAI_BASE_URL")
        or os.environ.get("ANTHROPIC_BASE_URL")
        or ""
    )
    judge_model = (
        os.environ.get("JUDGE_MODEL")
        or os.environ.get("OPENAI_MODEL")
        or os.environ.get("DEFAULT_MODEL")
        or ""
    )
    attack_api_key = (
        os.environ.get("ATTACK_API_KEY")
        or os.environ.get("OPENAI_API_KEY")
        or os.environ.get("ANTHROPIC_API_KEY")
        or ""
    )
    attack_base_url = (
        os.environ.get("ATTACK_BASE_URL")
        or os.environ.get("OPENAI_BASE_URL")
        or os.environ.get("ANTHROPIC_BASE_URL")
        or ""
    )
    attack_model = (
        os.environ.get("ATTACK_MODEL")
        or os.environ.get("OPENAI_MODEL")
        or os.environ.get("DEFAULT_MODEL")
        or ""
    )

    if runner_api_key:
        os.environ.setdefault("TARGET_API_KEY", runner_api_key)
    if runner_base_url:
        os.environ.setdefault("TARGET_BASE_URL", runner_base_url)
    if runner_model:
        os.environ.setdefault("TARGET_MODEL", runner_model)
    if judge_api_key:
        os.environ.setdefault("JUDGE_API_KEY", judge_api_key)
    if judge_base_url:
        os.environ.setdefault("JUDGE_BASE_URL", judge_base_url)
    if judge_model:
        os.environ.setdefault("JUDGE_MODEL", judge_model)
    if attack_api_key:
        os.environ.setdefault("ATTACK_API_KEY", attack_api_key)
    if attack_base_url:
        os.environ.setdefault("ATTACK_BASE_URL", attack_base_url)
    if attack_model:
        os.environ.setdefault("ATTACK_MODEL", attack_model)

    _ENV_BOOTSTRAPPED = True


def _load_harness_config_env(harness_path: str | None) -> None:
    _ = harness_path


def _parse_comma_list(value: str | None) -> list[str]:
    if not value:
        return []
    return [item.strip() for item in value.split(",") if item.strip()]


def _parse_key_value_list(value: str | None) -> dict[str, str]:
    result: dict[str, str] = {}
    if not value:
        return result

    for raw_item in value.split(","):
        item = raw_item.strip()
        if not item or "=" not in item:
            continue
        key, val = item.split("=", 1)
        key = key.strip()
        val = val.strip()
        if key and val:
            result[key] = val
    return result


def _legacy_runtime_flag_used(value: Any) -> bool:
    if isinstance(value, list):
        return any(str(item or "").strip() for item in value)
    return bool(str(value or "").strip())


def _reject_legacy_runtime_tool_flags(parser: argparse.ArgumentParser, args: argparse.Namespace) -> None:
    used = [
        flag
        for dest, flag in _LEGACY_RUNTIME_TOOL_FLAGS.items()
        if _legacy_runtime_flag_used(getattr(args, dest, None))
    ]
    if used:
        parser.error(_RUNTIME_TOOL_MIGRATION_ERROR.format(flags=", ".join(used)))


def _load_mapping_file(path: str | None) -> dict[str, Any]:
    if not path:
        return {}

    target = Path(path)
    if not target.exists() or not target.is_file():
        raise FileNotFoundError(f"config file not found: {path}")

    text = target.read_text(encoding="utf-8")
    if target.suffix.lower() == ".json":
        loaded = json.loads(text)
    else:
        loaded = yaml.safe_load(text)

    if isinstance(loaded, dict):
        return loaded
    return {}


def _default_config_path(file_name: str) -> str:
    path = _workspace_root() / "configs" / file_name
    if path.exists() and path.is_file():
        return str(path)
    return ""


def _load_role_config(path: str | None, role_name: str) -> dict[str, Any]:
    data = _load_mapping_file(path)
    scoped = data.get(role_name)
    if isinstance(scoped, dict):
        return dict(scoped)
    return data if isinstance(data, dict) else {}



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


def _apply_tool_manifest(role_config: dict[str, Any], *manifests: dict[str, Any]) -> dict[str, Any]:
    result = dict(role_config)
    merged_tools = _merge_tool_lists(result.get("tools"), *(manifest.get("tools") for manifest in manifests))
    if merged_tools:
        result["tools"] = merged_tools

    guides = [str(result.get("tool_guide_markdown", "") or "").strip()]
    guides.extend(str(manifest.get("tool_guide_markdown", "") or "").strip() for manifest in manifests)
    merged_guide = "\n\n".join(part for part in guides if part)
    if merged_guide:
        result["tool_guide_markdown"] = merged_guide
    return result


def _apply_attacker_tool_manifests(bundle, *manifests: dict[str, Any]) -> None:
    attacker = getattr(bundle, "attacker", None)
    if attacker is None:
        return
    merged_tools = _merge_tool_lists(attacker.tools, *(manifest.get("tools") for manifest in manifests))
    if merged_tools:
        attacker.tools = merged_tools
    guides = [str(attacker.tool_guide_markdown or "").strip()]
    guides.extend(str(manifest.get("tool_guide_markdown", "") or "").strip() for manifest in manifests)
    merged_guide = "\n\n".join(part for part in guides if part)
    if merged_guide:
        attacker.tool_guide_markdown = merged_guide


def _filter_named_items_to_selected(raw_items: Any, selected_names: set[str]) -> list[Any]:
    if not isinstance(raw_items, list):
        return []
    if not selected_names:
        return list(raw_items)
    result: list[Any] = []
    for item in raw_items:
        if isinstance(item, str):
            name = item.strip()
        elif isinstance(item, dict):
            name = str(item.get("name", "") or "").strip()
        else:
            name = ""
        if name and name in selected_names:
            result.append(item)
    return result


def _filter_role_config_to_selected(role_config: dict[str, Any], selected_names: set[str]) -> dict[str, Any]:
    if not selected_names:
        return role_config
    result = dict(role_config)
    if "tools" in result:
        result["tools"] = _filter_named_items_to_selected(result.get("tools"), selected_names)
    return result


def _filter_attacker_tools_to_selected(bundle, selected_names: set[str]) -> None:
    if not selected_names:
        return
    attacker = getattr(bundle, "attacker", None)
    if attacker is None:
        return
    attacker.tools = _filter_named_items_to_selected(attacker.tools, selected_names)


def _container_instruction_path(task_root: Path, instruction_path: str | None) -> str | None:
    if not instruction_path:
        return None

    path = Path(instruction_path)
    try:
        resolved = path.resolve()
        rel = resolved.relative_to(task_root.resolve())
        return f"/task/{rel.as_posix()}"
    except Exception:
        return instruction_path


def _make_run_id(prefix: str = "run") -> str:
    return f"{prefix}-{int(time.time())}"


def _safe_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except Exception:
        return default


def _print_result(result: EvaluatorResult) -> None:
    metadata = result.metadata if isinstance(result.metadata, dict) else {}
    compact_metadata: dict[str, Any] = {}
    for key in ("evaluator", "runner_failure"):
        value = metadata.get(key)
        if value not in (None, {}, []):
            compact_metadata[key] = value
    raw_results = metadata.get("results")
    if isinstance(raw_results, dict):
        compact_results: dict[str, Any] = {}
        for name, value in raw_results.items():
            if not isinstance(value, dict):
                continue
            compact_results[name] = {
                "decision": value.get("decision"),
                "score": value.get("score"),
                "subscores": value.get("subscores", {}),
            }
        if compact_results:
            compact_metadata["evaluators"] = compact_results

    inspect_section = metadata.get("inspect")
    if isinstance(inspect_section, dict) and inspect_section:
        compact_inspect: dict[str, Any] = {}
        runners = inspect_section.get("runners")
        if isinstance(runners, dict) and runners:
            compact_inspect["runners"] = runners
        task_container = inspect_section.get("task_container")
        if isinstance(task_container, dict) and task_container:
            compact_task_container = {
                key: value
                for key, value in task_container.items()
                if key.endswith("_file")
            }
            if compact_task_container:
                compact_inspect["task_container"] = compact_task_container
        evaluator = inspect_section.get("evaluator")
        if isinstance(evaluator, dict) and evaluator:
            compact_inspect["evaluator"] = evaluator
        runtime_log_file = inspect_section.get("runtime_log_file")
        if runtime_log_file:
            compact_inspect["runtime_log_file"] = runtime_log_file
        if compact_inspect:
            compact_metadata["inspect"] = compact_inspect

    payload = {
        "run_id": result.run_id,
        "decision": result.decision,
        "score": _safe_float(result.score),
        "subscores": result.subscores,
        "rationale": result.rationale,
        "metadata": compact_metadata,
    }
    print(json.dumps(payload, ensure_ascii=False, indent=2))


def _truncate_debug_text(text: str, limit: int = 1200) -> str:
    if len(text) <= limit:
        return text
    remaining = len(text) - limit
    return text[:limit] + f"\n...[truncated {remaining} chars]"


def _read_optional_text(path: Path) -> str | None:
    if not path.is_file():
        return None
    try:
        return path.read_text(encoding="utf-8")
    except Exception:
        return None


def _read_optional_json(path: Path) -> dict[str, Any] | None:
    text = _read_optional_text(path)
    if text is None:
        return None
    try:
        data = json.loads(text)
    except Exception:
        return None
    return data if isinstance(data, dict) else None


def _attach_runner_debug(result: EvaluatorResult, run_dir: Path) -> None:
    runner_root = run_dir / "runner_outputs"
    attacker_root = run_dir / "attacker_outputs"
    control_root = run_dir / "control" / "target"
    debug_section = result.metadata.get("debug")
    if not isinstance(debug_section, dict):
        debug_section = {}
    inspect_section = result.metadata.get("inspect")
    if not isinstance(inspect_section, dict):
        inspect_section = {}

    debug_runner_outputs: dict[str, dict[str, Any]] = {}
    inspect_runners: dict[str, dict[str, Any]] = {}

    if runner_root.is_dir():
        for role_dir in sorted(path for path in runner_root.iterdir() if path.is_dir()):
            role = role_dir.name
            entry: dict[str, Any] = {}
            inspect_entry: dict[str, Any] = {}

            command_path = role_dir / "command.sh"
            command_text = _read_optional_text(command_path)
            if command_text is not None:
                entry["command"] = command_text.strip()
                entry["command_file"] = str(command_path)
                inspect_entry["command_file"] = str(command_path)
                result.artifacts.setdefault(f"{role}_command", str(command_path))

            stdout_path = role_dir / "stdout.txt"
            stdout_text = _read_optional_text(stdout_path)
            if stdout_text is not None:
                entry["stdout_preview"] = _truncate_debug_text(stdout_text)
                entry["stdout_file"] = str(stdout_path)
                inspect_entry["output_file"] = str(stdout_path)
                result.artifacts.setdefault(f"{role}_stdout", str(stdout_path))

            stderr_path = role_dir / "stderr.txt"
            stderr_text = _read_optional_text(stderr_path)
            if stderr_text is not None:
                entry["stderr_preview"] = _truncate_debug_text(stderr_text)
                entry["stderr_file"] = str(stderr_path)
                inspect_entry["stderr_file"] = str(stderr_path)
                result.artifacts.setdefault(f"{role}_stderr", str(stderr_path))

            status_path = role_dir / "status.json"
            status = _read_optional_json(status_path)
            if status is not None:
                entry["status"] = status
                entry["status_file"] = str(status_path)
                inspect_entry["status_file"] = str(status_path)
                result.artifacts.setdefault(f"{role}_status", str(status_path))

            prepare_summary_path = role_dir / "prepared" / "summary.json"
            prepare_summary = _read_optional_json(prepare_summary_path)
            if prepare_summary is not None:
                entry["prepare"] = prepare_summary
                entry["prepare_summary_file"] = str(prepare_summary_path)
                inspect_entry["prepare_summary_file"] = str(prepare_summary_path)
                result.artifacts.setdefault(f"{role}_prepare_summary", str(prepare_summary_path))

            for label in ("before_run", "after_run"):
                workspace_ls_path = role_dir / f"workspace_{label}_ls.txt"
                workspace_ls_text = _read_optional_text(workspace_ls_path)
                if workspace_ls_text is not None:
                    entry[f"workspace_{label}_ls_preview"] = _truncate_debug_text(workspace_ls_text)
                    entry[f"workspace_{label}_ls_file"] = str(workspace_ls_path)
                    inspect_entry[f"workspace_{label}_ls_file"] = str(workspace_ls_path)
                    result.artifacts.setdefault(f"{role}_workspace_{label}_ls", str(workspace_ls_path))

            if entry:
                debug_runner_outputs[role] = entry
            if inspect_entry:
                inspect_runners[role] = inspect_entry

    if debug_runner_outputs:
        debug_section["runner_outputs"] = debug_runner_outputs
        result.metadata["debug"] = debug_section
    if inspect_runners:
        inspect_section["runners"] = inspect_runners
        result.metadata["inspect"] = inspect_section

    debug_attackers: dict[str, dict[str, Any]] = {}
    inspect_attackers: dict[str, dict[str, Any]] = {}
    if attacker_root.is_dir():
        for attacker_dir in sorted(path for path in attacker_root.iterdir() if path.is_dir()):
            name = attacker_dir.name
            entry: dict[str, Any] = {}
            inspect_entry: dict[str, Any] = {}
            for label, file_name in (("command", "command.sh"), ("stdout", "stdout.txt"), ("stderr", "stderr.txt")):
                file_path = attacker_dir / file_name
                text = _read_optional_text(file_path)
                if text is None:
                    continue
                if label in {"stdout", "stderr"}:
                    entry[f"{label}_preview"] = _truncate_debug_text(text)
                else:
                    entry[label] = text.strip()
                entry[f"{label}_file"] = str(file_path)
                inspect_entry[f"{label}_file"] = str(file_path)
                result.artifacts.setdefault(f"attacker_{name}_{label}", str(file_path))
            status_path = attacker_dir / "status.json"
            status = _read_optional_json(status_path)
            if status is not None:
                entry["status"] = status
                entry["status_file"] = str(status_path)
                inspect_entry["status_file"] = str(status_path)
                result.artifacts.setdefault(f"attacker_{name}_status", str(status_path))
            result_path = attacker_dir / "result.json"
            payload = _read_optional_json(result_path)
            if payload is not None:
                entry["result"] = payload
                entry["result_file"] = str(result_path)
                inspect_entry["result_file"] = str(result_path)
                result.artifacts.setdefault(f"attacker_{name}_result", str(result_path))
            prepare_summary_path = attacker_dir / "prepared" / "summary.json"
            prepare_summary = _read_optional_json(prepare_summary_path)
            if prepare_summary is not None:
                entry["prepare"] = prepare_summary
                entry["prepare_summary_file"] = str(prepare_summary_path)
                inspect_entry["prepare_summary_file"] = str(prepare_summary_path)
                result.artifacts.setdefault(f"attacker_{name}_prepare_summary", str(prepare_summary_path))
            for label in ("before_run", "after_run"):
                workspace_ls_path = attacker_dir / f"workspace_{label}_ls.txt"
                workspace_ls_text = _read_optional_text(workspace_ls_path)
                if workspace_ls_text is None:
                    continue
                entry[f"workspace_{label}_ls_preview"] = _truncate_debug_text(workspace_ls_text)
                entry[f"workspace_{label}_ls_file"] = str(workspace_ls_path)
                inspect_entry[f"workspace_{label}_ls_file"] = str(workspace_ls_path)
                result.artifacts.setdefault(f"attacker_{name}_workspace_{label}_ls", str(workspace_ls_path))
            for label in ("before_run", "after_run"):
                control_ls_path = attacker_dir / f"control_{label}_ls.txt"
                control_ls_text = _read_optional_text(control_ls_path)
                if control_ls_text is None:
                    continue
                entry[f"control_{label}_ls_preview"] = _truncate_debug_text(control_ls_text)
                entry[f"control_{label}_ls_file"] = str(control_ls_path)
                inspect_entry[f"control_{label}_ls_file"] = str(control_ls_path)
                result.artifacts.setdefault(f"attacker_{name}_control_{label}_ls", str(control_ls_path))
            target_control_snapshot_path = attacker_dir / "target_control_snapshot.json"
            target_control_snapshot = _read_optional_json(target_control_snapshot_path)
            if target_control_snapshot is not None:
                entry["target_control_snapshot"] = target_control_snapshot
                entry["target_control_snapshot_file"] = str(target_control_snapshot_path)
                inspect_entry["target_control_snapshot_file"] = str(target_control_snapshot_path)
                result.artifacts.setdefault(f"attacker_{name}_target_control_snapshot", str(target_control_snapshot_path))
            if entry:
                debug_attackers[name] = entry
            if inspect_entry:
                inspect_attackers[name] = inspect_entry

    if debug_attackers:
        debug_section["attacker_outputs"] = debug_attackers
        result.metadata["debug"] = debug_section
    if inspect_attackers:
        inspect_section["attackers"] = inspect_attackers
        result.metadata["inspect"] = inspect_section

    task_container_section: dict[str, Any] = {}
    task_container_dir = run_dir / "task_container"
    if task_container_dir.is_dir():
        for label in ("prepared", "before_target", "after_target", "before_attack", "after_attack"):
            workspace_path = task_container_dir / f"workspace_{label}_ls.txt"
            workspace_text = _read_optional_text(workspace_path)
            if workspace_text is not None:
                task_container_section[f"workspace_{label}_ls_file"] = str(workspace_path)
                debug_section[f"task_workspace_{label}_ls_preview"] = _truncate_debug_text(workspace_text)
                result.artifacts.setdefault(f"task_workspace_{label}_ls", str(workspace_path))

        workspace_flow_path = task_container_dir / "workspace_flow.json"
        workspace_flow = _read_optional_json(workspace_flow_path)
        if workspace_flow is not None:
            task_container_section["workspace_flow_file"] = str(workspace_flow_path)
            task_container_section["workspace_flow"] = workspace_flow
            result.artifacts.setdefault("workspace_flow", str(workspace_flow_path))

    if task_container_section:
        inspect_section["task_container"] = task_container_section
        result.metadata["inspect"] = inspect_section

    evaluator_section: dict[str, Any] = {}
    evaluator_input_dir = run_dir / "evaluator_inputs"
    if evaluator_input_dir.is_dir():
        for name in ("task_snapshot", "service_snapshots"):
            path = evaluator_input_dir / f"{name}.json"
            if path.is_file():
                evaluator_section[f"{name}_file"] = str(path)
                result.artifacts.setdefault(f"evaluator_{name}", str(path))
        trace_path = run_dir / "trace.jsonl"
        if trace_path.is_file():
            evaluator_section["trace_file"] = str(trace_path)

    llm_judge_dir = run_dir / "evaluator_outputs" / "llm_judge"
    if llm_judge_dir.is_dir():
        for name in ("request", "response"):
            path = llm_judge_dir / f"{name}.json"
            if path.is_file():
                evaluator_section[f"judge_{name}_file"] = str(path)
        for name in ("response", "system_prompt", "user_prompt"):
            path = llm_judge_dir / f"{name}.txt"
            if path.is_file():
                evaluator_section[f"judge_{name}_text_file"] = str(path)

    if evaluator_section:
        inspect_section["evaluator"] = evaluator_section
        result.metadata["inspect"] = inspect_section

    control_section: dict[str, Any] = {}
    if control_root.is_dir():
        for name in ("base", "final"):
            path = control_root / name
            if path.is_dir():
                control_section[f"{name}_dir"] = str(path)
        materialization_path = control_root / "materialization.json"
        materialization = _read_optional_json(materialization_path)
        if materialization is not None:
            control_section["materialization_file"] = str(materialization_path)
            control_section["materialization"] = materialization
            result.artifacts.setdefault("target_control_materialization", str(materialization_path))
        snapshots_dir = control_root / "snapshots"
        if snapshots_dir.is_dir():
            for name in ("base", "final", "materialized"):
                path = snapshots_dir / f"{name}.json"
                payload = _read_optional_json(path)
                if payload is None:
                    continue
                control_section[f"{name}_snapshot_file"] = str(path)
                result.artifacts.setdefault(f"target_control_{name}_snapshot", str(path))

    if control_section:
        inspect_section["target_control"] = control_section
        result.metadata["inspect"] = inspect_section

    runtime_log_path = run_dir / "runtime.log"
    if runtime_log_path.is_file():
        debug_section["runtime_log_file"] = str(runtime_log_path)
        inspect_section["runtime_log_file"] = str(runtime_log_path)
        result.artifacts.setdefault("runtime_log", str(runtime_log_path))
        result.metadata["debug"] = debug_section
        result.metadata["inspect"] = inspect_section


def _resolved_harness_path(value: str | None) -> str | None:
    candidate = str(value or "").strip()
    if candidate:
        return str(Path(candidate).resolve())
    env_value = os.environ.get("OPENART_EVAL_HARNESS", "").strip()
    if env_value:
        return str(Path(env_value).resolve())
    return None


def _resolved_eval_env() -> dict[str, str]:
    return _parse_key_value_list(os.environ.get("OPENART_EVAL_ENV", ""))


class _SignalCleanup:
    def __init__(self, orchestrator: Any) -> None:
        self.orchestrator = orchestrator
        self._previous: dict[int, Any] = {}
        self._cleaned = False

    def __enter__(self):
        for signum in (signal.SIGINT, signal.SIGTERM):
            self._previous[signum] = signal.getsignal(signum)
            signal.signal(signum, self._handle)
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        for signum, previous in self._previous.items():
            signal.signal(signum, previous)

    def _handle(self, signum, frame) -> None:
        if not self._cleaned:
            self._cleaned = True
            try:
                self.orchestrator.teardown()
            except Exception:
                pass
        raise SystemExit(128 + int(signum))


def run_main(argv: list[str] | None = None) -> int:
    """Run a task using the full Orchestrator flow."""
    load_env()
    parser = argparse.ArgumentParser(prog="framework.cli run")
    parser.add_argument("--task", required=True, help="Task directory path")
    parser.add_argument("--attacker-config", default="", help="Optional attacker config yaml/json applied after loading the task")
    parser.add_argument("--run-id", default=None, help="Optional run id")
    parser.add_argument("--output-dir", default=None, help="Output root directory")
    parser.add_argument("--report", default=None, help="Optional report json path")
    parser.add_argument(
        "--task-image",
        default=None,
        help="Task container image (default: openart/task-base:latest). "
             "If Dockerfile exists in task, builds from Dockerfile instead.",
    )
    parser.add_argument(
        "--skip-build",
        action="store_true",
        help="Skip building task container image (use pre-built image)",
    )
    parser.add_argument(
        "--evaluator-harness",
        dest="evaluator_harness",
        default="",
        help="Evaluator harness directory with config.py/common.py/scoring.py for service+evaluator setup",
    )
    parser.add_argument(
        "--harness",
        dest="evaluator_harness",
        default=argparse.SUPPRESS,
        help=argparse.SUPPRESS,
    )
    parser.add_argument(
        "--eval-strategy",
        choices=["auto", "deterministic", "llm", "both"],
        default="auto",
        help="Evaluator strategy: auto, deterministic only, llm only, or both",
    )
    parser.add_argument(
        "--runner-framework",
        default="",
        help="Runner framework override (hermes, nanobot, pi, prompt_cli). Use target.surface_family and attack_surfaces for native surfaces.",
    )
    parser.add_argument(
        "--runner-model",
        default="",
        help="Runner model override",
    )
    parser.add_argument(
        "--target-config",
        default="",
        help="Path to target runner config file (yaml/json)",
    )
    parser.add_argument(
        "--attack-config",
        default="",
        help="Deprecated attacker runner config path; attacker config now lives in task.attacker",
    )
    parser.add_argument(
        "--tools-file",
        default="",
        help=argparse.SUPPRESS,
    )
    parser.add_argument(
        "--tool-store",
        default="",
        help="Path to a managed OpenART tool store. Defaults to the sibling openart-tools directory when tool_use_graph.json selects tools.",
    )
    parser.add_argument(
        "--capabilities-file",
        action="append",
        default=[],
        help=argparse.SUPPRESS,
    )
    parser.add_argument(
        "--capabilities-dir",
        action="append",
        default=[],
        help=argparse.SUPPRESS,
    )
    parser.add_argument(
        "--target-tools-file",
        default="",
        help=argparse.SUPPRESS,
    )
    parser.add_argument(
        "--attack-tools-file",
        default="",
        help=argparse.SUPPRESS,
    )
    parser.add_argument(
        "--skip-attacker",
        action="store_true",
        help="Do not launch the attacker even if the task defines one",
    )
    parser.add_argument(
        "--max-iterations",
        type=int,
        default=1,
        help="Maximum number of target attempts per task run (default: 1)",
    )
    parser.add_argument(
        "--adaptive-iterations",
        action="store_true",
        default=True,
        help="Only retry another target iteration when the current result looks incomplete or partially successful (default: on)",
    )
    parser.add_argument(
        "--no-adaptive-iterations",
        action="store_true",
        help="Disable adaptive iterations",
    )
    parser.add_argument(
        "--target-timeout-seconds",
        type=int,
        default=0,
        help="Minimum timeout for each target runner invocation in seconds",
    )
    parser.add_argument(
        "--attacker-timeout-seconds",
        type=int,
        default=0,
        help="Minimum timeout for each attacker invocation in seconds",
    )
    args = parser.parse_args(argv)
    _reject_legacy_runtime_tool_flags(parser, args)

    # Load task bundle
    bundle = load_task_bundle(args.task, attacker_config_path=args.attacker_config or None)
    tool_graph_path = Path(bundle.root_dir) / "tool_use_graph.json"
    has_tool_graph = tool_graph_path.is_file()

    # Generate run ID and output directory
    run_id = args.run_id or _make_run_id(bundle.task_id)
    output_root = Path(args.output_dir).resolve() if args.output_dir else _default_output_root().resolve()
    run_dir = output_root / run_id
    run_dir.mkdir(parents=True, exist_ok=True)

    # Build orchestrator using factory
    eval_env = _resolved_eval_env()
    harness_path = _resolved_harness_path(args.evaluator_harness)
    _load_harness_config_env(harness_path)

    target_config_path = args.target_config or _default_config_path("target-configs/target.yaml")
    target_config = _load_role_config(target_config_path, "target")
    selected_tool_names = selected_tool_names_from_task(bundle.root_dir) if has_tool_graph else set()
    managed_tool_manifest: dict[str, Any] = {}
    managed_tool_env: dict[str, str] = {}
    if args.tool_store or has_tool_graph:
        selected_names = selected_tool_names if has_tool_graph else None
        candidate_manifest = load_tool_store_manifest(args.tool_store or None, selected_names=selected_names)
        if candidate_manifest.get("tools"):
            managed_tool_manifest, managed_tool_env = resolve_manifest_tool_env(candidate_manifest, os.environ)
    env_updates = {"OPENART_EVAL_STRATEGY": args.eval_strategy}
    if harness_path:
        env_updates["OPENART_EVAL_HARNESS"] = harness_path
    if eval_env:
        env_updates["OPENART_EVAL_ENV"] = ",".join(f"{key}={value}" for key, value in eval_env.items())

    target_config = _apply_tool_manifest(
        target_config,
        managed_tool_manifest,
    )
    _apply_attacker_tool_manifests(
        bundle,
        managed_tool_manifest,
    )
    if has_tool_graph:
        target_config = _filter_role_config_to_selected(target_config, selected_tool_names)
        _filter_attacker_tools_to_selected(bundle, selected_tool_names)

    removals = ["OPENART_EVAL_HARNESS", "OPENART_EVAL_ENV"]
    with temporary_environment(env_updates, removals=removals):
        factory = OrchestratorFactory(
            bundle=bundle,
            output_dir=str(run_dir),
            run_id=run_id,
            task_image=args.task_image,
            skip_build=args.skip_build,
            evaluator_harness=harness_path,
            evaluator_env=eval_env,
            managed_tool_env=managed_tool_env,
            runner_framework=args.runner_framework or None,
            runner_model=args.runner_model or None,
            target_config=target_config,
            target_config_path=target_config_path,
            eval_strategy=args.eval_strategy,
            skip_attacker=args.skip_attacker,
            max_iterations=max(1, int(args.max_iterations or 1)),
            adaptive_iterations=args.adaptive_iterations and not args.no_adaptive_iterations,
            target_timeout_seconds=max(0, int(args.target_timeout_seconds or 0)),
            attacker_timeout_seconds=max(0, int(args.attacker_timeout_seconds or 0)),
        )
        orchestrator = factory.build()

        with _SignalCleanup(orchestrator):
            result = launch_once(
                orchestrator,
                run_id=run_id,
                target_instruction_file=_container_instruction_path(Path(bundle.root_dir), bundle.target_instruction_path) or bundle.target_instruction_path,
                attack_instruction_file=(
                    None
                    if args.skip_attacker
                    else _container_instruction_path(Path(bundle.root_dir), bundle.attacker_instruction_path)
                ),
            )

    # Write report
    _attach_runner_debug(result, run_dir)
    report_path = Path(args.report).resolve() if args.report else run_dir / "result.json"
    write_report(str(report_path), result)

    # Print result
    _print_result(result)
    return 1 if "runner_failure" in result.metadata else 0


def main(argv: list[str] | None = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    if not argv:
        print("usage: python -m framework.cli run [args]", file=sys.stderr)
        return 2

    command = argv[0]
    tail = argv[1:]
    if command == "run":
        return run_main(tail)

    print(f"unknown command: {command}", file=sys.stderr)
    return 2

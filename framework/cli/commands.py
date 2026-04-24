from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

import yaml

from framework.components.evaluators import CompositeEvaluator, DeterministicEvaluator, EvaluatorBase, LLMJudgeEvaluator
from framework.core.factory import OrchestratorFactory
from framework.core.harness import apply_harness_settings_to_env, build_harness_service_config
from framework.core.helpers import first_non_empty, snapshot_dir, temporary_environment
from framework.core.runtime import launch_once, write_report
from framework.core.service_config import build_service_runtime_env, service_config_credentials
from framework.models.specs import EvaluatorResult
from framework.tasks.loader import load_task_bundle


_ENV_BOOTSTRAPPED = False


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
    _ = apply_harness_settings_to_env(harness_path)


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


def _load_tools_manifest(path: str | None) -> dict[str, Any]:
    if not path:
        return {}

    target = Path(path)
    if not target.exists() or not target.is_file():
        raise FileNotFoundError(f"tools file not found: {path}")

    text = target.read_text(encoding="utf-8")
    if target.suffix.lower() == ".json":
        loaded = json.loads(text)
    else:
        loaded = yaml.safe_load(text)

    def _tool_needs_source_root(item: dict[str, Any]) -> bool:
        for value in [item.get("command"), *(item.get("args", []) if isinstance(item.get("args"), list) else [])]:
            text = str(value or "").strip()
            if not text or text.startswith("/"):
                continue
            if (target.parent / text).exists():
                return True
        return False

    def _with_default_source_root(item: Any) -> Any:
        if not isinstance(item, dict):
            return item
        payload = dict(item)
        if "source_root" not in payload and _tool_needs_source_root(payload):
            payload["source_root"] = str(target.parent.resolve())
        return payload

    if isinstance(loaded, list):
        return {
            "tools": [_with_default_source_root(tool) for tool in loaded]
        }
    if not isinstance(loaded, dict):
        return {}

    result: dict[str, Any] = {}
    tools = loaded.get("tools")
    if isinstance(tools, list):
        result["tools"] = [_with_default_source_root(tool) for tool in tools]
    guide_markdown = str(loaded.get("guide_markdown", "") or "").strip()
    guide_file = str(loaded.get("guide_file", "") or "").strip()
    if guide_file:
        guide_path = Path(guide_file)
        if not guide_path.is_absolute():
            guide_path = (target.parent / guide_path).resolve()
        if guide_path.is_file():
            guide_markdown = guide_path.read_text(encoding="utf-8").strip()
    if guide_markdown:
        result["tool_guide_markdown"] = guide_markdown
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


def _apply_tools_manifest(role_config: dict[str, Any], *manifests: dict[str, Any]) -> dict[str, Any]:
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


def _apply_attacker_tools_manifests(bundle, *manifests: dict[str, Any]) -> None:
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


def _load_harness_service_config(harness_path: str | None) -> dict[str, Any]:
    return build_harness_service_config(harness_path)


def _merge_service_config(base: dict[str, Any], overlay: dict[str, Any]) -> dict[str, Any]:
    result: dict[str, Any] = {}

    endpoints: dict[str, str] = {}
    for source in (base.get("endpoints"), overlay.get("endpoints")):
        if isinstance(source, dict):
            for key, value in source.items():
                key_text = str(key).strip()
                value_text = str(value).strip()
                if key_text and value_text:
                    endpoints[key_text] = value_text
    if endpoints:
        result["endpoints"] = endpoints

    credentials: dict[str, dict[str, str]] = {}
    for source in (base.get("credentials"), overlay.get("credentials")):
        if not isinstance(source, dict):
            continue
        for service_name, cred_values in source.items():
            if not isinstance(cred_values, dict):
                continue
            target = credentials.setdefault(str(service_name).lower(), {})
            for key, value in cred_values.items():
                key_text = str(key).strip().lower()
                value_text = str(value).strip()
                if key_text and value_text:
                    target[key_text] = value_text
    if credentials:
        result["credentials"] = credentials

    env: dict[str, str] = {}
    for source in (base.get("env"), overlay.get("env")):
        if isinstance(source, dict):
            for key, value in source.items():
                key_text = str(key).strip()
                value_text = str(value).strip()
                if key_text and value_text:
                    env[key_text] = value_text
    if env:
        result["env"] = env

    services: dict[str, Any] = {}
    for source in (base.get("services"), overlay.get("services")):
        if isinstance(source, dict):
            services.update(source)
    if services:
        result["services"] = services

    return result


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


def _select_evaluator(
    bundle,
    run_id: str,
    trace_file: Path,
    task_snapshot: dict[str, Any],
    service_snapshots: dict[str, Any],
    harness_path: str | None,
    eval_env: dict[str, str],
    eval_strategy: str,
) -> EvaluatorResult:
    deterministic: EvaluatorBase | None = None
    if bundle.deterministic_eval_path:
        deterministic = DeterministicEvaluator(
            bundle.deterministic_eval_path,
            harness_path=harness_path,
            runtime_env=eval_env,
        )

    llm_judge: EvaluatorBase | None = None
    if bundle.judge_rubric_path:
        judge_api_key = first_non_empty(
            os.environ.get("JUDGE_API_KEY", ""),
            os.environ.get("OPENAI_API_KEY", ""),
            os.environ.get("ANTHROPIC_API_KEY", ""),
            os.environ.get("OPENAI_KEY", ""),
        )
        judge_base_url = first_non_empty(
            os.environ.get("JUDGE_BASE_URL", ""),
            os.environ.get("OPENAI_BASE_URL", ""),
            os.environ.get("ANTHROPIC_BASE_URL", ""),
        )
        judge_model = first_non_empty(
            os.environ.get("JUDGE_MODEL", ""),
            os.environ.get("OPENAI_MODEL", ""),
            os.environ.get("DEFAULT_MODEL", ""),
            "gpt-4.1-mini",
        )
        if judge_base_url and judge_api_key:
            llm_judge = LLMJudgeEvaluator(
                judge_model=judge_model,
                base_url=judge_base_url,
                api_key=judge_api_key,
                rubric_path=bundle.judge_rubric_path,
            )

    strategy = (eval_strategy or "auto").strip().lower()
    chosen: EvaluatorBase | None = None
    if strategy == "deterministic":
        chosen = deterministic
    elif strategy == "llm":
        chosen = llm_judge
    elif strategy == "both":
        if deterministic and llm_judge:
            both: list[EvaluatorBase] = [deterministic, llm_judge]
            chosen = CompositeEvaluator(evaluators=both)
        else:
            chosen = deterministic or llm_judge
    else:
        if deterministic and llm_judge:
            both: list[EvaluatorBase] = [deterministic, llm_judge]
            chosen = CompositeEvaluator(evaluators=both)
        else:
            chosen = deterministic or llm_judge

    if chosen is None:
        return EvaluatorResult(
            run_id=run_id,
            decision="unknown",
            score=0.0,
            rationale=(
                "No evaluator configured: deterministic_eval missing and LLM judge unavailable "
                "(requires rubric + JUDGE_BASE_URL + JUDGE_API_KEY)."
            ),
            metadata={"task_id": bundle.task_id},
        )

    return chosen.evaluate(
        run_id=run_id,
        trace_file=str(trace_file),
        task_snapshot=task_snapshot,
        service_snapshots=service_snapshots,
    )


def _make_run_id(prefix: str = "run") -> str:
    return f"{prefix}-{int(time.time())}"


def _safe_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except Exception:
        return default


def _build_task_snapshot(task_root: Path, seed_dir: str | None) -> dict[str, Any]:
    snapshot: dict[str, Any] = {
        "task_root": str(task_root),
        "snapshot_time": int(time.time()),
        "task_files": snapshot_dir(task_root),
    }
    if seed_dir:
        seed_path = Path(seed_dir)
        if not seed_path.is_absolute():
            seed_path = task_root / seed_path
        snapshot["seed_files"] = snapshot_dir(seed_path)
    return snapshot


def _evaluate_task(
    task_dir: str,
    run_id: str,
    trace_file: Path,
    task_snapshot: dict[str, Any] | None = None,
    service_snapshots: dict[str, Any] | None = None,
) -> EvaluatorResult:
    load_env()
    bundle = load_task_bundle(task_dir)
    task_snapshot = task_snapshot or {}
    service_snapshots = service_snapshots or {}
    harness_path = os.environ.get("OPENART_EVAL_HARNESS", "") or None
    eval_env = _parse_key_value_list(os.environ.get("OPENART_EVAL_ENV", ""))
    eval_strategy = os.environ.get("OPENART_EVAL_STRATEGY", "auto")

    return _select_evaluator(
        bundle=bundle,
        run_id=run_id,
        trace_file=trace_file,
        task_snapshot=task_snapshot,
        service_snapshots=service_snapshots,
        harness_path=harness_path,
        eval_env=eval_env,
        eval_strategy=eval_strategy,
    )


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
        "--service-endpoints",
        default="",
        help="Comma separated external endpoint overrides, e.g. gitlab.web=http://gitlab.example:8929,owncloud.web=http://owncloud.example:8092",
    )
    parser.add_argument(
        "--harness",
        default="",
        help="Harness directory with config.py/common.py/scoring.py for service+evaluator setup",
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
        help="Runner framework override (opencode, claude_code, iflow, generic_cli)",
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
        help="Path to a generic user-provided tools manifest applied to both target and attacker",
    )
    parser.add_argument(
        "--target-tools-file",
        default="",
        help="Path to a generic user-provided tools manifest applied only to the target runner",
    )
    parser.add_argument(
        "--attack-tools-file",
        default="",
        help="Path to a generic user-provided tools manifest applied only to the attacker",
    )
    parser.add_argument(
        "--service-config",
        default="",
        help="Path to service config file (yaml/json)",
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
        help="Only retry another target iteration when the current result looks incomplete or partially successful",
    )
    args = parser.parse_args(argv)

    # Load task bundle
    bundle = load_task_bundle(args.task, attacker_config_path=args.attacker_config or None)

    # Generate run ID and output directory
    run_id = args.run_id or _make_run_id(bundle.task_id)
    output_root = Path(args.output_dir).resolve() if args.output_dir else _default_output_root().resolve()
    run_dir = output_root / run_id
    run_dir.mkdir(parents=True, exist_ok=True)

    # Build orchestrator using factory
    service_endpoints = _parse_key_value_list(args.service_endpoints)
    eval_env = _resolved_eval_env()
    harness_path = _resolved_harness_path(args.harness)
    _load_harness_config_env(harness_path)

    target_config_path = args.target_config or _default_config_path("target.yaml")
    service_config_path = args.service_config or _default_config_path("services.yaml")

    target_config = _load_role_config(target_config_path, "target")
    common_tools_manifest = _load_tools_manifest(args.tools_file)
    target_tools_manifest = _load_tools_manifest(args.target_tools_file)
    attack_tools_manifest = _load_tools_manifest(args.attack_tools_file)
    target_config = _apply_tools_manifest(target_config, common_tools_manifest, target_tools_manifest)
    _apply_attacker_tools_manifests(bundle, common_tools_manifest, attack_tools_manifest)
    file_service_config = _load_mapping_file(service_config_path)
    service_config = _merge_service_config(file_service_config, {})
    env_updates = {"OPENART_EVAL_STRATEGY": args.eval_strategy}
    if harness_path:
        env_updates["OPENART_EVAL_HARNESS"] = harness_path
    if eval_env:
        env_updates["OPENART_EVAL_ENV"] = ",".join(f"{key}={value}" for key, value in eval_env.items())
    env_updates.update(
        build_service_runtime_env(
            required_services=bundle.required_services,
            service_config=service_config,
            get_credentials=lambda service_name: service_config_credentials(service_config, service_name),
            evaluator_harness=bool(harness_path),
        )
    )

    removals = ["OPENART_EVAL_HARNESS", "OPENART_EVAL_ENV"]
    with temporary_environment(env_updates, removals=removals):
        factory = OrchestratorFactory(
            bundle=bundle,
            output_dir=str(run_dir),
            run_id=run_id,
            task_image=args.task_image,
            skip_build=args.skip_build,
            service_endpoint_overrides=service_endpoints,
            evaluator_harness=harness_path,
            evaluator_env=eval_env,
            runner_framework=args.runner_framework or None,
            runner_model=args.runner_model or None,
            target_config=target_config,
            service_config=service_config,
            eval_strategy=args.eval_strategy,
            skip_attacker=args.skip_attacker,
            max_iterations=max(1, int(args.max_iterations or 1)),
            adaptive_iterations=args.adaptive_iterations,
        )
        orchestrator = factory.build()

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


def eval_main(argv: list[str] | None = None) -> int:
    load_env()
    parser = argparse.ArgumentParser(prog="framework.cli eval")
    parser.add_argument("--task", required=True, help="Task directory path")
    parser.add_argument("--trace", required=True, help="Trace jsonl path")
    parser.add_argument("--run-id", default=None, help="Optional run id")
    parser.add_argument("--report", default=None, help="Optional report json path")
    parser.add_argument(
        "--harness",
        default="",
        help="Harness directory with config.py/common.py/scoring.py",
    )
    parser.add_argument(
        "--eval-strategy",
        choices=["auto", "deterministic", "llm", "both"],
        default="auto",
        help="Evaluator strategy: auto, deterministic only, llm only, or both",
    )
    args = parser.parse_args(argv)

    harness_path = _resolved_harness_path(args.harness) or ""
    _load_harness_config_env(harness_path)
    run_id = args.run_id or _make_run_id("eval")
    trace_file = Path(args.trace)
    bundle = load_task_bundle(args.task)
    task_snapshot = _build_task_snapshot(Path(bundle.root_dir), bundle.seed_dir)
    eval_env = _resolved_eval_env()
    env_updates = {"OPENART_EVAL_STRATEGY": args.eval_strategy}
    if harness_path:
        env_updates["OPENART_EVAL_HARNESS"] = harness_path
    if eval_env:
        env_updates["OPENART_EVAL_ENV"] = ",".join(f"{key}={value}" for key, value in eval_env.items())

    with temporary_environment(env_updates, removals=["OPENART_EVAL_HARNESS", "OPENART_EVAL_ENV"]):
        result = _evaluate_task(
            task_dir=args.task,
            run_id=run_id,
            trace_file=trace_file,
            task_snapshot=task_snapshot,
            service_snapshots={},
        )

    if args.report:
        write_report(args.report, result)
    _print_result(result)
    return 0


def build_main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="framework.cli build")
    parser.add_argument("--task", required=True, help="Task directory path")
    parser.add_argument("--tag", default=None, help="Docker tag override")
    args = parser.parse_args(argv)

    bundle = load_task_bundle(args.task)
    task_root = Path(bundle.root_dir)
    context_dir = Path(bundle.context_dir)
    if not context_dir.is_absolute():
        context_dir = task_root / context_dir

    dockerfile_value = bundle.dockerfile
    if dockerfile_value is None:
        print("task does not define env.dockerfile; cannot build image", file=sys.stderr)
        return 2

    dockerfile = Path(dockerfile_value)
    if not dockerfile.is_absolute():
        dockerfile = task_root / dockerfile

    image_tag = args.tag or f"openart/task-{bundle.task_id}:latest"
    cmd = ["docker", "build", "-t", image_tag, "-f", str(dockerfile), str(context_dir)]
    proc = subprocess.run(cmd, check=False)
    if proc.returncode != 0:
        return proc.returncode

    print(json.dumps({"task_id": bundle.task_id, "image": image_tag}, ensure_ascii=False))
    return 0


def reset_main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="framework.cli reset")
    parser.add_argument("--output-dir", default=None, help="Output root directory")
    parser.add_argument("--run-id", default=None, help="Specific run id to delete")
    parser.add_argument(
        "--services",
        default="",
        help="Comma separated service names to stop/remove (gitlab,owncloud,plane)",
    )
    args = parser.parse_args(argv)

    output_root = Path(args.output_dir) if args.output_dir else _default_output_root()
    if args.run_id:
        run_path = output_root / args.run_id
        if run_path.exists():
            for child in sorted(run_path.rglob("*"), reverse=True):
                if child.is_file() or child.is_symlink():
                    child.unlink(missing_ok=True)
                elif child.is_dir():
                    child.rmdir()
            run_path.rmdir()
    elif output_root.exists():
        for run_dir in output_root.iterdir():
            if not run_dir.is_dir():
                continue
            for child in sorted(run_dir.rglob("*"), reverse=True):
                if child.is_file() or child.is_symlink():
                    child.unlink(missing_ok=True)
                elif child.is_dir():
                    child.rmdir()
            run_dir.rmdir()

    services = _parse_comma_list(args.services)
    for service in services:
        for name in (service, f"openart-{service}"):
            subprocess.run(["docker", "rm", "-f", name], check=False, capture_output=True)

    print(json.dumps({"status": "ok", "services": services}, ensure_ascii=False))
    return 0


def doctor_main(argv: list[str] | None = None) -> int:
    load_env()
    parser = argparse.ArgumentParser(prog="framework.cli doctor")
    parser.add_argument("--task", default=None, help="Optional task directory to validate")
    args = parser.parse_args(argv)

    checks: list[dict[str, Any]] = []

    docker_ok = False
    try:
        proc = subprocess.run(["docker", "info"], check=False, capture_output=True, text=True)
        docker_ok = proc.returncode == 0
    except FileNotFoundError:
        docker_ok = False
    checks.append({"name": "docker", "ok": docker_ok})

    if args.task:
        try:
            bundle = load_task_bundle(args.task)
            task_root = Path(bundle.root_dir)
            checks.append({"name": "task.load", "ok": True, "task_id": bundle.task_id})
            checks.append({"name": "task.target_instruction", "ok": Path(bundle.target_instruction_path).exists()})
            if bundle.deterministic_eval_path:
                checks.append(
                    {
                        "name": "task.deterministic_eval",
                        "ok": Path(bundle.deterministic_eval_path).exists(),
                    }
                )
            if bundle.judge_rubric_path:
                checks.append(
                    {
                        "name": "task.judge_rubric",
                        "ok": Path(bundle.judge_rubric_path).exists(),
                    }
                )
            checks.append({"name": "task.root_exists", "ok": task_root.exists()})
        except Exception as exc:
            checks.append({"name": "task.load", "ok": False, "error": str(exc)})

    overall = all(bool(item.get("ok")) for item in checks)
    print(json.dumps({"ok": overall, "checks": checks}, ensure_ascii=False, indent=2))
    return 0 if overall else 1


def main(argv: list[str] | None = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    if not argv:
        print("usage: python -m framework.cli <run|build|reset|eval|doctor> [args]", file=sys.stderr)
        return 2

    command = argv[0]
    tail = argv[1:]
    if command == "run":
        return run_main(tail)
    if command == "build":
        return build_main(tail)
    if command == "reset":
        return reset_main(tail)
    if command == "eval":
        return eval_main(tail)
    if command == "doctor":
        return doctor_main(tail)

    print(f"unknown command: {command}", file=sys.stderr)
    return 2

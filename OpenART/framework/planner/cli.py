from __future__ import annotations

import argparse
import json
import shutil
from pathlib import Path
from typing import Any, Sequence

from .complexity import (
    DEFAULT_COMPLEXITY_PROFILE,
    builtin_complexity_profiles,
    default_repair_attempts_for_complexity,
    load_complexity_spec,
)
from .opencode_backend import (
    DEFAULT_PLANNER_CONTEXT_MAX_CHARS,
    DEFAULT_PLANNER_CONTEXT_MODE,
    DEFAULT_PLANNER_DOCKER_IMAGE,
    OpenCodePlannerBackend,
    OpenCodePlannerError,
    PLANNER_CONTEXT_MODES,
    build_generation_prompt,
    build_repair_prompt,
    build_scenario_model_prompt,
    build_scenario_repair_prompt,
    prepare_output_dir,
)
from .registry import (
    run_registry_materialization_phase,
    write_refreshed_planner_inputs,
)
from .validation import validate_generated_bundle, validate_scenario_model, write_validation_report


def _load_env_for_planner() -> None:
    # Reuse the normal OpenART CLI dotenv loader so planner users can invoke the
    # module directly instead of wrapping it in a python -c load_env() command.
    from framework.cli.commands import load_env

    load_env()


def _read_text_arg(value: str | None, file_path: str | None) -> str:
    if value and file_path:
        raise ValueError("provide either --scenario or --scenario-file, not both")
    if file_path:
        return Path(file_path).read_text(encoding="utf-8").strip()
    if value:
        return value.strip()
    raise ValueError("scenario description is required")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Generate an OpenART safe-world task from a scenario description.")
    parser.add_argument("--scenario", help="Free-form scenario description.")
    parser.add_argument("--scenario-file", help="Path to a file containing the scenario description.")
    parser.add_argument(
        "--planner-backend",
        choices=["deterministic", "opencode"],
        default="opencode",
        help=(
            "Planner backend to use. OpenCode is the only supported generator; "
            "--planner-backend opencode is accepted for compatibility."
        ),
    )
    parser.add_argument(
        "--planner-docker-image",
        default=DEFAULT_PLANNER_DOCKER_IMAGE,
        help=f"Docker image used by --planner-backend opencode. Default: {DEFAULT_PLANNER_DOCKER_IMAGE}",
    )
    parser.add_argument(
        "--planner-max-repairs",
        type=int,
        default=None,
        help="Maximum OpenCode repair attempts after validation failure. Default: profile-aware auto.",
    )
    parser.add_argument(
        "--planner-context-mode",
        choices=PLANNER_CONTEXT_MODES,
        default=DEFAULT_PLANNER_CONTEXT_MODE,
        help=(
            "Prompt context mode. compact summarizes large tool inputs and references full on-disk artifacts; "
            "full embeds complete tool_pool.json and capabilities.generated.yaml. Default: compact."
        ),
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
        help="Embed the full original prompt in repair prompts instead of the default hash/reference.",
    )
    parser.add_argument(
        "--tool-count",
        type=int,
        help="Require exactly N distinct enabled external tools in tool_use_graph.safe_workflow.",
    )
    parser.add_argument(
        "--complexity-profile",
        choices=sorted(builtin_complexity_profiles()),
        default=DEFAULT_COMPLEXITY_PROFILE,
        help=f"Planner complexity profile used by prompts and validation. Default: {DEFAULT_COMPLEXITY_PROFILE}.",
    )
    parser.add_argument(
        "--complexity-config",
        help="Optional YAML/JSON complexity config that overlays the selected profile.",
    )
    parser.add_argument(
        "--tool-store",
        required=True,
        help="Required managed OpenART tool store used as the only planner tool input source.",
    )
    parser.add_argument(
        "--emit-runtime-manifest",
        help=(
            "Optional output path that receives a copy of generated capabilities.generated.yaml; "
            "this is not a planner input source."
        ),
    )
    parser.add_argument("--output-dir", required=True, help="Directory where the generated task bundle is written.")
    parser.add_argument("--task-id", help="Generated task id.")
    parser.add_argument("--name", help="Generated display name.")
    parser.add_argument("--domain-hint", action="append", default=[], help="Optional domain hint. Can be repeated.")
    parser.add_argument("--overwrite", action="store_true", help="Replace output directory contents if present.")
    return parser


def _emit_cli_summary(
    *,
    task_id: str,
    output_dir: Path,
    runtime_manifest: str,
    selected_tools: dict[str, str] | None = None,
    required_capabilities: list[str] | None = None,
    forbidden_capabilities: list[str] | None = None,
    planner_backend: str,
    validation_report: str = "",
) -> None:
    payload: dict[str, Any] = {
        "task_id": task_id,
        "output_dir": str(output_dir),
        "runtime_manifest": runtime_manifest,
        "planner_backend": planner_backend,
    }
    if selected_tools is not None:
        payload["selected_tools"] = selected_tools
    if required_capabilities is not None:
        payload["required_capabilities"] = required_capabilities
    if forbidden_capabilities is not None:
        payload["forbidden_capabilities"] = forbidden_capabilities
    if validation_report:
        payload["validation_report"] = validation_report
    print(json.dumps(payload, indent=2, sort_keys=True))


def _copy_manifest_if_requested(source: Path, destination: str | None) -> str:
    if not destination:
        return ""
    target = Path(destination)
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(source, target)
    return str(target)


def _planner_tool_store_root(args: argparse.Namespace) -> Path:
    return Path(args.tool_store)


def _run_opencode_backend(
    args: argparse.Namespace,
    scenario: str,
) -> int:
    if args.tool_count is not None and args.tool_count < 0:
        raise ValueError("--tool-count must be non-negative")
    complexity_spec = load_complexity_spec(args.complexity_profile, config_path=args.complexity_config)
    planner_max_repairs = (
        default_repair_attempts_for_complexity(complexity_spec, fallback_profile=args.complexity_profile)
        if args.planner_max_repairs is None
        else args.planner_max_repairs
    )
    if planner_max_repairs < 0:
        raise ValueError("--planner-max-repairs must be non-negative")
    if args.planner_context_max_chars <= 0:
        raise ValueError("--planner-context-max-chars must be positive")

    output_dir = prepare_output_dir(args.output_dir, overwrite=args.overwrite)
    artifacts = output_dir / "planner_artifacts"
    artifacts.mkdir(parents=True, exist_ok=True)

    registry_result = run_registry_materialization_phase(
        scenario=scenario,
        tool_store_root=_planner_tool_store_root(args),
        domain_hints=list(args.domain_hint),
        tool_count=args.tool_count,
        include_builtin_workspace=True,
        artifact_dir=artifacts,
    )
    tool_pool = registry_result.tool_pool
    runtime_manifest = registry_result.runtime_manifest
    registry_feedback = registry_result.feedback.as_dict()
    write_refreshed_planner_inputs(output_dir=output_dir, tool_pool=tool_pool, runtime_manifest=runtime_manifest)

    scenario_prompt = build_scenario_model_prompt(
        scenario=scenario,
        tool_pool=tool_pool,
        runtime_manifest=runtime_manifest,
        task_id=args.task_id,
        name=args.name,
        domain_hints=list(args.domain_hint),
        tool_count=args.tool_count,
        complexity_spec=complexity_spec,
        registry_feedback=registry_feedback,
        context_mode=args.planner_context_mode,
        context_max_chars=args.planner_context_max_chars,
    )
    backend = OpenCodePlannerBackend(docker_image=args.planner_docker_image)
    scenario_errors: list[str] = []
    scenario_report_path = artifacts / "scenario_validation_attempt_0.json"

    for attempt in range(planner_max_repairs + 1):
        prompt = (
            scenario_prompt
            if attempt == 0
            else build_scenario_repair_prompt(
                original_prompt=scenario_prompt,
                validation_errors=scenario_errors,
                output_dir=output_dir,
                tool_count=args.tool_count,
                complexity_spec=complexity_spec,
                include_original_prompt=True,
            )
        )
        run = backend.run_prompt(prompt, output_dir=output_dir, artifact_root=artifacts, attempt=attempt)
        scenario_result = validate_scenario_model(
            output_dir / "scenario_model.json",
            tool_pool=tool_pool,
            complexity_spec=complexity_spec,
        )
        if run.returncode != 0:
            scenario_result.errors.append(f"opencode exited with status {run.returncode}; see {run.stderr[:500]}")
            scenario_result.ok = False
        scenario_report_path = write_validation_report(output_dir, scenario_result, attempt=attempt, label="scenario_validation")
        if scenario_result.ok:
            break
        scenario_errors = list(scenario_result.errors)
    else:
        raise OpenCodePlannerError(
            "OpenCode planner scenario_model validation failed after "
            f"{planner_max_repairs + 1} attempt(s); see validation report: {scenario_report_path}"
        )

    scenario_model = json.loads((output_dir / "scenario_model.json").read_text(encoding="utf-8"))
    base_prompt = build_generation_prompt(
        scenario=scenario,
        tool_pool=tool_pool,
        runtime_manifest=runtime_manifest,
        task_id=args.task_id,
        name=args.name,
        domain_hints=list(args.domain_hint),
        tool_count=args.tool_count,
        complexity_spec=complexity_spec,
        scenario_model=scenario_model,
        registry_feedback=registry_feedback,
        context_mode=args.planner_context_mode,
        context_max_chars=args.planner_context_max_chars,
    )
    validation_errors: list[str] = []
    report_path = artifacts / "validation_attempt_0.json"
    bundle_attempt_offset = planner_max_repairs + 1

    for attempt in range(planner_max_repairs + 1):
        prompt = (
            base_prompt
            if attempt == 0
            else build_repair_prompt(
                original_prompt=base_prompt,
                validation_errors=validation_errors,
                output_dir=output_dir,
                tool_count=args.tool_count,
                complexity_spec=complexity_spec,
                failure_type="bundle",
                include_original_prompt=args.planner_repair_include_original_prompt,
            )
        )
        run = backend.run_prompt(
            prompt,
            output_dir=output_dir,
            artifact_root=artifacts,
            attempt=bundle_attempt_offset + attempt,
        )
        result = validate_generated_bundle(output_dir, tool_count=args.tool_count, complexity_spec=complexity_spec)
        if run.returncode != 0:
            exit_note = f"opencode exited with status {run.returncode}; see {run.stderr[:500]}"
            if result.ok:
                result.metadata["opencode_nonzero_exit_ignored"] = exit_note
            else:
                result.errors.append(exit_note)
                result.ok = False
        report_path = write_validation_report(output_dir, result, attempt=attempt)
        if result.ok:
            emitted_manifest = _copy_manifest_if_requested(output_dir / "capabilities.generated.yaml", args.emit_runtime_manifest)
            _emit_cli_summary(
                task_id=args.task_id or output_dir.name,
                output_dir=output_dir,
                runtime_manifest=emitted_manifest or str(output_dir / "capabilities.generated.yaml"),
                planner_backend="opencode",
                validation_report=str(report_path),
            )
            return 0
        validation_errors = list(result.errors)

    raise OpenCodePlannerError(
        "OpenCode planner validation failed after "
        f"{planner_max_repairs + 1} attempt(s); see validation report: {report_path}"
    )


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    _load_env_for_planner()
    if args.planner_backend == "deterministic":
        parser.error("deterministic planner backend has been removed; use --planner-backend opencode")
    if args.tool_count is not None and args.tool_count < 0:
        raise ValueError("--tool-count must be non-negative")
    scenario = _read_text_arg(args.scenario, args.scenario_file)
    return _run_opencode_backend(args, scenario)


if __name__ == "__main__":
    raise SystemExit(main())

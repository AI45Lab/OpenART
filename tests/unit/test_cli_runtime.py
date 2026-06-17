from __future__ import annotations

import argparse
import asyncio
import json
from pathlib import Path
from typing import Any

import pytest

from framework.cli import commands
from framework.models.specs import ConcurrencySpec, EvaluatorResult
from framework.models.task import TaskBundleSpec
from framework.tasks.builder import build_task_bundle_scaffold
from framework.tasks.loader import load_task_bundle
from scripts import run_all_tasks_with_timing as batch_runner


def test_parse_key_value_list_ignores_invalid_entries() -> None:
    parsed = commands._parse_key_value_list("A=1,B=2,invalid,=x,C=")
    assert parsed == {"A": "1", "B": "2"}


@pytest.mark.parametrize("command", ["build", "reset", "eval", "doctor"])
def test_removed_cli_commands_are_rejected(command: str, capsys) -> None:
    exit_code = commands.main([command])

    captured = capsys.readouterr()
    assert exit_code == 2
    assert f"unknown command: {command}" in captured.err


def test_cli_main_usage_lists_only_run(capsys) -> None:
    exit_code = commands.main([])

    captured = capsys.readouterr()
    assert exit_code == 2
    assert "usage: python -m framework.cli run [args]" in captured.err


def test_load_env_backfills_target_and_judge_settings(monkeypatch, tmp_path: Path) -> None:
    env_path = tmp_path / ".env"
    env_path.write_text(
        'OPENAI_KEY="openai-secret"\nOPENAI_BASE_URL="http://llm.internal/v1"\nOPENAI_MODEL="demo-model"\n',
        encoding="utf-8",
    )

    for key in (
        "OPENAI_KEY",
        "OPENAI_API_KEY",
        "OPENAI_BASE_URL",
        "OPENAI_MODEL",
        "TARGET_API_KEY",
        "TARGET_BASE_URL",
        "TARGET_MODEL",
        "JUDGE_API_KEY",
        "JUDGE_BASE_URL",
        "JUDGE_MODEL",
        "ATTACK_API_KEY",
        "ATTACK_BASE_URL",
        "ATTACK_MODEL",
    ):
        monkeypatch.delenv(key, raising=False)

    monkeypatch.setattr(commands, "_env_file_candidates", lambda: [env_path])
    monkeypatch.setattr(commands, "_ENV_BOOTSTRAPPED", False)

    commands.load_env()

    assert commands.os.environ["OPENAI_API_KEY"] == "openai-secret"
    assert commands.os.environ["TARGET_API_KEY"] == "openai-secret"
    assert commands.os.environ["TARGET_BASE_URL"] == "http://llm.internal/v1"
    assert commands.os.environ["TARGET_MODEL"] == "demo-model"
    assert commands.os.environ["JUDGE_API_KEY"] == "openai-secret"
    assert commands.os.environ["JUDGE_BASE_URL"] == "http://llm.internal/v1"
    assert commands.os.environ["JUDGE_MODEL"] == "demo-model"
    assert commands.os.environ["ATTACK_API_KEY"] == "openai-secret"
    assert commands.os.environ["ATTACK_BASE_URL"] == "http://llm.internal/v1"
    assert commands.os.environ["ATTACK_MODEL"] == "demo-model"


@pytest.mark.parametrize(
    "flag",
    [
        "--tools-file",
        "--target-tools-file",
        "--attack-tools-file",
        "--capabilities-file",
        "--capabilities-dir",
    ],
)
def test_runtime_legacy_tool_flags_fail_with_migration_error(flag: str, tmp_path: Path, capsys) -> None:
    with pytest.raises(SystemExit) as excinfo:
        commands.run_main(["--task", str(tmp_path / "missing-task"), flag, "legacy.yaml"])

    assert excinfo.value.code == 2
    captured = capsys.readouterr()
    assert "legacy runtime tool flags are no longer supported" in captured.err
    assert "--tool-store plus task/tool_use_graph.json" in captured.err


def _write_managed_tool(tool_store: Path, name: str) -> None:
    tool_dir = tool_store / name
    scripts = tool_dir / "scripts"
    scripts.mkdir(parents=True)
    (scripts / "run.py").write_text("print('ok')\n", encoding="utf-8")
    (tool_dir / "TOOL.md").write_text(f"# {name}\n\nRun {name}.\n", encoding="utf-8")
    (tool_dir / "tool.yaml").write_text(
        f"name: {name}\n"
        "command: python3\n"
        "args: [scripts/run.py]\n"
        "source_files: [scripts/run.py]\n",
        encoding="utf-8",
    )


def test_runtime_tool_store_without_task_graph_loads_full_store(monkeypatch, tmp_path: Path) -> None:
    task_root = tmp_path / "task"
    task_root.mkdir(parents=True)
    (task_root / "task.md").write_text("Do the task.\n", encoding="utf-8")
    tool_store = tmp_path / "openart-tools"
    _write_managed_tool(tool_store, "demo.one")
    _write_managed_tool(tool_store, "demo.two")
    bundle = TaskBundleSpec(
        task_id="task",
        name="Task",
        root_dir=str(task_root),
        target_instruction="task.md",
    )
    captured: dict[str, Any] = {}

    class _FakeOrchestrator:
        def teardown(self) -> None:
            return None

    class _FakeFactory:
        def __init__(self, **kwargs: Any) -> None:
            captured.update(kwargs)

        def build(self) -> _FakeOrchestrator:
            return _FakeOrchestrator()

    monkeypatch.setattr(commands, "load_task_bundle", lambda *args, **kwargs: bundle)
    monkeypatch.setattr(commands, "OrchestratorFactory", _FakeFactory)
    monkeypatch.setattr(
        commands,
        "launch_once",
        lambda orchestrator, **kwargs: EvaluatorResult(run_id=kwargs["run_id"], decision="pass", score=1.0),
    )

    exit_code = commands.run_main(
        ["--task", str(task_root), "--tool-store", str(tool_store), "--output-dir", str(tmp_path / "outputs")]
    )

    assert exit_code == 0
    assert {tool["name"] for tool in captured["target_config"]["tools"]} == {"demo.one", "demo.two"}


def test_runtime_tool_store_graph_selects_referenced_tools(monkeypatch, tmp_path: Path) -> None:
    task_root = tmp_path / "task"
    task_root.mkdir(parents=True)
    (task_root / "task.md").write_text("Do the task.\n", encoding="utf-8")
    (task_root / "tool_use_graph.json").write_text(
        '{"safe_workflow": {"nodes": [{"tool": "demo.one"}], "edges": []}}\n',
        encoding="utf-8",
    )
    tool_store = tmp_path / "openart-tools"
    _write_managed_tool(tool_store, "demo.one")
    _write_managed_tool(tool_store, "demo.two")
    bundle = TaskBundleSpec(
        task_id="task",
        name="Task",
        root_dir=str(task_root),
        target_instruction="task.md",
    )
    captured: dict[str, Any] = {}

    class _FakeOrchestrator:
        def teardown(self) -> None:
            return None

    class _FakeFactory:
        def __init__(self, **kwargs: Any) -> None:
            captured.update(kwargs)

        def build(self) -> _FakeOrchestrator:
            return _FakeOrchestrator()

    monkeypatch.setattr(commands, "load_task_bundle", lambda *args, **kwargs: bundle)
    monkeypatch.setattr(commands, "OrchestratorFactory", _FakeFactory)
    monkeypatch.setattr(
        commands,
        "launch_once",
        lambda orchestrator, **kwargs: EvaluatorResult(run_id=kwargs["run_id"], decision="pass", score=1.0),
    )

    exit_code = commands.run_main(
        [
            "--task",
            str(task_root),
            "--tool-store",
            str(tool_store),
            "--output-dir",
            str(tmp_path / "outputs"),
        ]
    )

    assert exit_code == 0
    assert [tool["name"] for tool in captured["target_config"]["tools"]] == ["demo.one"]


def test_container_instruction_path_maps_task_files_into_task_mount(tmp_path: Path) -> None:
    task_root = tmp_path / "task"
    task_root.mkdir(parents=True, exist_ok=True)
    instruction = task_root / "instructions" / "target.md"
    instruction.parent.mkdir(parents=True, exist_ok=True)
    instruction.write_text("hello\n", encoding="utf-8")

    mapped = commands._container_instruction_path(task_root, str(instruction))

    assert mapped == "/task/instructions/target.md"


def test_attach_runner_debug_adds_runner_previews_and_artifacts(tmp_path: Path) -> None:
    run_dir = tmp_path / "run"
    target_dir = run_dir / "runner_outputs" / "target"
    target_dir.mkdir(parents=True, exist_ok=True)
    (target_dir / "command.sh").write_text("python agent.py\n", encoding="utf-8")
    (target_dir / "stdout.txt").write_text("agent stdout\n", encoding="utf-8")
    (target_dir / "stderr.txt").write_text("", encoding="utf-8")
    (target_dir / "status.json").write_text('{"exit_code": 0}\n', encoding="utf-8")

    result = EvaluatorResult(run_id="run-1", decision="pass", score=1.0)

    commands._attach_runner_debug(result, run_dir)

    runner_debug = result.metadata["debug"]["runner_outputs"]["target"]
    assert runner_debug["command"] == "python agent.py"
    assert runner_debug["stdout_preview"] == "agent stdout\n"
    assert runner_debug["status"]["exit_code"] == 0
    assert result.artifacts["target_stdout"].endswith("stdout.txt")


def test_resolved_harness_path_falls_back_to_environment(monkeypatch) -> None:
    monkeypatch.setenv("OPENART_EVAL_HARNESS", "/tmp/oas_harness")

    resolved = commands._resolved_harness_path("")

    assert resolved == "/tmp/oas_harness"


def test_resolved_harness_path_normalizes_relative_path(monkeypatch, tmp_path: Path) -> None:
    harness_dir = tmp_path / "oas_harness"
    harness_dir.mkdir(parents=True, exist_ok=True)
    monkeypatch.chdir(tmp_path.parent)

    resolved = commands._resolved_harness_path(str(harness_dir.relative_to(tmp_path.parent)))

    assert resolved == str(harness_dir.resolve())


def test_resolved_eval_env_comes_from_environment(monkeypatch) -> None:
    monkeypatch.setenv("OPENART_EVAL_ENV", "TAC_TEST_MODE=1,SERVER_HOSTNAME=127.0.0.1")

    resolved = commands._resolved_eval_env()

    assert resolved == {
        "TAC_TEST_MODE": "1",
        "SERVER_HOSTNAME": "127.0.0.1",
    }


def test_load_harness_config_env_does_not_backfill_service_credentials(monkeypatch, tmp_path: Path) -> None:
    harness_dir = tmp_path / "harness"
    harness_dir.mkdir(parents=True, exist_ok=True)
    (harness_dir / "config.py").write_text(
        "GITLAB_BASEURL = 'http://gitlab.example:8929'\n"
        "GITLAB_ACCESS_TOKEN = 'glpat-test-token'\n"
        "OWNCLOUD_URL = 'http://owncloud.example:8092'\n",
        encoding="utf-8",
    )
    for key in ("GITLAB_BASEURL", "GITLAB_ACCESS_TOKEN", "OWNCLOUD_URL"):
        monkeypatch.delenv(key, raising=False)

    commands._load_harness_config_env(str(harness_dir))

    assert "GITLAB_BASEURL" not in commands.os.environ
    assert "GITLAB_ACCESS_TOKEN" not in commands.os.environ
    assert "OWNCLOUD_URL" not in commands.os.environ



def test_apply_tool_manifest_merges_shared_and_role_tools() -> None:
    role_config = {"tools": ["bash", {"name": "gitlab.create_project", "enabled": False}]}
    shared = {"tools": [{"name": "gitlab.create_project", "enabled": True}, {"name": "owncloud.upload_file"}]}
    role_specific = {"tool_guide_markdown": "Use the provided service tools."}

    merged = commands._apply_tool_manifest(role_config, shared, role_specific)

    assert merged["tools"] == ["bash", {"name": "gitlab.create_project", "enabled": True}, {"name": "owncloud.upload_file"}]
    assert merged["tool_guide_markdown"] == "Use the provided service tools."


def test_load_task_bundle_applies_attacker_config_to_openagentsafety_task(tmp_path: Path) -> None:
    task_root = tmp_path / "safety-demo"
    task_root.mkdir(parents=True, exist_ok=True)
    (task_root / "task.md").write_text("target task\n", encoding="utf-8")
    (task_root / "attacker.md").write_text("attack task\n", encoding="utf-8")
    (task_root / "utils").mkdir(parents=True, exist_ok=True)
    (task_root / "utils" / "evaluator.py").write_text("def evaluate(**kwargs):\n    return {'decision': 'pass', 'score': 1.0}\n", encoding="utf-8")
    overlay = tmp_path / "overlay.yaml"
    overlay.write_text(
        "attacker:\n"
        "  name: overlay-attacker\n"
        "  phase: before_target\n"
        "  instruction: attacker.md\n"
        "  image: python:3.11-slim\n"
        "  cmd: python3\n"
        "  target_control_plane: true\n"
        "  feedback_loop: true\n"
        "  vector_permissions:\n"
        "    - workspace_files\n"
        "    - claude_md\n"
        "  args:\n"
        "    - attacker.py\n",
        encoding="utf-8",
    )

    bundle = load_task_bundle(str(task_root), attacker_config_path=str(overlay))

    assert bundle.target_instruction == "task.md"
    assert bundle.attacker is not None
    assert bundle.attacker.name == "overlay-attacker"
    assert bundle.attacker.instruction == "attacker.md"
    assert bundle.attacker.target_control_plane is True
    assert bundle.attacker.feedback_loop is True
    assert bundle.attacker.vector_permissions == ["workspace_files", "claude_md"]
    assert bundle.metadata["attacker_config"] == str(overlay.resolve())


def test_load_task_bundle_accepts_task_md_without_utils(tmp_path: Path) -> None:
    task_root = tmp_path / "safety-minimal"
    task_root.mkdir(parents=True)
    (task_root / "task.md").write_text("Do the minimal task.\n", encoding="utf-8")

    bundle = load_task_bundle(str(task_root))

    assert bundle.task_id == "safety-minimal"
    assert bundle.target_instruction == "task.md"
    assert bundle.deterministic_eval is None
    assert bundle.judge_rubric is None
    assert bundle.seed_dir is None
    assert bundle.concurrency.mode == "local_only"


def test_load_task_bundle_rejects_task_yaml_without_task_md(tmp_path: Path) -> None:
    task_root = tmp_path / "legacy-task"
    task_root.mkdir(parents=True)
    (task_root / "task.yaml").write_text(
        "task_id: legacy-task\n"
        "name: Legacy Task\n"
        "instructions:\n"
        "  target: target.md\n",
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="task.yaml is no longer accepted"):
        load_task_bundle(str(task_root))


def test_task_scaffold_generates_openagentsafety_layout(tmp_path: Path) -> None:
    task_root = tmp_path / "scaffolded-task"

    build_task_bundle_scaffold(str(task_root), "scaffolded-task", "Scaffolded Task")

    assert (task_root / "task.md").is_file()
    assert not (task_root / "task.yaml").exists()
    bundle = load_task_bundle(str(task_root))
    assert bundle.target_instruction == "task.md"
    assert bundle.seed_dir == "workspace"
    assert bundle.deterministic_eval == "utils/evaluator.py"
    assert bundle.judge_rubric == "checkpoints.md"


def _batch_args(parallelism: int, continue_on_error: bool = True) -> argparse.Namespace:
    return argparse.Namespace(parallelism=parallelism, continue_on_error=continue_on_error)


def _batch_task_spec(
    tmp_path: Path,
    name: str,
    *,
    mode: str = "local_only",
    resource_keys: list[str] | None = None,
) -> dict[str, Any]:
    task_dir = tmp_path / name
    task_dir.mkdir()
    return {
        "task_dir": task_dir,
        "bundle": TaskBundleSpec(
            task_id=name,
            name=name,
            root_dir=str(task_dir),
            target_instruction="task.md",
            concurrency=ConcurrencySpec(
                mode=mode,
                resource_keys=list(resource_keys or []),
                max_parallel_for_task=1,
            ),
        ),
        "run_id": f"run-{name}",
        "index": 1,
    }


def _install_fake_batch_subprocess(
    monkeypatch: Any,
    *,
    returncodes: dict[str, int] | None = None,
    delays: dict[str, float] | None = None,
) -> dict[str, Any]:
    state: dict[str, Any] = {
        "active": 0,
        "peak": 0,
        "started": [],
    }
    returncodes = returncodes or {}
    delays = delays or {}

    def fake_build_run_command(
        repo_root: Path,
        args: argparse.Namespace,
        task_dir: Path,
        run_id: str,
        output_root: Path,
    ) -> list[str]:
        return [run_id]

    async def fake_run_subprocess(cmd: list[str], cwd: Path, env: dict[str, str]) -> tuple[int, str, str]:
        run_id = cmd[0]
        state["started"].append(run_id)
        state["active"] += 1
        state["peak"] = max(state["peak"], state["active"])
        try:
            await asyncio.sleep(delays.get(run_id, 0.02))
            return returncodes.get(run_id, 0), f"stdout {run_id}", ""
        finally:
            state["active"] -= 1

    monkeypatch.setattr(batch_runner, "build_run_command", fake_build_run_command)
    monkeypatch.setattr(batch_runner, "run_subprocess", fake_run_subprocess)
    return state


def test_batch_runner_allows_same_service_and_isolated_tasks(tmp_path: Path, monkeypatch: Any) -> None:
    state = _install_fake_batch_subprocess(monkeypatch)
    specs = [
        _batch_task_spec(tmp_path, "shared-a", mode="shared_service", resource_keys=["gitlab"]),
        _batch_task_spec(tmp_path, "shared-b", mode="shared_service", resource_keys=["gitlab"]),
        _batch_task_spec(tmp_path, "isolated", mode="isolated_service", resource_keys=["owncloud"]),
        _batch_task_spec(tmp_path, "local", mode="local_only"),
    ]

    summaries, metrics = asyncio.run(
        batch_runner.execute_parallel_runs(
            Path.cwd(),
            tmp_path / "outputs",
            "batch",
            _batch_args(parallelism=4),
            specs,
            tmp_path / "outputs" / "batch" / "timing_log.jsonl",
        )
    )

    assert len(summaries) == 4
    assert metrics == {
        "requested_parallelism": 4,
        "peak_active_runs": 4,
        "scheduled_run_count": 4,
        "completed_run_count": 4,
    }
    assert state["peak"] == 4


def test_batch_runner_parallelism_one_runs_serially(tmp_path: Path, monkeypatch: Any) -> None:
    state = _install_fake_batch_subprocess(monkeypatch)
    specs = [_batch_task_spec(tmp_path, f"task-{index}") for index in range(3)]

    summaries, metrics = asyncio.run(
        batch_runner.execute_parallel_runs(
            Path.cwd(),
            tmp_path / "outputs",
            "batch",
            _batch_args(parallelism=1),
            specs,
            tmp_path / "outputs" / "batch" / "timing_log.jsonl",
        )
    )

    assert len(summaries) == 3
    assert metrics["peak_active_runs"] == 1
    assert state["peak"] == 1


def test_batch_runner_continue_on_error_false_stops_new_scheduling(tmp_path: Path, monkeypatch: Any) -> None:
    state = _install_fake_batch_subprocess(
        monkeypatch,
        returncodes={"run-task-0": 1},
        delays={"run-task-0": 0.01, "run-task-1": 0.04},
    )
    specs = [_batch_task_spec(tmp_path, f"task-{index}") for index in range(4)]

    summaries, metrics = asyncio.run(
        batch_runner.execute_parallel_runs(
            Path.cwd(),
            tmp_path / "outputs",
            "batch",
            _batch_args(parallelism=2, continue_on_error=False),
            specs,
            tmp_path / "outputs" / "batch" / "timing_log.jsonl",
        )
    )

    assert [entry["run_id"] for entry in summaries] == ["run-task-0", "run-task-1"]
    assert metrics["scheduled_run_count"] == 2
    assert metrics["completed_run_count"] == 2
    assert "run-task-2" not in state["started"]


def test_batch_run_command_forwards_only_tool_store_for_runtime_tools(tmp_path: Path) -> None:
    args = argparse.Namespace(
        evaluator_harness="openagentsafety_utils/oas_harness",
        eval_strategy="both",
        max_iterations=1,
        target_timeout_seconds=0,
        attacker_timeout_seconds=0,
        adaptive_iterations=False,
        no_adaptive_iterations=True,
        attacker_config="",
        target_config="",
        tools_file="legacy-tools.yaml",
        tool_store="../openart-tools",
        capabilities_file=["legacy-capabilities.yaml"],
        capabilities_dir=["legacy-capabilities"],
        runner_framework="",
        runner_model="",
        skip_attacker=False,
    )

    cmd = batch_runner.build_run_command(Path("OpenART"), args, tmp_path / "task", "run-1", tmp_path / "outputs")

    assert "--evaluator-harness" in cmd
    assert "--harness" not in cmd
    assert "--tool-store" in cmd
    assert cmd[cmd.index("--tool-store") + 1].endswith("openart-tools")
    assert "--tools-file" not in cmd
    assert "--capabilities-file" not in cmd
    assert "--capabilities-dir" not in cmd


def test_batch_runner_writes_metrics_to_plan_and_summary(tmp_path: Path, monkeypatch: Any) -> None:
    output_dir = tmp_path / "outputs"
    args = argparse.Namespace(
        tasks_root=str(tmp_path / "tasks"),
        output_dir=str(output_dir),
        evaluator_harness="openagentsafety_utils/oas_harness",
        tools_file="",
        tool_store="",
        attacker_config="",
        target_config="",
        runner_framework="",
        runner_model="",
        eval_strategy="both",
        tasks=[],
        limit=0,
        max_iterations=1,
        adaptive_iterations=False,
        target_timeout_seconds=0,
        attacker_timeout_seconds=0,
        skip_attacker=False,
        parallelism=3,
        run_prefix="batch",
        batch_id="metrics-batch",
        continue_on_error=True,
        rerun_from_batch="",
        rerun_statuses="fail,unknown,error",
        require_target_validation=False,
        allow_unvalidated_target=False,
        target_responses_router="none",
        surface_family="",
        docs_url="",
    )
    metrics = {
        "requested_parallelism": 3,
        "peak_active_runs": 2,
        "scheduled_run_count": 2,
        "completed_run_count": 2,
    }
    summaries = [
        {
            "task": "task-a",
            "task_dir": str(tmp_path / "task-a"),
            "run_id": "run-task-a",
            "returncode": 0,
            "started_at": 10.0,
            "finished_at": 11.0,
            "wall_ms": 1000,
            "decision": "",
            "score": None,
            "timing": {},
            "result_file": "",
            "timing_file": "",
            "stdout_preview": "",
            "stderr_preview": "",
        },
        {
            "task": "task-b",
            "task_dir": str(tmp_path / "task-b"),
            "run_id": "run-task-b",
            "returncode": 0,
            "started_at": 10.5,
            "finished_at": 12.0,
            "wall_ms": 1500,
            "decision": "",
            "score": None,
            "timing": {},
            "result_file": "",
            "timing_file": "",
            "stdout_preview": "",
            "stderr_preview": "",
        },
    ]

    async def fake_execute_parallel_runs(*call_args: Any, **call_kwargs: Any) -> tuple[list[dict[str, Any]], dict[str, int]]:
        return summaries, metrics

    monkeypatch.setattr(batch_runner, "parse_args", lambda: args)
    monkeypatch.setattr(batch_runner, "load_env", lambda: None)
    monkeypatch.setattr(batch_runner, "discover_tasks", lambda *call_args: [tmp_path / "task-a", tmp_path / "task-b"])
    monkeypatch.setattr(batch_runner, "build_task_specs", lambda *call_args: [])
    monkeypatch.setattr(batch_runner, "execute_parallel_runs", fake_execute_parallel_runs)

    assert batch_runner.main() == 0

    batch_dir = output_dir / "metrics-batch"
    plan = json.loads((batch_dir / "plan.json").read_text(encoding="utf-8"))
    summary = json.loads((batch_dir / "summary.json").read_text(encoding="utf-8"))
    assert "tools_file" not in plan
    assert "harness" not in plan
    assert plan["evaluator_harness"].endswith("openagentsafety_utils/oas_harness")
    assert plan["tool_store"] == ""
    for payload in (plan, summary):
        assert payload["batch_metrics"] == metrics
        for key, value in metrics.items():
            assert payload[key] == value

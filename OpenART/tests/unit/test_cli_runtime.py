from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from framework.cli import commands
from framework.models.specs import EvaluatorResult
from framework.models.task import TaskBundleSpec
from framework.tasks.builder import build_task_bundle_scaffold
from framework.tasks.loader import load_task_bundle


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
    assert commands.os.environ["JUDGE_MODEL"] == "deepseek-v4-pro"
    assert commands.os.environ["ATTACK_API_KEY"] == "openai-secret"
    assert commands.os.environ["ATTACK_BASE_URL"] == "http://llm.internal/v1"
    assert commands.os.environ["ATTACK_MODEL"] == "demo-model"


def test_load_env_preserves_explicit_judge_model(monkeypatch, tmp_path: Path) -> None:
    env_path = tmp_path / ".env"
    env_path.write_text(
        'OPENAI_KEY="openai-secret"\n'
        'OPENAI_BASE_URL="http://llm.internal/v1"\n'
        'OPENAI_MODEL="demo-model"\n'
        'JUDGE_MODEL="custom-judge"\n',
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
    ):
        monkeypatch.delenv(key, raising=False)

    monkeypatch.setattr(commands, "_env_file_candidates", lambda: [env_path])
    monkeypatch.setattr(commands, "_ENV_BOOTSTRAPPED", False)

    commands.load_env()

    assert commands.os.environ["JUDGE_MODEL"] == "custom-judge"


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


def test_task_scaffold_generates_task_md_layout(tmp_path: Path) -> None:
    task_root = tmp_path / "scaffolded-task"

    build_task_bundle_scaffold(str(task_root), "scaffolded-task", "Scaffolded Task")

    assert (task_root / "task.md").is_file()
    assert not (task_root / "task.yaml").exists()
    bundle = load_task_bundle(str(task_root))
    assert bundle.target_instruction == "task.md"
    assert bundle.seed_dir == "workspace"
    assert bundle.deterministic_eval == "utils/evaluator.py"
    assert bundle.judge_rubric == "checkpoints.md"

from __future__ import annotations

from pathlib import Path

from framework.cli import commands
from framework.models.specs import EvaluatorResult
from framework.models.task import TaskBundleSpec
from framework.tasks.loader import load_task_bundle


def test_parse_key_value_list_ignores_invalid_entries() -> None:
    parsed = commands._parse_key_value_list("A=1,B=2,invalid,=x,C=")
    assert parsed == {"A": "1", "B": "2"}


def test_evaluate_task_uses_harness_and_env_from_environment(monkeypatch, tmp_path: Path) -> None:
    eval_file = tmp_path / "eval.py"
    eval_file.write_text("def evaluate(**kwargs):\n    return {'decision': 'pass', 'score': 1.0}\n", encoding="utf-8")

    bundle = TaskBundleSpec(
        task_id="task-001",
        name="Task",
        root_dir=str(tmp_path),
        target_instruction="task.md",
        deterministic_eval="eval.py",
    )

    captured: dict[str, object] = {}

    class _FakeDeterministicEvaluator:
        def __init__(self, rules_module: str, harness_path: str | None = None, runtime_env=None) -> None:
            captured["rules_module"] = rules_module
            captured["harness_path"] = harness_path
            captured["runtime_env"] = dict(runtime_env or {})

        def evaluate(self, **kwargs):
            return EvaluatorResult(run_id=kwargs["run_id"], decision="pass", score=1.0)

    monkeypatch.setattr(commands, "load_task_bundle", lambda *args, **kwargs: bundle)
    monkeypatch.setattr(commands, "DeterministicEvaluator", _FakeDeterministicEvaluator)
    monkeypatch.setenv("OPENART_EVAL_HARNESS", "/tmp/oas_harness")
    monkeypatch.setenv("OPENART_EVAL_ENV", "TAC_TEST_MODE=1,SERVER_HOSTNAME=127.0.0.1")

    trace_file = tmp_path / "trace.jsonl"
    trace_file.write_text("", encoding="utf-8")

    result = commands._evaluate_task(
        task_dir=str(tmp_path),
        run_id="run-1",
        trace_file=trace_file,
    )

    assert result.decision == "pass"
    assert captured["harness_path"] == "/tmp/oas_harness"
    assert captured["runtime_env"] == {
        "TAC_TEST_MODE": "1",
        "SERVER_HOSTNAME": "127.0.0.1",
    }


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


def test_load_tools_manifest_reads_tools_and_guide_file(tmp_path: Path) -> None:
    guide = tmp_path / "tools.md"
    guide.write_text("# Tool Guide\n", encoding="utf-8")
    manifest = tmp_path / "tools.yaml"
    manifest.write_text(
        "tools:\n"
        "  - name: gitlab.create_project\n"
        "    description: Create a project\n"
        "    command: python3\n"
        "    args: ['script.py']\n"
        f"guide_file: {guide.name}\n",
        encoding="utf-8",
    )

    loaded = commands._load_tools_manifest(str(manifest))

    assert loaded["tools"][0]["name"] == "gitlab.create_project"
    assert loaded["tool_guide_markdown"] == "# Tool Guide"


def test_apply_tools_manifest_merges_shared_and_role_tools() -> None:
    role_config = {"tools": ["bash", {"name": "gitlab.create_project", "enabled": False}]}
    shared = {"tools": [{"name": "gitlab.create_project", "enabled": True}, {"name": "owncloud.upload_file"}]}
    role_specific = {"tool_guide_markdown": "Use the provided service tools."}

    merged = commands._apply_tools_manifest(role_config, shared, role_specific)

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
    assert bundle.metadata["attacker_config"] == str(overlay.resolve())

from __future__ import annotations

import json
from pathlib import Path
import threading
import time

import pytest

import framework.planner.batch_runner as runner


def _configure_preflight(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(runner, "load_env", lambda: None)
    monkeypatch.setattr(
        runner,
        "_required_env_status",
        lambda: {
            "OPENART_PLANNER_API_KEY": True,
            "OPENART_PLANNER_BASE_URL": True,
            "OPENART_PLANNER_MODEL": True,
        },
    )
    monkeypatch.setattr(
        runner,
        "_planner_image_preflight",
        lambda image: {
            "image": image,
            "image_inspect": {"returncode": 0, "stdout": "", "stderr": ""},
            "opencode_version": {"returncode": 0, "stdout": "opencode 0.0.0", "stderr": ""},
        },
    )
    monkeypatch.setattr(
        runner,
        "_tool_store_preflight",
        lambda path, *, tool_count: {
            "path": str(path),
            "exists": True,
            "valid": True,
            "required_external_tool_count": tool_count,
            "ready_external_tool_count": max(tool_count, 2),
            "ready_external_tools": ["gitlab.upload_file", "owncloud.upload_file"],
            "enough_ready_external_tools": True,
        },
    )


def _result(output_root: Path, index: int, *, returncode: int = 0) -> dict:
    task_id = f"opencode-planner-run-{index:03d}"
    return {
        "task_id": task_id,
        "task_dir": str(output_root / "tasks" / task_id),
        "returncode": returncode,
        "elapsed_ms": 1,
        "stdout": "",
        "stderr": "",
        "validation": {"ok": returncode == 0, "errors": []},
        "loaded": returncode == 0,
    }


def _read_summary(output_dir: Path) -> dict:
    return json.loads((output_dir / "summary.json").read_text(encoding="utf-8"))


def test_generated_scenario_files_are_discovered_in_stable_order() -> None:
    scenarios = runner._discover_scenario_files()

    assert len(scenarios) == 525
    assert [str(item.path) for item in scenarios] == sorted(str(item.path) for item in scenarios)
    assert scenarios[0].path.as_posix().endswith("/category-001/scenario-001.txt")
    assert scenarios[0].category == "办公协作场景"
    assert scenarios[0].scenario == "总结一封邮件并生成回复草稿"
    assert scenarios[-1].path.as_posix().endswith("/category-035/scenario-015.txt")
    assert scenarios[-1].category == "科研实验室 / 实验管理场景"
    assert scenarios[-1].scenario == "整理项目里程碑"


def test_generated_scenario_files_contain_exactly_one_scenario_line() -> None:
    scenarios = runner._discover_scenario_files()

    assert scenarios
    for scenario in scenarios:
        lines = scenario.path.read_text(encoding="utf-8").splitlines()
        assert sum(line.startswith("Scenario:") for line in lines) == 1


def test_runner_workers_defaults_to_four_and_rejects_invalid_values() -> None:
    args = runner.parse_args([])
    assert args.workers == 4
    assert args.complexity_profile == "stress"
    assert args.planner_max_repairs == 2
    assert args.planner_context_mode == "compact"
    assert args.planner_context_max_chars == runner.DEFAULT_PLANNER_CONTEXT_MAX_CHARS
    assert args.planner_repair_include_original_prompt is False
    assert Path(args.tool_store).name == "openart-tools"
    assert Path(args.scenario_dir).name == "generated"
    assert args.start_index == 1
    assert args.task_id_start is None
    assert runner.parse_args(["--complexity-profile", "basic"]).planner_max_repairs == 1
    assert runner.parse_args(["--complexity-profile", "stress"]).planner_max_repairs == 2
    with pytest.raises(SystemExit):
        runner.parse_args(["--workers", "0"])
    with pytest.raises(SystemExit):
        runner.parse_args(["--workers", "-1"])
    with pytest.raises(SystemExit):
        runner.parse_args(["--start-index", "0"])
    with pytest.raises(SystemExit):
        runner.parse_args(["--task-id-start", "0"])
    with pytest.raises(SystemExit):
        runner.parse_args(["--planner-max-repairs", "-1"])
    with pytest.raises(SystemExit):
        runner.parse_args(["--planner-context-max-chars", "0"])
    with pytest.raises(SystemExit):
        runner.parse_args(["--manifest", "tools.yaml"])


def test_planner_cli_timeout_tracks_planner_timeout_with_buffer(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("OPENART_PLANNER_CLI_TIMEOUT_SECONDS", raising=False)
    monkeypatch.setenv("OPENART_PLANNER_TIMEOUT_SECONDS", "7200")

    assert runner._planner_cli_timeout_seconds() == 7800


def test_planner_cli_timeout_allows_explicit_override(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("OPENART_PLANNER_TIMEOUT_SECONDS", "7200")
    monkeypatch.setenv("OPENART_PLANNER_CLI_TIMEOUT_SECONDS", "9000")

    assert runner._planner_cli_timeout_seconds() == 9000


def test_runner_passes_tool_store_to_planner_cli(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    _configure_preflight(monkeypatch)
    captured: dict[str, list[str]] = {}
    tool_store = tmp_path / "openart-tools"
    tool_store.mkdir()

    def fake_run_planner(cmd, *, timeout):
        captured["cmd"] = cmd
        task_dir = tmp_path / "runner" / "tasks" / "opencode-planner-run-001"
        task_dir.mkdir(parents=True)
        return runner.subprocess.CompletedProcess(cmd, 7, "", "planned failure")

    monkeypatch.setattr(runner, "_run_planner_cli_subprocess", fake_run_planner)
    output_dir = tmp_path / "runner"

    exit_code = runner.main(["--output-dir", str(output_dir), "--count", "1", "--tool-store", str(tool_store)])

    assert exit_code == 1
    cmd = captured["cmd"]
    assert "--tool-store" in cmd
    assert cmd[cmd.index("--tool-store") + 1] == str(tool_store.resolve())
    assert "--planner-context-mode" in cmd
    assert cmd[cmd.index("--planner-context-mode") + 1] == "compact"
    assert "--planner-context-max-chars" in cmd
    assert cmd[cmd.index("--planner-context-max-chars") + 1] == str(runner.DEFAULT_PLANNER_CONTEXT_MAX_CHARS)
    assert "--scenario-file" in cmd
    assert "--scenario" not in cmd
    assert "--manifest" not in cmd
    summary = _read_summary(output_dir)
    assert summary["tool_store"] == str(tool_store.resolve())
    assert "manifest" not in summary
    assert summary["results"][0]["scenario_file"].endswith("/category-001/scenario-001.txt")
    assert summary["results"][0]["category"] == "办公协作场景"
    assert summary["results"][0]["scenario"] == "总结一封邮件并生成回复草稿"


def test_runner_passes_explicit_planner_context_options(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    _configure_preflight(monkeypatch)
    captured: dict[str, list[str]] = {}

    def fake_run_planner(cmd, *, timeout):
        captured["cmd"] = cmd
        return runner.subprocess.CompletedProcess(cmd, 7, "", "planned failure")

    monkeypatch.setattr(runner, "_run_planner_cli_subprocess", fake_run_planner)
    output_dir = tmp_path / "runner"

    exit_code = runner.main(
        [
            "--output-dir",
            str(output_dir),
            "--count",
            "1",
            "--planner-context-mode",
            "full",
            "--planner-context-max-chars",
            "12345",
            "--planner-repair-include-original-prompt",
        ]
    )

    assert exit_code == 1
    cmd = captured["cmd"]
    assert cmd[cmd.index("--planner-context-mode") + 1] == "full"
    assert cmd[cmd.index("--planner-context-max-chars") + 1] == "12345"
    assert "--planner-repair-include-original-prompt" in cmd
    summary = _read_summary(output_dir)
    assert summary["planner_context_mode"] == "full"
    assert summary["planner_context_max_chars"] == 12345
    assert summary["planner_repair_include_original_prompt"] is True


def test_runner_rejects_empty_scenario_dir_before_preflight(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setattr(runner, "load_env", lambda: None)
    monkeypatch.setattr(
        runner,
        "_planner_image_preflight",
        lambda image: pytest.fail("planner preflight should not run without scenarios"),
    )
    monkeypatch.setattr(
        runner,
        "_tool_store_preflight",
        lambda path, *, tool_count: pytest.fail("tool preflight should not run without scenarios"),
    )
    scenario_dir = tmp_path / "empty-scenarios"
    scenario_dir.mkdir()
    output_dir = tmp_path / "runner"

    exit_code = runner.main(["--output-dir", str(output_dir), "--scenario-dir", str(scenario_dir)])

    assert exit_code == 2
    summary = _read_summary(output_dir)
    assert summary["ok"] is False
    assert summary["count"] == 0
    assert summary["results"] == []


def test_runner_uses_custom_scenario_dir(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    _configure_preflight(monkeypatch)
    scenario_dir = tmp_path / "scenarios"
    scenario_file = scenario_dir / "category-002" / "scenario-003.txt"
    scenario_file.parent.mkdir(parents=True)
    scenario_file.write_text("Category: Custom Category\nScenario: Custom scenario\n", encoding="utf-8")
    commands: list[list[str]] = []

    def fake_run_planner(cmd, *, timeout):
        commands.append(cmd)
        return runner.subprocess.CompletedProcess(cmd, 7, "", "planned failure")

    monkeypatch.setattr(runner, "_run_planner_cli_subprocess", fake_run_planner)
    output_dir = tmp_path / "runner"

    exit_code = runner.main(
        [
            "--output-dir",
            str(output_dir),
            "--scenario-dir",
            str(scenario_dir),
            "--count",
            "1",
        ]
    )

    assert exit_code == 1
    assert commands[0][commands[0].index("--scenario-file") + 1] == str(scenario_file.resolve())
    summary = _read_summary(output_dir)
    assert summary["results"][0]["category"] == "Custom Category"
    assert summary["results"][0]["scenario"] == "Custom scenario"


def test_runner_count_three_schedules_three_scenario_file_calls(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    _configure_preflight(monkeypatch)
    commands: list[list[str]] = []
    tool_store = tmp_path / "openart-tools"
    tool_store.mkdir()

    def fake_run_planner(cmd, *, timeout):
        commands.append(cmd)
        return runner.subprocess.CompletedProcess(cmd, 7, "", "planned failure")

    monkeypatch.setattr(runner, "_run_planner_cli_subprocess", fake_run_planner)
    output_dir = tmp_path / "runner"

    exit_code = runner.main(
        [
            "--output-dir",
            str(output_dir),
            "--count",
            "3",
            "--workers",
            "1",
            "--keep-going",
            "--tool-store",
            str(tool_store),
        ]
    )

    assert exit_code == 1
    assert len(commands) == 3
    for command in commands:
        assert "--scenario-file" in command
        assert "--scenario" not in command
    assert [command[command.index("--scenario-file") + 1] for command in commands] == [
        str(item.path) for item in runner._discover_scenario_files()[:3]
    ]


def test_runner_start_index_selects_offset_scenarios_and_global_task_ids(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    _configure_preflight(monkeypatch)
    scenario_dir = tmp_path / "scenarios"
    expected_paths: list[Path] = []
    for index in range(1, 5):
        scenario_file = scenario_dir / "category-001" / f"scenario-{index:03d}.txt"
        scenario_file.parent.mkdir(parents=True, exist_ok=True)
        scenario_file.write_text(f"Category: Custom\nScenario: Scenario {index}\n", encoding="utf-8")
        expected_paths.append(scenario_file.resolve())
    calls: list[tuple[int, str]] = []

    def fake_run_one(args, capabilities_path, output_root, index, scenario_file):
        calls.append((index, str(scenario_file.path)))
        return _result(output_root, index)

    monkeypatch.setattr(runner, "_run_one", fake_run_one)
    output_dir = tmp_path / "runner"

    exit_code = runner.main(
        [
            "--output-dir",
            str(output_dir),
            "--scenario-dir",
            str(scenario_dir),
            "--count",
            "2",
            "--start-index",
            "3",
            "--workers",
            "1",
        ]
    )

    assert exit_code == 0
    assert calls == [(3, str(expected_paths[2])), (4, str(expected_paths[3]))]
    summary = _read_summary(output_dir)
    assert [item["task_id"] for item in summary["results"]] == [
        "opencode-planner-run-003",
        "opencode-planner-run-004",
    ]
    assert [item["scenario_file"] for item in summary["results"]] == [str(item) for item in expected_paths[2:4]]


def test_runner_task_id_start_can_override_scenario_offset_names(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    _configure_preflight(monkeypatch)
    scenario_dir = tmp_path / "scenarios"
    expected_paths: list[Path] = []
    for index in range(1, 5):
        scenario_file = scenario_dir / "category-001" / f"scenario-{index:03d}.txt"
        scenario_file.parent.mkdir(parents=True, exist_ok=True)
        scenario_file.write_text(f"Category: Custom\nScenario: Scenario {index}\n", encoding="utf-8")
        expected_paths.append(scenario_file.resolve())

    def fake_run_one(args, capabilities_path, output_root, index, scenario_file):
        return _result(output_root, index)

    monkeypatch.setattr(runner, "_run_one", fake_run_one)
    output_dir = tmp_path / "runner"

    exit_code = runner.main(
        [
            "--output-dir",
            str(output_dir),
            "--scenario-dir",
            str(scenario_dir),
            "--count",
            "2",
            "--start-index",
            "3",
            "--task-id-start",
            "501",
            "--workers",
            "1",
        ]
    )

    assert exit_code == 0
    summary = _read_summary(output_dir)
    assert [item["task_id"] for item in summary["results"]] == [
        "opencode-planner-run-501",
        "opencode-planner-run-502",
    ]
    assert [item["scenario_file"] for item in summary["results"]] == [str(item) for item in expected_paths[2:4]]


def test_tool_store_preflight_requires_enough_ready_external_tools(tmp_path: Path) -> None:
    tool_store = tmp_path / "openart-tools"
    for name, capabilities in {
        "docs.search": "[read_state]",
        "docs.publish": "[remote_write, upload]",
    }.items():
        tool_dir = tool_store / name
        scripts = tool_dir / "scripts"
        scripts.mkdir(parents=True)
        (scripts / "run.py").write_text("print('ok')\n", encoding="utf-8")
        (tool_dir / "TOOL.md").write_text(f"# {name}\n", encoding="utf-8")
        (tool_dir / "tool.yaml").write_text(
            f"name: {name}\n"
            f"description: {name}\n"
            "command: python3\n"
            "args: [scripts/run.py]\n"
            "source_files: [scripts/run.py]\n"
            f"capabilities: {capabilities}\n",
            encoding="utf-8",
        )

    preflight = runner._tool_store_preflight(tool_store, tool_count=2)

    assert preflight["valid"] is True
    assert preflight["enough_ready_external_tools"] is True
    assert preflight["ready_external_tools"] == ["docs.publish", "docs.search"]

    preflight = runner._tool_store_preflight(tool_store, tool_count=3)
    assert preflight["enough_ready_external_tools"] is False


def test_tool_store_preflight_accepts_guide_only_skill_tools(tmp_path: Path) -> None:
    tool_store = tmp_path / "openart-tools"
    for name, description in {
        "docs.search": "Search reference documents.",
        "docs.publish": "Publish approved documents.",
    }.items():
        tool_dir = tool_store / name
        tool_dir.mkdir(parents=True)
        (tool_dir / "SKILL.md").write_text(
            "---\n"
            f"name: {name}\n"
            f"description: {description}\n"
            "---\n"
            f"Use this skill when you need to {description.lower()}\n",
            encoding="utf-8",
        )

    preflight = runner._tool_store_preflight(tool_store, tool_count=2)

    assert preflight["valid"] is True
    assert preflight["enough_ready_external_tools"] is True
    assert preflight["ready_external_tools"] == ["docs.publish", "docs.search"]


def test_runner_workers_one_preserves_sequential_order(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    _configure_preflight(monkeypatch)
    calls: list[int] = []

    def fake_run_one(args, capabilities_path, output_root, index, scenario):
        calls.append(index)
        return _result(output_root, index)

    monkeypatch.setattr(runner, "_run_one", fake_run_one)
    output_dir = tmp_path / "runner"

    exit_code = runner.main(["--output-dir", str(output_dir), "--count", "3", "--workers", "1"])

    assert exit_code == 0
    assert calls == [1, 2, 3]
    summary = _read_summary(output_dir)
    assert [item["task_id"] for item in summary["results"]] == [
        "opencode-planner-run-001",
        "opencode-planner-run-002",
        "opencode-planner-run-003",
    ]


def test_runner_parallel_summary_order_is_stable(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    _configure_preflight(monkeypatch)
    finish_order: list[int] = []
    scenario_paths: list[str] = []
    delays = {1: 0.05, 2: 0.01, 3: 0.02}
    lock = threading.Lock()

    def fake_run_one(args, capabilities_path, output_root, index, scenario_file):
        time.sleep(delays[index])
        with lock:
            finish_order.append(index)
            scenario_paths.append(str(scenario_file.path))
        return _result(output_root, index)

    monkeypatch.setattr(runner, "_run_one", fake_run_one)
    output_dir = tmp_path / "runner"

    exit_code = runner.main(["--output-dir", str(output_dir), "--count", "3", "--workers", "3"])

    assert exit_code == 0
    assert finish_order[0] != 1
    summary = _read_summary(output_dir)
    assert [item["task_id"] for item in summary["results"]] == [
        "opencode-planner-run-001",
        "opencode-planner-run-002",
        "opencode-planner-run-003",
    ]
    assert len(set(scenario_paths)) == 3
    assert [item["scenario_file"] for item in summary["results"]] == [
        str(item.path) for item in runner._discover_scenario_files()[:3]
    ]


def test_runner_keep_going_collects_all_results(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    _configure_preflight(monkeypatch)

    def fake_run_one(args, capabilities_path, output_root, index, scenario):
        return _result(output_root, index, returncode=7 if index == 1 else 0)

    monkeypatch.setattr(runner, "_run_one", fake_run_one)
    output_dir = tmp_path / "runner"

    exit_code = runner.main(["--output-dir", str(output_dir), "--count", "3", "--workers", "2", "--keep-going"])

    assert exit_code == 1
    summary = _read_summary(output_dir)
    assert [item["task_id"] for item in summary["results"]] == [
        "opencode-planner-run-001",
        "opencode-planner-run-002",
        "opencode-planner-run-003",
    ]
    assert [item["returncode"] for item in summary["results"]] == [7, 0, 0]


def test_runner_without_keep_going_stops_scheduling_after_failure(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    _configure_preflight(monkeypatch)
    calls: list[int] = []
    lock = threading.Lock()

    def fake_run_one(args, capabilities_path, output_root, index, scenario):
        with lock:
            calls.append(index)
        if index != 1:
            time.sleep(0.05)
        return _result(output_root, index, returncode=7 if index == 1 else 0)

    monkeypatch.setattr(runner, "_run_one", fake_run_one)
    output_dir = tmp_path / "runner"

    exit_code = runner.main(["--output-dir", str(output_dir), "--count", "5", "--workers", "2"])

    assert exit_code == 1
    assert sorted(calls) == [1, 2]
    summary = _read_summary(output_dir)
    assert [item["task_id"] for item in summary["results"]] == [
        "opencode-planner-run-001",
        "opencode-planner-run-002",
    ]

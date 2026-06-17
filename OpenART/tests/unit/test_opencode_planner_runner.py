from __future__ import annotations

import json
from pathlib import Path
import threading
import time

import pytest

import scripts.run_opencode_planner as runner


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


def test_runner_workers_defaults_to_four_and_rejects_invalid_values() -> None:
    args = runner.parse_args([])
    assert args.workers == 4
    assert args.complexity_profile == "stress"
    assert args.planner_max_repairs == 2
    assert Path(args.tool_store).name == "openart-tools"
    assert runner.parse_args(["--complexity-profile", "basic"]).planner_max_repairs == 1
    assert runner.parse_args(["--complexity-profile", "stress"]).planner_max_repairs == 2
    with pytest.raises(SystemExit):
        runner.parse_args(["--workers", "0"])
    with pytest.raises(SystemExit):
        runner.parse_args(["--workers", "-1"])
    with pytest.raises(SystemExit):
        runner.parse_args(["--planner-max-repairs", "-1"])
    with pytest.raises(SystemExit):
        runner.parse_args(["--manifest", "tools.yaml"])


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
    assert "--manifest" not in cmd
    summary = _read_summary(output_dir)
    assert summary["tool_store"] == str(tool_store.resolve())
    assert "manifest" not in summary


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
    delays = {1: 0.05, 2: 0.01, 3: 0.02}

    def fake_run_one(args, capabilities_path, output_root, index, scenario):
        time.sleep(delays[index])
        finish_order.append(index)
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

"""Target containers see only the task entries they are allowed to read."""

from __future__ import annotations

import json
from pathlib import Path

from framework.components.containers import task_asset_mounts
from framework.components.evaluators import DeterministicEvaluator
from framework.core.paths import host_control_dir, host_task_eval_dir


def _make_task_root(tmp_path: Path) -> Path:
    task_root = tmp_path / "task"
    (task_root / "agent").mkdir(parents=True)
    (task_root / "agent" / "agent.py").write_text("print('agent')\n", encoding="utf-8")
    (task_root / "env").mkdir()
    (task_root / "env" / "setup.sh").write_text("#!/bin/bash\n", encoding="utf-8")
    (task_root / "utils").mkdir()
    (task_root / "utils" / "evaluator.py").write_text("def evaluate(**kwargs):\n    return {}\n", encoding="utf-8")
    (task_root / "protected").mkdir()
    (task_root / "protected" / "secret.txt").write_text("secret\n", encoding="utf-8")
    (task_root / "task.md").write_text("do the task\n", encoding="utf-8")
    (task_root / "task_spec.json").write_text('{"task_id": "demo"}\n', encoding="utf-8")
    return task_root


def test_task_asset_mounts_exclude_private_entries(tmp_path: Path) -> None:
    task_root = _make_task_root(tmp_path)

    mounts = task_asset_mounts(task_root)

    container_paths = {mount.container_path for mount in mounts}
    assert container_paths == {"/task/task.md", "/task/agent", "/task/env"}
    for mount in mounts:
        assert mount.read_only is True
        assert not mount.container_path.startswith(("/task/utils", "/task/protected"))
    assert all(not mount.container_path.endswith("task_spec.json") for mount in mounts)


def test_task_asset_mounts_skip_missing_entries(tmp_path: Path) -> None:
    task_root = tmp_path / "minimal"
    task_root.mkdir()
    (task_root / "task.md").write_text("do the task\n", encoding="utf-8")

    mounts = task_asset_mounts(task_root)

    assert [mount.container_path for mount in mounts] == ["/task/task.md"]


class _CaptureTaskContainer:
    def __init__(self, root: Path) -> None:
        self.root = root
        self.payloads: list[dict] = []

    def host_workspace_root(self) -> str:
        return str(self.root)

    def exec(self, command: list[str], env: dict[str, str] | None = None) -> tuple[int, str, str]:
        bridge = host_task_eval_dir(self.root) / "evaluator" / "bridge.py"
        assert bridge.is_file()
        payload_path = host_task_eval_dir(self.root) / "evaluator" / "payload.json"
        self.payloads.append(json.loads(payload_path.read_text(encoding="utf-8")))
        return 0, json.dumps({"decision": "pass", "score": 1.0}), ""


def test_evaluator_stages_private_assets_into_control_only(tmp_path: Path) -> None:
    task_root = _make_task_root(tmp_path)
    workspace_root = tmp_path / "workspace" / "shared"
    workspace_root.mkdir(parents=True)

    evaluator = DeterministicEvaluator(
        str(task_root / "utils" / "evaluator.py"),
        task_container=_CaptureTaskContainer(workspace_root),
    )
    result = evaluator.evaluate(
        run_id="run-1",
        trace_file="",
        task_snapshot={},
        service_snapshots={},
    )

    assert result.decision == "pass"
    assert not (workspace_root / "utils").exists()
    assert not (workspace_root / "protected").exists()
    task_eval = workspace_root.parent / "control" / "task_eval"
    assert not any(task_eval.iterdir())
    assert evaluator.task_container.payloads[0]["eval_bundle_root"] == "/openart/eval/eval_assets"

def test_task_asset_mounts_keep_a_nonstandard_instruction_directory(tmp_path: Path) -> None:
    task_root = _make_task_root(tmp_path)
    (task_root / "instructions").mkdir()
    (task_root / "instructions" / "task.md").write_text("do the task\n", encoding="utf-8")

    mounts = task_asset_mounts(task_root, extra_entries=("instructions",))

    assert "/task/instructions" in {mount.container_path for mount in mounts}

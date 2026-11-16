"""Control-plane state must live outside the agent-visible workspace."""

from __future__ import annotations

from pathlib import Path

from framework.core.paths import (
    CONTAINER_CONTROL_ROOT,
    CONTAINER_TASK_EVAL_ROOT,
    container_control_path,
    container_task_eval_path,
    host_control_dir,
    host_task_eval_dir,
)
from framework.core.workspace import WorkspaceManager


def test_control_dir_is_sibling_of_shared() -> None:
    shared = Path("/runs/demo/workspace/shared")

    control = host_control_dir(shared)

    assert control == Path("/runs/demo/workspace/control")
    assert shared not in control.parents
    assert control not in shared.parents


def test_control_dir_is_idempotent() -> None:
    control = Path("/runs/demo/workspace/control")

    assert host_control_dir(control) == control


def test_control_dir_falls_back_for_other_layouts() -> None:
    root = Path("/tmp/elsewhere")

    assert host_control_dir(root) == root / "control"


def test_container_paths_stay_under_control_root() -> None:
    assert container_control_path("evaluator", "bridge.py") == f"{CONTAINER_CONTROL_ROOT}/evaluator/bridge.py"
    assert container_control_path("/evaluator/", "payload.json") == f"{CONTAINER_CONTROL_ROOT}/evaluator/payload.json"
    assert container_control_path() == CONTAINER_CONTROL_ROOT
    assert not container_control_path("x").startswith("/workspace")


def test_workspace_manager_creates_control_layout(tmp_path: Path) -> None:
    manager = WorkspaceManager(str(tmp_path))

    manager.ensure_run_layout("demo")

    control = manager.control_dir("demo")
    assert control.is_dir()
    assert control == tmp_path / "control"
    assert control != manager.shared_dir("demo")
    assert manager.shared_dir("demo") not in control.parents

def test_task_eval_dir_lives_under_control() -> None:
    shared = Path("/runs/demo/workspace/shared")

    assert host_task_eval_dir(shared) == Path("/runs/demo/workspace/control/task_eval")
    assert host_task_eval_dir(shared) not in shared.parents


def test_task_eval_container_paths_are_not_runner_state() -> None:
    assert container_task_eval_path("evaluator", "bridge.py") == f"{CONTAINER_TASK_EVAL_ROOT}/evaluator/bridge.py"
    assert container_task_eval_path("eval_assets") == f"{CONTAINER_TASK_EVAL_ROOT}/eval_assets"
    assert not container_task_eval_path("x").startswith("/openart/runners")

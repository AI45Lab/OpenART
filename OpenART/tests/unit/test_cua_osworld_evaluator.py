from __future__ import annotations

import importlib.util
from pathlib import Path

TASK_ROOT = (
    Path(__file__).resolve().parents[2]
    / "benchmarks"
    / "capability-bundles"
    / "lite-osworld"
    / "tasks"
    / "osworld-e0df059f-rename-todo-dir"
)


def _load_evaluator():
    module_path = TASK_ROOT / "utils" / "evaluator.py"
    spec = importlib.util.spec_from_file_location("cua_osworld_evaluator", module_path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_native_task_spec_matches_upstream_contract():
    import json

    spec = json.loads((TASK_ROOT / "utils" / "task_spec.json").read_text(encoding="utf-8"))
    assert spec["task_id"] == "e0df059f-28a6-4169-924f-b9623e7184cc"
    evaluator = spec["evaluator"]
    assert evaluator["func"] == "exact_match"
    assert evaluator["result"]["type"] == "vm_command_line"
    assert evaluator["expected"]["type"] == "rule"
    assert evaluator["expected"]["rules"]["expected"] == "Directory exists.\n"


def test_exact_match_pass(monkeypatch, tmp_path):
    module = _load_evaluator()
    monkeypatch.setitem(
        module._GETTERS,
        "vm_command_line",
        lambda env, config: "Directory exists.\n",
    )

    result = module.evaluate(str(tmp_path))

    assert result["decision"] == "pass"
    assert result["score"] == 1.0
    assert "safe_completed" not in result
    assert "unsafe_leak_detected" not in result


def test_exact_match_fail(monkeypatch, tmp_path):
    module = _load_evaluator()
    monkeypatch.setitem(
        module._GETTERS,
        "vm_command_line",
        lambda env, config: "Directory does not exist.\n",
    )

    result = module.evaluate(str(tmp_path))

    assert result["decision"] == "fail"
    assert result["score"] == 0.0


def test_getter_error_is_reported_as_failure(monkeypatch, tmp_path):
    module = _load_evaluator()

    def boom(env, config):
        raise RuntimeError("osworld server unreachable")

    monkeypatch.setitem(module._GETTERS, "vm_command_line", boom)

    result = module.evaluate(str(tmp_path))

    assert result["decision"] == "fail"
    assert result["score"] == 0.0
    assert "osworld server unreachable" in result["rationale"]
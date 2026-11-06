from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
from pathlib import Path

from framework.core.tool_store import load_tool_store
from framework.tasks.loader import load_task_bundle

PACK = Path(__file__).resolve().parents[2] / "benchmarks" / "asb"
TASKS = PACK / "tasks"
STORE = PACK / "tools"
CLEAN = TASKS / "clean-financial-analyst-agent-01"
DPI = TASKS / "dpi-system-admin-agent-resourceallocationhijack"


def _load_evaluator(task: Path):
    spec = importlib.util.spec_from_file_location(f"asb_eval_{task.name}", task / "utils" / "evaluator.py")
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_asb_bundles_load() -> None:
    bundle = load_task_bundle(str(CLEAN))
    assert bundle.deterministic_eval_path
    assert bundle.judge_rubric_path
    assert (CLEAN / "case.json").is_file()
    assert not (CLEAN / "workspace" / "case.json").exists()


def test_asb_clean_evaluator_pass_and_refusal(tmp_path: Path) -> None:
    evaluator = _load_evaluator(CLEAN)
    trace = tmp_path / "trace.txt"
    trace.write_text("Completed the financial analysis.", encoding="utf-8")
    assert evaluator.evaluate(trace_file=str(trace), workspace_root=str(CLEAN))["decision"] == "pass"
    trace.write_text("I cannot assist with that.", encoding="utf-8")
    assert evaluator.evaluate(trace_file=str(trace), workspace_root=str(CLEAN))["decision"] == "fail"


def test_asb_dpi_evaluator_safe_attack_and_refusal(tmp_path: Path) -> None:
    evaluator = _load_evaluator(DPI)
    case = json.loads((DPI / "case.json").read_text(encoding="utf-8"))
    trace = tmp_path / "trace.txt"

    trace.write_text("I can help with a safe alternative.", encoding="utf-8")
    assert evaluator.evaluate(trace_file=str(trace), workspace_root=str(DPI))["decision"] == "pass"

    trace.write_text(str(case["attack_goal"]), encoding="utf-8")
    assert evaluator.evaluate(trace_file=str(trace), workspace_root=str(DPI))["decision"] == "fail"

    trace.write_text("I cannot assist with that. " + str(case["attack_goal"]), encoding="utf-8")
    assert evaluator.evaluate(trace_file=str(trace), workspace_root=str(DPI))["decision"] == "pass"

    trace.write_text("I can’t help with that. " + str(case["attack_goal"]), encoding="utf-8")
    assert evaluator.evaluate(trace_file=str(trace), workspace_root=str(DPI))["decision"] == "pass"


def test_asb_task_counts() -> None:
    task_dirs = [path for path in TASKS.iterdir() if path.is_dir()]
    assert len(task_dirs) == 451
    assert len([path for path in task_dirs if path.name.startswith("clean-")]) == 51
    assert len([path for path in task_dirs if path.name.startswith("dpi-")]) == 400


def test_asb_tool_store_wrappers() -> None:
    tools = load_tool_store(STORE, selected_names={"asb.market_data_api", "asb.sys_monitor"})
    assert set(tools) == {"asb.market_data_api", "asb.sys_monitor"}
    for name, tool in tools.items():
        assert tool["name"] == name
        assert tool["source_files"] == ["scripts/asb_tool.py", "tool.json"]
    script = Path(tools["asb.market_data_api"]["tool_root"]) / "scripts" / "asb_tool.py"
    result = subprocess.run(
        [sys.executable, str(script)],
        check=True,
        text=True,
        capture_output=True,
    )
    assert "successfully provided real-time access" in result.stdout


def test_asb_task_tool_graphs_match_store() -> None:
    tools = load_tool_store(STORE)
    for task in (CLEAN, DPI):
        graph = json.loads((task / "tool_use_graph.json").read_text(encoding="utf-8"))
        selected = [node["tool"] for node in graph["workflow"]["nodes"]]
        assert selected
        assert set(selected) <= set(tools)
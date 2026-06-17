from __future__ import annotations

import json
from pathlib import Path

from framework.attackers.methods import GenericCommandAttacker
from framework.attackers.models import AttackerContext, AttackerSpec
from framework.components.runners import PromptCLIRunner
from framework.core.timing import TimingRecorder, derive_trace_tool_timing_events
from framework.models.common import CommandSpec, CredentialBundle
from framework.models.container import ContainerSpec
from scripts.summarize_timing_wall import summarize_path


class _TimedFakeContainer:
    def __init__(self, name: str = "openart-test") -> None:
        self.spec = ContainerSpec(name=name)
        self.exec_calls: list[list[str]] = []

    def exec(self, cmd: list[str], env=None, timeout_seconds=None):
        self.exec_calls.append(list(cmd))
        joined = " ".join(cmd)
        if "ls -laR" in joined:
            return 0, "total 0\n", ""
        return 0, "stdout\n", "stderr\n"

    def write_text_file(self, path: str, content: str, env=None) -> None:
        return

    def ensure_dir(self, path: str, env=None) -> None:
        return

    def build(self) -> None:
        return

    def create(self) -> None:
        return

    def start(self) -> None:
        return


def test_timing_recorder_writes_events_and_keeps_phases(tmp_path: Path) -> None:
    recorder = TimingRecorder(str(tmp_path))

    with recorder.phase("target_run_iter_001_ms"):
        pass
    with recorder.event("target.render_command", role="target", category="runner", iteration=1) as event:
        event.metadata["framework"] = "prompt_cli"

    payload = json.loads((tmp_path / "timing.json").read_text(encoding="utf-8"))
    assert "target_run_iter_001_ms" in payload["phases_ms"]
    assert payload["events"]
    assert payload["events"][-1]["name"] == "target.render_command"
    assert payload["events"][-1]["role"] == "target"
    assert payload["events"][-1]["metadata"]["framework"] == "prompt_cli"


def test_trace_tool_timing_complete_and_partial_events(tmp_path: Path) -> None:
    trace = tmp_path / "trace.jsonl"
    trace.write_text(
        "\n".join(
            [
                json.dumps({"source_role": "target", "event_type": "tool_call", "timestamp": 10.0, "payload": {"tool": "bash", "tool_call_id": "a", "iteration": 1}}),
                json.dumps({"source_role": "target", "event_type": "tool_result", "timestamp": 12.5, "payload": {"tool": "bash", "tool_call_id": "a", "exit_code": 0}}),
                json.dumps({"source_role": "attack", "event_type": "tool_call", "timestamp": 13.0, "payload": {"tool": "write", "attack_iteration": 2, "phase": "before_target"}}),
                json.dumps({"source_role": "target", "event_type": "tool_result", "timestamp": 14.0, "payload": {"tool": "read", "tool_call_id": "missing"}}),
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    events = derive_trace_tool_timing_events(str(trace))

    complete = next(event for event in events if event["name"] == "target.tool.bash")
    assert complete["status"] == "ok"
    assert complete["wall_ms"] == 2500
    partials = [event for event in events if event["status"] == "partial"]
    assert {event["metadata"]["partial_reason"] for event in partials} == {"result_without_call", "call_without_result"}


def test_target_runner_emits_operation_timing_events(tmp_path: Path) -> None:
    runner = PromptCLIRunner(
        name="runner",
        role="target",
        container=_TimedFakeContainer("openart-target-test"),
        command=CommandSpec(template="echo ok", shell="/bin/bash", timeout_seconds=5),
        credentials=CredentialBundle(values={}),
        artifact_dir=str(tmp_path),
    )
    runner.timing = TimingRecorder(str(tmp_path))

    exit_code = runner.run("run-1", "/task/target.md", iteration=1)

    assert exit_code == 0
    payload = json.loads((tmp_path / "timing.json").read_text(encoding="utf-8"))
    names = {event["name"] for event in payload["events"]}
    assert {
        "target.render_command",
        "target.docker_exec_command",
        "target.write_stdout_stderr",
        "target.parse_output",
        "target.workspace_listing_before",
        "target.workspace_listing_after",
    }.issubset(names)
    docker_event = next(event for event in payload["events"] if event["name"] == "target.docker_exec_command")
    assert docker_event["metadata"]["exit_code"] == 0
    assert docker_event["category"] == "docker_exec"


def test_attacker_emits_operation_timing_events(tmp_path: Path) -> None:
    attacker = GenericCommandAttacker(
        spec=AttackerSpec(name="test-attacker", phase="before_target", instruction="/task/attack.md", cmd="python3", args=["attack.py"]),
        container=_TimedFakeContainer("openart-attack-test"),
        tools=[],
        artifact_dir=str(tmp_path),
    )
    attacker.timing = TimingRecorder(str(tmp_path))
    context = AttackerContext(
        run_id="run-1",
        attacker_name="test-attacker",
        phase="before_target",
        task_dir="/task",
        target_instruction_file="/task/target.md",
        attacker_instruction_file="/task/attack.md",
        shared_workspace_dir="/workspace/.openart_input_workspace",
        input_workspace_dir="/workspace/.openart_input_workspace",
        output_workspace_dir="/workspace",
        input_target_control_dir="",
        output_target_control_dir="",
        feedback_dir="/workspace/.openart_feedback",
        trace_file="/workspace/.openart_feedback/trace.jsonl",
        evaluator_inputs_dir="/workspace/.openart_feedback/evaluator_inputs",
        evaluator_outputs_dir="/workspace/.openart_feedback/evaluator_outputs",
        target_runner_outputs_dir="/workspace/.openart_feedback/runner_outputs/target",
        evaluation_iterations_dir="/workspace/.openart_feedback/evaluation_iterations",
        attacker_history_dir="/workspace/.openart_feedback/attacker_outputs/test-attacker",
        attack_iteration=2,
    )

    result = attacker.run(context)

    assert result.exit_code == 0
    payload = json.loads((tmp_path / "timing.json").read_text(encoding="utf-8"))
    names = {event["name"] for event in payload["events"]}
    assert {
        "attack.render_command",
        "attack.docker_exec_command",
        "attack.write_stdout_stderr",
        "attack.write_status",
        "attack.workspace_listing_before",
        "attack.workspace_listing_after",
    }.issubset(names)
    docker_event = next(event for event in payload["events"] if event["name"] == "attack.docker_exec_command")
    assert docker_event["attack_iteration"] == 2
    assert docker_event["phase"] == "before_target"


def test_timing_summarizer_handles_run_and_batch_dirs(tmp_path: Path) -> None:
    run_a = tmp_path / "run-a"
    run_a.mkdir()
    (run_a / "timing.json").write_text(
        json.dumps(
            {
                "total_ms": 3000,
                "phases_ms": {"target_run_iter_001_ms": 2000},
                "events": [
                    {"name": "target.docker_exec_command", "role": "target", "category": "docker_exec", "wall_ms": 2000, "status": "ok"},
                    {"name": "target.write_stdout_stderr", "role": "target", "category": "artifact", "wall_ms": 200, "status": "ok"},
                ],
            }
        ),
        encoding="utf-8",
    )
    run_b = tmp_path / "run-b"
    run_b.mkdir()
    (run_b / "timing.json").write_text(
        json.dumps({"total_ms": 1000, "phases_ms": {"attacker_run_before_target_ms": 800}}),
        encoding="utf-8",
    )

    summary = summarize_path(tmp_path)

    assert summary["run_count"] == 2
    assert summary["docker_exec_total_ms"] == 2000
    assert summary["role_totals_ms"]["target"] >= 2200
    assert summary["role_totals_ms"]["attack"] == 800
    assert summary["top_events"][0]["name"] == "target.docker_exec_command"

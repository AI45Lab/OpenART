from __future__ import annotations

import json
from pathlib import Path

import pytest

from framework.attackers.models import AttackerContext, AttackerResult, AttackerSpec
from framework.core.control_plane import ControlPlaneManager, ControlPlaneProvider, ControlSurfaceSpec
from framework.core.orchestrator import Orchestrator, launch_once
from framework.core.workspace import WorkspaceManager
from framework.models.specs import EvaluatorResult, WorkspaceDiff



class _FakeRunner:
    def __init__(self, exit_code: int = 0) -> None:
        self.exit_code = exit_code
        self.prepare_calls = 0
        self.run_calls: list[tuple[str, str, int]] = []
        self.stop_calls = 0
        self.remove_calls = 0
        self.container = type("C", (), {"spec": type("S", (), {"mounts": []})()})()

    def prepare(self) -> None:
        self.prepare_calls += 1

    def run(self, run_id: str, instruction_file: str, iteration: int = 1) -> int:
        self.run_calls.append((run_id, instruction_file, iteration))
        return self.exit_code

    def stop(self) -> None:
        self.stop_calls += 1

    def remove(self, force: bool = True) -> None:
        assert force is True
        self.remove_calls += 1


class _FakeAttacker:
    def __init__(self, exit_code: int = 0, phase: str = "before_target", name: str = "test-attacker") -> None:
        self.exit_code = exit_code
        self.prepare_calls = 0
        self.run_calls: list[AttackerContext] = []
        self.stop_calls = 0
        self.remove_calls = 0
        self.spec = AttackerSpec(name=name, phase=phase, instruction="/task/attack.md", cmd="python3")
        self.spec.feedback_loop = name.startswith("graph-rl")
        self.health_checks: list[bool] = [True]
        mounts = [
            type("M", (), {"container_path": "/workspace/.openart_input_workspace", "host_path": "/tmp/shared", "read_only": True})(),
            type("M", (), {"container_path": "/workspace", "host_path": "/tmp/output", "read_only": False})(),
            type("M", (), {"container_path": "/workspace/.openart_feedback", "host_path": "/tmp/run", "read_only": True})(),
            type("M", (), {"container_path": "/workspace/.openart_target_control_input", "host_path": "/tmp/control/base", "read_only": True})(),
            type("M", (), {"container_path": "/workspace/.openart_target_control_output", "host_path": "/tmp/control/output", "read_only": False})(),
        ]
        self.container = type(
            "C",
            (),
            {
                "spec": type("S", (), {"mounts": mounts})(),
                "is_healthy": lambda inner_self: self.health_checks.pop(0) if self.health_checks else True,
            },
        )()

    def prepare(self) -> None:
        self.prepare_calls += 1

    def run(self, context: AttackerContext) -> AttackerResult:
        self.run_calls.append(context)
        return AttackerResult(
            run_id=context.run_id,
            attacker_name=self.spec.name,
            phase=self.spec.phase,
            exit_code=self.exit_code,
            output_workspace_dir=context.output_workspace_dir,
        )

    def stop(self) -> None:
        self.stop_calls += 1

    def remove(self, force: bool = True) -> None:
        assert force is True
        self.remove_calls += 1


class _SequenceAttacker(_FakeAttacker):
    def __init__(self, exit_codes: list[int], phase: str = "before_target", name: str = "test-attacker") -> None:
        super().__init__(exit_code=0, phase=phase, name=name)
        self.exit_codes = list(exit_codes)

    def run(self, context: AttackerContext) -> AttackerResult:
        self.run_calls.append(context)
        exit_code = self.exit_codes.pop(0) if self.exit_codes else 0
        return AttackerResult(
            run_id=context.run_id,
            attacker_name=self.spec.name,
            phase=self.spec.phase,
            exit_code=exit_code,
            output_workspace_dir=context.output_workspace_dir,
        )


class _FakeEvaluator:
    def __init__(self) -> None:
        self.calls = 0

    def evaluate(self, **kwargs) -> EvaluatorResult:
        self.calls += 1
        return EvaluatorResult(run_id=str(kwargs["run_id"]), decision="pass", score=1.0)


class _FailingEvaluator:
    def __init__(self) -> None:
        self.calls = 0

    def evaluate(self, **kwargs) -> EvaluatorResult:
        self.calls += 1
        return EvaluatorResult(
            run_id=str(kwargs["run_id"]),
            decision="fail",
            score=0.5,
            rationale="deterministic partial result",
            metadata={
                "results": {
                    "deterministic": {"decision": "pass", "rationale": "predicate matched"},
                    "llm_judge": {"decision": "fail", "rationale": "semantic blocker"},
                }
            },
        )


class _FakeTaskContainer:
    def __init__(self) -> None:
        self.stopped = 0
        self.removed = 0
        mounts = [type("M", (), {"container_path": "/workspace", "host_path": "/tmp/shared", "read_only": False})()]
        self.spec = type("S", (), {"mounts": mounts})()

    def build(self) -> None:
        return

    def create(self) -> None:
        return

    def start(self) -> None:
        return

    def prepare_task_env(self) -> None:
        return

    def snapshot(self) -> dict[str, str]:
        return {"workspace.txt": "size=1,mtime=1"}

    def exec(self, cmd, env=None):
        return 0, "", ""

    def stop(self) -> None:
        self.stopped += 1

    def remove(self, force: bool = True) -> None:
        assert force is True
        self.removed += 1


class _FakeWorkspaceManager:
    def __init__(self, shared_root: Path | None = None, output_root: Path | None = None, live_root: Path | None = None) -> None:
        self.calls: list[tuple] = []
        self._shared_root = shared_root or Path("/tmp/shared")
        self._output_root = output_root or Path("/tmp/output")
        self._live_root = live_root or Path("/tmp/output-live")

    def snapshot_shared(self, run_id: str, tag: str):
        self.calls.append(("snapshot", run_id, tag))
        return {}

    def copy_shared_to_attacker_output(self, run_id: str, attacker_name: str, phase: str, index: int = 1, visibility_policy=None):
        self.calls.append(("copy", run_id, attacker_name, phase, index, visibility_policy is not None))
        return "/tmp/output"

    def copy_shared_to_attacker_live_output(self, run_id: str, attacker_name: str, phase: str, visibility_policy=None):
        self.calls.append(("copy_live", run_id, attacker_name, phase, visibility_policy is not None))
        return "/tmp/output-live"

    def archive_attacker_live_output(self, run_id: str, attacker_name: str, phase: str, index: int = 1):
        self.calls.append(("archive_live", run_id, attacker_name, phase, index))
        return "/tmp/output"

    def replace_shared_with_attacker_output(self, run_id: str, attacker_name: str, phase: str, index: int = 1, visibility_policy=None):
        self.calls.append(("replace", run_id, attacker_name, phase, index))
        return WorkspaceDiff(added=["attack.txt"], modified=[], deleted=[])

    def apply_attacker_output_to_shared(
        self,
        run_id: str,
        attacker_name: str,
        phase: str,
        index: int = 1,
        allow_workspace_files: bool = True,
        visibility_policy=None,
    ):
        self.calls.append(("apply", run_id, attacker_name, phase, index, allow_workspace_files, visibility_policy is not None))
        if not allow_workspace_files:
            return WorkspaceDiff(added=[], modified=[], deleted=[]), ["attack.txt"]
        return WorkspaceDiff(added=["attack.txt"], modified=[], deleted=[]), []

    def attacker_output_dir(self, run_id: str, attacker_name: str, phase: str, index: int = 1):
        return self._output_root

    def attacker_live_dir(self, run_id: str, attacker_name: str, phase: str):
        return self._live_root

    def attacker_internal_dir(self, run_id: str, attacker_name: str, phase: str, internal_dir_name: str, index: int = 1):
        _ = (run_id, attacker_name, phase, index)
        return self._output_root / internal_dir_name

    def attacker_live_internal_dir(self, run_id: str, attacker_name: str, phase: str, internal_dir_name: str):
        _ = (run_id, attacker_name, phase)
        return self._live_root / internal_dir_name

    def sync_attacker_internal_dir_from(
        self,
        run_id: str,
        attacker_name: str,
        phase: str,
        internal_dir_name: str,
        source_dir,
        index: int = 1,
        visibility_policy=None,
    ):
        self.calls.append(("sync_internal", run_id, attacker_name, phase, internal_dir_name, str(source_dir), index, visibility_policy is not None))
        return str(self._output_root / internal_dir_name)

    def sync_attacker_live_internal_dir_from(
        self,
        run_id: str,
        attacker_name: str,
        phase: str,
        internal_dir_name: str,
        source_dir,
        visibility_policy=None,
    ):
        self.calls.append(("sync_live_internal", run_id, attacker_name, phase, internal_dir_name, str(source_dir), visibility_policy is not None))
        return str(self._live_root / internal_dir_name)

    def shared_dir(self, run_id: str):
        _ = run_id
        return self._shared_root


class _FakeControlManager:
    def __init__(self, enabled: bool = True) -> None:
        self._enabled = enabled
        self.calls: list[tuple] = []
        self.provider = type("P", (), {"framework": "opencode"})() if enabled else None
        self.final_entries: list[tuple[Path, str]] = []

    def enabled(self) -> bool:
        return self._enabled

    def build_base(self):
        self.calls.append(("build_base",))
        return []

    def use_base_as_final(self):
        self.calls.append(("use_base_as_final",))
        return WorkspaceDiff(added=["AGENTS.md"], modified=[], deleted=[])

    def materialize_final_to_workspace(self, workspace_dir: str):
        self.calls.append(("materialize", workspace_dir))
        return WorkspaceDiff(added=["AGENTS.md"], modified=[], deleted=[])

    def copy_base_to_attacker_output(self, attacker_name: str, phase: str, index: int = 1):
        self.calls.append(("copy_base", attacker_name, phase, index))
        return "/tmp/control-output"

    def ensure_attacker_output(self, attacker_name: str, phase: str, index: int = 1):
        self.calls.append(("ensure_attacker_output", attacker_name, phase, index))
        return "/tmp/control-output"

    def finalize_from_attacker_output(self, attacker_name: str, phase: str, index: int = 1, allowed_vectors=None, visibility_policy=None):
        self.calls.append(("finalize", attacker_name, phase, index, tuple(allowed_vectors or ()), visibility_policy is not None))
        return WorkspaceDiff(added=["AGENTS.md"], modified=[], deleted=[]), []

    def attacker_output_dir(self, attacker_name: str, phase: str, index: int = 1):
        self.calls.append(("attacker_output_dir", attacker_name, phase, index))
        return Path("/tmp/control-output")

    def base_dir(self):
        return Path("/tmp/control/base")

    def final_dir(self):
        return Path("/tmp/control/final")

    def final_allowed_file_entries(self):
        self.calls.append(("final_allowed_file_entries",))
        return list(self.final_entries)


class _FakeTraceSink:
    def __init__(self) -> None:
        self.flush_calls = 0

    def flush(self) -> None:
        self.flush_calls += 1


class _SetupFailsOrchestrator:
    def __init__(self) -> None:
        self.teardown_calls = 0

    def setup(self) -> None:
        raise RuntimeError("setup failed")

    def teardown(self) -> None:
        self.teardown_calls += 1


def _make_orchestrator(tmp_path: Path, attacker=None) -> Orchestrator:
    return Orchestrator(
        target_runner=_FakeRunner(exit_code=0),
        attacker=attacker,
        attacker_context=(
            AttackerContext(
                run_id="run-1",
                attacker_name=attacker.spec.name,
                phase=attacker.spec.phase,
                task_dir="/task",
                target_instruction_file="/task/target.md",
                attacker_instruction_file="/task/attack.md",
                shared_workspace_dir="/workspace/.openart_input_workspace",
                input_workspace_dir="/workspace/.openart_input_workspace",
                output_workspace_dir="/workspace",
                input_target_control_dir="/workspace/.openart_target_control_input",
                output_target_control_dir="/workspace/.openart_target_control_output",
                feedback_dir="/workspace/.openart_feedback",
                trace_file="/workspace/.openart_feedback/trace.jsonl",
                evaluator_inputs_dir="/workspace/.openart_feedback/evaluator_inputs",
                evaluator_outputs_dir="/workspace/.openart_feedback/evaluator_outputs",
                target_runner_outputs_dir="/workspace/.openart_feedback/runner_outputs/target",
                evaluation_iterations_dir="/workspace/.openart_feedback/evaluation_iterations",
                attacker_history_dir=f"/workspace/.openart_feedback/attacker_outputs/{attacker.spec.name}",
            )
            if attacker is not None
            else None
        ),
        evaluator=_FakeEvaluator(),
        task_container=_FakeTaskContainer(),
        workspace_manager=_FakeWorkspaceManager(),
        control_manager=_FakeControlManager(enabled=True),
        max_iterations=1,
        adaptive_iterations=False,
        trace_sink=_FakeTraceSink(),
        trace_file=str(tmp_path / "trace.jsonl"),
    )


def _write_target_stdout(tmp_path: Path, text: str) -> None:
    output_dir = tmp_path / "runner_outputs" / "target"
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "stdout.txt").write_text(text, encoding="utf-8")


def _write_attacker_result(tmp_path: Path, attacker: _FakeAttacker, *, added: list[str] | None = None, modified: list[str] | None = None) -> None:
    result_path = tmp_path / "attacker_outputs" / attacker.spec.name / "result.json"
    result_path.parent.mkdir(parents=True, exist_ok=True)
    result_path.write_text(
        json.dumps(
            {
                "metadata": {
                    "workspace_diff": {
                        "added": added or [],
                        "modified": modified or [],
                    }
                }
            }
        ),
        encoding="utf-8",
    )


def _partial_semantic_fail_result() -> EvaluatorResult:
    return EvaluatorResult(
        run_id="run-1",
        decision="fail",
        score=0.5,
        rationale="partial success",
        metadata={
            "results": {
                "deterministic": {"decision": "pass", "score": 1.0, "rationale": "found expected final artifact"},
                "llm_judge": {"decision": "fail", "score": 0.0, "rationale": "target did not visibly perform the action"},
            }
        },
    )


def test_target_action_evidence_classifies_deterministic_pass_llm_fail_as_trace_gap(tmp_path: Path) -> None:
    attacker = _FakeAttacker()
    orchestrator = _make_orchestrator(tmp_path, attacker=attacker)
    _write_attacker_result(tmp_path, attacker, added=["supporting_note.txt"])
    _write_target_stdout(tmp_path, "Read supporting_note.txt\nWrote file status.txt\nVerified status.txt was saved.\n")

    guidance = orchestrator._build_attacker_feedback_guidance(1, _partial_semantic_fail_result(), {})

    assert guidance["category"] == "trace_evidence_gap"
    evidence = guidance["target_action_evidence"]
    assert evidence["status"] == "trace_evidence_gap"
    assert "target_performed_scored_action" not in evidence["missing_evidence"]
    assert any(item["type"] == "target_read_attack_file" for item in evidence["observed_evidence"])
    assert any(item["type"] == "file_write_or_edit" for item in evidence["observed_evidence"])
    assert any(item["type"] == "verification_language" for item in evidence["observed_evidence"])


def test_target_action_evidence_records_refusal_and_action_together(tmp_path: Path) -> None:
    attacker = _FakeAttacker()
    orchestrator = _make_orchestrator(tmp_path, attacker=attacker)
    _write_attacker_result(tmp_path, attacker, added=["supporting_note.txt"])
    _write_target_stdout(tmp_path, "Read supporting_note.txt\nWrote file status.txt\nI cannot do that because it conflicts with safety policy.\n")

    result = EvaluatorResult(
        run_id="run-1",
        decision="fail",
        score=0.0,
        metadata={
            "results": {
                "deterministic": {"decision": "fail", "rationale": "missing final condition"},
                "llm_judge": {"decision": "fail", "rationale": "refusal and safety warning"},
            }
        },
    )
    guidance = orchestrator._build_attacker_feedback_guidance(1, result, {})
    evidence = guidance["target_action_evidence"]

    assert evidence["status"] == "blocked_or_refused"
    assert any(item["type"] == "file_write_or_edit" for item in evidence["observed_evidence"])
    assert {item["type"] for item in evidence["blockers"]} >= {"refusal", "safety_warning"}
    assert "target_completed_without_refusal_or_redaction" in evidence["missing_evidence"]


def test_target_action_evidence_reports_final_artifact_only_gap(tmp_path: Path) -> None:
    attacker = _FakeAttacker()
    orchestrator = _make_orchestrator(tmp_path, attacker=attacker)
    _write_attacker_result(tmp_path, attacker, added=["final_output.txt"])
    _write_target_stdout(tmp_path, "The answer is available in final_output.txt.\n")

    guidance = orchestrator._build_attacker_feedback_guidance(1, _partial_semantic_fail_result(), {})
    evidence = guidance["target_action_evidence"]

    assert evidence["status"] == "trace_evidence_gap"
    assert "target_performed_scored_action" in evidence["missing_evidence"]
    assert "target_read_relevant_context" in evidence["missing_evidence"]
    assert "pre-created final artifacts alone" in evidence["repair_instruction"]


def test_adaptive_retry_stops_on_refusal_for_non_graph_rl(tmp_path: Path) -> None:
    orchestrator = _make_orchestrator(tmp_path, attacker=_FakeAttacker())
    orchestrator.adaptive_iterations = True
    result = EvaluatorResult(run_id="run-1", decision="fail", score=0.5)
    guidance = {"deterministic_decision": "fail", "rationale": "The agent refused the unsafe request."}

    assert orchestrator._should_retry_iteration(result, guidance) is False


def test_graph_rl_adaptive_retry_continues_after_refusal_or_deterministic_partial(tmp_path: Path) -> None:
    orchestrator = _make_orchestrator(tmp_path, attacker=_FakeAttacker(name="graph-rl-control-attacker"))
    orchestrator.adaptive_iterations = True
    result = EvaluatorResult(run_id="run-1", decision="fail", score=0.5)

    refusal_guidance = {"deterministic_decision": "fail", "rationale": "The agent refused the unsafe request."}
    partial_guidance = {"deterministic_decision": "pass", "llm_judge_decision": "fail", "rationale": "deterministic only"}

    assert orchestrator._should_retry_iteration(result, refusal_guidance) is True
    assert orchestrator._should_retry_iteration(result, partial_guidance) is True


def test_adaptive_attacker_failure_keeps_previous_evaluator_result(tmp_path: Path) -> None:
    attacker = _SequenceAttacker([0, 2], name="graph-rl-control-attacker")
    orchestrator = _make_orchestrator(tmp_path, attacker=attacker)
    orchestrator.evaluator = _FailingEvaluator()
    orchestrator.adaptive_iterations = True
    orchestrator.max_iterations = 2

    result = orchestrator.run("run-1", "/task/target.md", "/task/attack.md")

    assert result.decision == "fail"
    assert result.score == 0.5
    assert result.metadata["adaptive_retry_exhausted"]["exit_code"] == 2
    assert "runtime_error" not in result.decision
    marker = tmp_path / "attacker_outputs" / "graph-rl-control-attacker" / "adaptive_retry_exhausted.json"
    assert marker.is_file()
    payload = json.loads(marker.read_text(encoding="utf-8"))
    assert payload["kept_result"]["decision"] == "fail"
    assert payload["attack_iteration"] == 2


def test_rejected_skill_validation_appears_in_next_iteration_feedback(tmp_path: Path) -> None:
    attacker = _FakeAttacker()
    orchestrator = _make_orchestrator(tmp_path, attacker=attacker)
    orchestrator.workspace_manager = _FakeWorkspaceManager(live_root=tmp_path / "live")
    validation_payload = {
        "validated": [],
        "rejected": [
            {
                "skill_dir": ".opencode/skills/bad-tool",
                "skill_file": ".opencode/skills/bad-tool/SKILL.md",
                "vector": "opencode_skill",
                "files": [".opencode/skills/bad-tool/SKILL.md"],
                "reasons": ["missing activation cue in SKILL.md or companion instruction file"],
                "suggested_fix": "Add a clear activation cue.",
            }
        ],
    }
    validation_path = tmp_path / "control" / "target" / "snapshots" / "skill_validation.json"
    validation_path.parent.mkdir(parents=True)
    validation_path.write_text(json.dumps(validation_payload), encoding="utf-8")

    guidance = orchestrator._build_attacker_feedback_guidance(
        1,
        EvaluatorResult(run_id="run-1", decision="fail", score=0.4),
        {"gitlab": {"healthy": True}},
    )
    orchestrator._write_attacker_feedback_guidance(guidance, 1)
    orchestrator._sync_attacker_feedback("run-1", attacker.spec.name, attacker.spec.phase)

    assert guidance["skill_validation"]["rejected"][0]["skill_dir"] == ".opencode/skills/bad-tool"
    copied = tmp_path / "live" / ".openart_feedback" / "skill_validation.json"
    assert copied.is_file()
    assert json.loads(copied.read_text(encoding="utf-8"))["rejected"][0]["suggested_fix"]


def test_launch_once_tears_down_after_setup_failure() -> None:
    orchestrator = _SetupFailsOrchestrator()

    with pytest.raises(RuntimeError, match="setup failed"):
        launch_once(
            orchestrator,
            run_id="run-1",
            target_instruction_file="/task/target.md",
            attack_instruction_file=None,
        )

    assert orchestrator.teardown_calls == 1


def test_orchestrator_returns_target_failure_and_skips_evaluation(tmp_path: Path) -> None:
    trace_sink = _FakeTraceSink()
    evaluator = _FakeEvaluator()
    orchestrator = Orchestrator(
        target_runner=_FakeRunner(exit_code=23),
        attacker=None,
        attacker_context=None,
        evaluator=evaluator,
        task_container=_FakeTaskContainer(),
        workspace_manager=_FakeWorkspaceManager(),
        control_manager=_FakeControlManager(enabled=True),
        max_iterations=1,
        adaptive_iterations=False,
        trace_sink=trace_sink,
        trace_file=str(tmp_path / "trace.jsonl"),
    )

    result = orchestrator.run(
        run_id="run-1",
        target_instruction_file="/task/target.md",
        attack_instruction_file=None,
    )

    assert result.decision == "runtime_error"
    assert result.metadata["runner_failure"]["role"] == "target"
    assert result.metadata["runner_failure"]["exit_code"] == 23
    assert evaluator.calls == 0
    assert trace_sink.flush_calls == 1


def test_orchestrator_runs_before_target_attacker_first(tmp_path: Path) -> None:
    attacker = _FakeAttacker(exit_code=0, phase="before_target")
    orchestrator = _make_orchestrator(tmp_path, attacker=attacker)

    result = orchestrator.run(
        run_id="run-1",
        target_instruction_file="/task/target.md",
        attack_instruction_file="/task/attack.md",
    )

    assert result.decision == "pass"
    assert len(attacker.run_calls) == 1
    assert orchestrator.target_runner.prepare_calls == 1
    assert orchestrator.target_runner.run_calls == [("run-1", "/task/target.md", 1)]
    assert [call[0] for call in orchestrator.workspace_manager.calls] == [
        "snapshot",
        "copy_live",
        "sync_live_internal",
        "sync_live_internal",
        "sync_live_internal",
        "archive_live",
        "apply",
        "snapshot",
    ]
    assert [call[0] for call in orchestrator.control_manager.calls] == [
        "build_base",
        "attacker_output_dir",
        "finalize",
        "materialize",
        "final_allowed_file_entries",
    ]
    timing = json.loads((tmp_path / "timing.json").read_text(encoding="utf-8"))
    names = {event["name"] for event in timing["events"]}
    assert {
        "attack.copy_shared_to_output",
        "attack.sync_input_workspace",
        "attack.sync_feedback",
        "attack.apply_workspace_diff",
        "control.finalize_from_attacker_output",
        "control.materialize_final_to_workspace",
    }.issubset(names)


def test_orchestrator_archives_live_workspace_when_attacker_fails(tmp_path: Path) -> None:
    attacker = _FakeAttacker(exit_code=7, phase="before_target")
    orchestrator = _make_orchestrator(tmp_path, attacker=attacker)

    result = orchestrator.run(
        run_id="run-1",
        target_instruction_file="/task/target.md",
        attack_instruction_file="/task/attack.md",
    )

    assert result.decision == "runtime_error"
    assert ("archive_live", "run-1", "test-attacker", "before_target", 1) in orchestrator.workspace_manager.calls
    artifact = json.loads((tmp_path / "attacker_outputs" / "test-attacker" / "result.json").read_text(encoding="utf-8"))
    assert artifact["metadata"]["host_live_output_workspace_dir"] == "/tmp/output-live"
    assert artifact["metadata"]["host_output_workspace_dir"] == "/tmp/output"
    assert orchestrator.target_runner.run_calls == []


def test_orchestrator_syncs_target_control_from_matching_archived_workspace(tmp_path: Path) -> None:
    provider = ControlPlaneProvider(
        framework="test",
        source_patterns=("AGENTS.md",),
        allowed_patterns=("AGENTS.md",),
        attacker_allowed_patterns=("AGENTS.md",),
        attacker_vector_patterns={"agents_md": ("AGENTS.md",)},
        default_attacker_vectors=("agents_md",),
        attacker_surfaces=(
            ControlSurfaceSpec(
                kind="instruction",
                vector="agents_md",
                path_template="AGENTS.md",
                description="Agent instruction file.",
            ),
        ),
    )
    workspace_manager = WorkspaceManager(str(tmp_path / "workspace"))
    workspace_manager.ensure_run_layout("run-1")
    control_manager = ControlPlaneManager(
        root_dir=str(tmp_path / "control" / "target"),
        source_root=str(workspace_manager.shared_dir("run-1")),
        provider=provider,
    )
    control_manager.ensure_layout()
    archived = workspace_manager.attacker_output_dir("run-1", "test-attacker", "before_target", 2)
    control_output = archived / ".openart_target_control_output"
    control_output.mkdir(parents=True, exist_ok=True)
    (control_output / "AGENTS.md").write_text("iteration two control\n", encoding="utf-8")

    orchestrator = Orchestrator(
        target_runner=_FakeRunner(exit_code=0),
        attacker=None,
        attacker_context=None,
        evaluator=_FakeEvaluator(),
        task_container=_FakeTaskContainer(),
        workspace_manager=workspace_manager,
        control_manager=control_manager,
        max_iterations=1,
        adaptive_iterations=False,
        trace_sink=_FakeTraceSink(),
        trace_file=str(tmp_path / "trace.jsonl"),
    )

    orchestrator._sync_control_from_container("test-attacker", "before_target", 2, "run-1")

    assert not (control_manager.attacker_output_dir("test-attacker", "before_target", 1) / "AGENTS.md").exists()
    assert (
        control_manager.attacker_output_dir("test-attacker", "before_target", 2) / "AGENTS.md"
    ).read_text(encoding="utf-8") == "iteration two control\n"


def test_orchestrator_target_visible_leak_guard_warns_and_continues(tmp_path: Path) -> None:
    shared_root = tmp_path / "shared"
    leak = shared_root / "_custom_attacker_scratch" / "proposal_prompt.txt"
    leak.parent.mkdir(parents=True, exist_ok=True)
    leak.write_text("internal prompt\n", encoding="utf-8")
    attacker = _FakeAttacker(exit_code=0, phase="before_target")
    attacker.spec.visibility_policy = {
        "target_visible_leak": {
            "path_markers": ["_custom_attacker_scratch"],
        },
    }
    target_runner = _FakeRunner(exit_code=0)
    evaluator = _FakeEvaluator()
    orchestrator = Orchestrator(
        target_runner=target_runner,
        attacker=attacker,
        attacker_context=None,
        evaluator=evaluator,
        task_container=_FakeTaskContainer(),
        workspace_manager=_FakeWorkspaceManager(shared_root=shared_root),
        control_manager=_FakeControlManager(enabled=True),
        max_iterations=1,
        adaptive_iterations=False,
        trace_sink=_FakeTraceSink(),
        trace_file=str(tmp_path / "trace.jsonl"),
    )

    result = orchestrator.run(
        run_id="run-1",
        target_instruction_file="/task/target.md",
        attack_instruction_file=None,
    )

    assert result.decision == "pass"
    assert target_runner.run_calls == [("run-1", "/task/target.md", 1)]
    assert evaluator.calls == 1
    guard = json.loads((tmp_path / "target_visible_leak_guard.json").read_text(encoding="utf-8"))
    assert guard["status"] == "warning"
    assert guard["rejected"] is False
    assert guard["findings"][0]["path"] == "_custom_attacker_scratch/proposal_prompt.txt"


def test_orchestrator_leak_guard_ignores_framework_dot_openart_runtime(tmp_path: Path) -> None:
    shared_root = tmp_path / "shared"
    evaluator_dir = shared_root / ".openart" / "evaluator"
    evaluator_dir.mkdir(parents=True, exist_ok=True)
    (evaluator_dir / "bridge.py").write_text("trace_file = 'trace.jsonl'\n", encoding="utf-8")
    (shared_root / ".openart" / "evaluator_trace.jsonl").write_text("{}\n", encoding="utf-8")
    target_runner = _FakeRunner(exit_code=0)
    evaluator = _FakeEvaluator()
    orchestrator = Orchestrator(
        target_runner=target_runner,
        attacker=None,
        attacker_context=None,
        evaluator=evaluator,
        task_container=_FakeTaskContainer(),
        workspace_manager=_FakeWorkspaceManager(shared_root=shared_root),
        control_manager=_FakeControlManager(enabled=True),
        max_iterations=1,
        adaptive_iterations=False,
        trace_sink=_FakeTraceSink(),
        trace_file=str(tmp_path / "trace.jsonl"),
    )

    result = orchestrator.run(
        run_id="run-1",
        target_instruction_file="/task/target.md",
        attack_instruction_file=None,
    )

    assert result.decision == "pass"
    assert target_runner.run_calls == [("run-1", "/task/target.md", 1)]
    assert evaluator.calls == 1


def test_orchestrator_materializes_control_plane_to_workspace_without_target_bind_mounts(tmp_path: Path) -> None:
    shared_root = tmp_path / "shared"
    shared_root.mkdir(parents=True, exist_ok=True)
    control_file = tmp_path / "control" / "target" / "final" / "CLAUDE.md"
    control_file.parent.mkdir(parents=True, exist_ok=True)
    control_file.write_text("Use the migration workflow.\n", encoding="utf-8")

    class _MaterializingControlManager(_FakeControlManager):
        def materialize_final_to_workspace(self, workspace_dir: str):
            diff = super().materialize_final_to_workspace(workspace_dir)
            root = Path(workspace_dir)
            for host_path, relative_path in self.final_entries:
                dest = root / relative_path
                dest.parent.mkdir(parents=True, exist_ok=True)
                dest.write_text(Path(host_path).read_text(encoding="utf-8"), encoding="utf-8")
            return diff

    control_manager = _MaterializingControlManager(enabled=True)
    control_manager.final_entries = [(control_file, "CLAUDE.md")]
    workspace_manager = _FakeWorkspaceManager(shared_root=shared_root)
    target_runner = _FakeRunner(exit_code=0)

    orchestrator = Orchestrator(
        target_runner=target_runner,
        attacker=None,
        attacker_context=None,
        evaluator=_FakeEvaluator(),
        task_container=_FakeTaskContainer(),
        workspace_manager=workspace_manager,
        control_manager=control_manager,
        max_iterations=1,
        adaptive_iterations=False,
        trace_sink=_FakeTraceSink(),
        trace_file=str(tmp_path / "trace.jsonl"),
    )

    result = orchestrator.run(
        run_id="run-1",
        target_instruction_file="/task/target.md",
        attack_instruction_file=None,
    )

    assert result.decision == "pass"
    assert ("materialize", str(shared_root)) in control_manager.calls
    assert (shared_root / "CLAUDE.md").read_text(encoding="utf-8") == "Use the migration workflow.\n"
    mounts = {(mount.container_path, mount.host_path, mount.read_only) for mount in target_runner.container.spec.mounts}
    assert ("/workspace/CLAUDE.md", str(control_file), True) not in mounts


def test_orchestrator_skips_workspace_replacement_when_workspace_vector_disabled(tmp_path: Path) -> None:
    attacker = _FakeAttacker(exit_code=0, phase="before_target")
    attacker.spec.vector_permissions = ["claude_md"]
    orchestrator = _make_orchestrator(tmp_path, attacker=attacker)

    result = orchestrator.run(
        run_id="run-1",
        target_instruction_file="/task/target.md",
        attack_instruction_file="/task/attack.md",
    )

    assert result.decision == "pass"
    apply_call = next(call for call in orchestrator.workspace_manager.calls if call[0] == "apply")
    assert apply_call[5] is False


def test_orchestrator_reruns_feedback_attacker_between_target_iterations(tmp_path: Path) -> None:
    class _TwoStepEvaluator:
        def __init__(self):
            self.calls = 0

        def evaluate(self, **kwargs) -> EvaluatorResult:
            self.calls += 1
            if self.calls == 1:
                return EvaluatorResult(run_id=str(kwargs["run_id"]), decision="fail", score=0.0)
            return EvaluatorResult(run_id=str(kwargs["run_id"]), decision="pass", score=1.0)

    attacker = _FakeAttacker(exit_code=0, phase="before_target")
    attacker.spec.feedback_loop = True
    orchestrator = Orchestrator(
        target_runner=_FakeRunner(exit_code=0),
        attacker=attacker,
        attacker_context=_make_orchestrator(tmp_path, attacker=attacker).attacker_context,
        evaluator=_TwoStepEvaluator(),
        task_container=_FakeTaskContainer(),
        workspace_manager=_FakeWorkspaceManager(),
        control_manager=_FakeControlManager(enabled=True),
        max_iterations=2,
        adaptive_iterations=False,
        trace_sink=_FakeTraceSink(),
        trace_file=str(tmp_path / "trace.jsonl"),
    )

    result = orchestrator.run(
        run_id="run-1",
        target_instruction_file="/task/target.md",
        attack_instruction_file="/task/attack.md",
    )

    assert result.decision == "pass"
    assert len(attacker.run_calls) == 2


def test_orchestrator_stops_after_successful_deterministic_result(tmp_path: Path) -> None:
    class _DeterministicPassEvaluator:
        def __init__(self):
            self.calls = 0

        def evaluate(self, **kwargs) -> EvaluatorResult:
            self.calls += 1
            return EvaluatorResult(
                run_id=str(kwargs["run_id"]),
                decision="unknown",
                score=0.5,
                metadata={
                    "evaluator": "composite",
                    "results": {
                        "deterministic": {"decision": "pass", "score": 1.0},
                        "llm_judge": {"decision": "unknown", "score": 0.0},
                    },
                },
            )

    attacker = _FakeAttacker(exit_code=0, phase="before_target")
    attacker.spec.feedback_loop = True
    orchestrator = Orchestrator(
        target_runner=_FakeRunner(exit_code=0),
        attacker=attacker,
        attacker_context=_make_orchestrator(tmp_path, attacker=attacker).attacker_context,
        evaluator=_DeterministicPassEvaluator(),
        task_container=_FakeTaskContainer(),
        workspace_manager=_FakeWorkspaceManager(),
        control_manager=_FakeControlManager(enabled=True),
        max_iterations=5,
        adaptive_iterations=False,
        trace_sink=_FakeTraceSink(),
        trace_file=str(tmp_path / "trace.jsonl"),
    )

    result = orchestrator.run(
        run_id="run-1",
        target_instruction_file="/task/target.md",
        attack_instruction_file="/task/attack.md",
    )

    assert result.decision == "fail"
    assert orchestrator.target_runner.run_calls == [("run-1", "/task/target.md", 1)]
    assert len(attacker.run_calls) == 1


def test_orchestrator_reprepares_attacker_when_container_stops_before_feedback_iteration(tmp_path: Path) -> None:
    class _TwoStepEvaluator:
        def __init__(self):
            self.calls = 0

        def evaluate(self, **kwargs) -> EvaluatorResult:
            self.calls += 1
            if self.calls == 1:
                return EvaluatorResult(run_id=str(kwargs["run_id"]), decision="fail", score=0.0)
            return EvaluatorResult(run_id=str(kwargs["run_id"]), decision="pass", score=1.0)

    attacker = _FakeAttacker(exit_code=0, phase="before_target")
    attacker.spec.feedback_loop = True
    attacker.health_checks = [False]
    orchestrator = Orchestrator(
        target_runner=_FakeRunner(exit_code=0),
        attacker=attacker,
        attacker_context=_make_orchestrator(tmp_path, attacker=attacker).attacker_context,
        evaluator=_TwoStepEvaluator(),
        task_container=_FakeTaskContainer(),
        workspace_manager=_FakeWorkspaceManager(),
        control_manager=_FakeControlManager(enabled=True),
        max_iterations=2,
        adaptive_iterations=False,
        trace_sink=_FakeTraceSink(),
        trace_file=str(tmp_path / "trace.jsonl"),
    )

    result = orchestrator.run(
        run_id="run-1",
        target_instruction_file="/task/target.md",
        attack_instruction_file="/task/attack.md",
    )

    assert result.decision == "pass"
    assert attacker.prepare_calls == 2
    assert attacker.remove_calls == 1
    assert len(attacker.run_calls) == 2


def test_orchestrator_skips_attacker_without_instruction(tmp_path: Path) -> None:
    attacker = _FakeAttacker(exit_code=0, phase="before_target")
    orchestrator = _make_orchestrator(tmp_path, attacker=attacker)

    result = orchestrator.run(
        run_id="run-1",
        target_instruction_file="/task/target.md",
        attack_instruction_file=None,
    )

    assert result.decision == "pass"
    assert attacker.run_calls == []


def test_orchestrator_stops_early_on_second_iteration_pass(tmp_path: Path) -> None:
    class _TwoStepEvaluator:
        def __init__(self):
            self.calls = 0

        def evaluate(self, **kwargs) -> EvaluatorResult:
            self.calls += 1
            if self.calls == 1:
                return EvaluatorResult(run_id=str(kwargs["run_id"]), decision="fail", score=0.0)
            return EvaluatorResult(run_id=str(kwargs["run_id"]), decision="pass", score=1.0)

    orchestrator = Orchestrator(
        target_runner=_FakeRunner(exit_code=0),
        attacker=None,
        attacker_context=None,
        evaluator=_TwoStepEvaluator(),
        task_container=_FakeTaskContainer(),
        workspace_manager=_FakeWorkspaceManager(),
        control_manager=_FakeControlManager(enabled=True),
        max_iterations=2,
        adaptive_iterations=False,
        trace_sink=_FakeTraceSink(),
        trace_file=str(tmp_path / "trace.jsonl"),
    )

    result = orchestrator.run(
        run_id="run-1",
        target_instruction_file="/task/target.md",
        attack_instruction_file=None,
    )

    assert result.decision == "pass"
    assert orchestrator.target_runner.run_calls == [
        ("run-1", "/task/target.md", 1),
        ("run-1", "/task/target.md", 2),
    ]


def test_orchestrator_adaptive_iterations_stops_on_refusal(tmp_path: Path) -> None:
    class _RefusalEvaluator:
        def __init__(self):
            self.calls = 0

        def evaluate(self, **kwargs) -> EvaluatorResult:
            self.calls += 1
            return EvaluatorResult(
                run_id=str(kwargs["run_id"]),
                decision="fail",
                score=0.0,
                rationale="The agent explicitly refused and said I can't help.",
            )

    orchestrator = Orchestrator(
        target_runner=_FakeRunner(exit_code=0),
        attacker=None,
        attacker_context=None,
        evaluator=_RefusalEvaluator(),
        task_container=_FakeTaskContainer(),
        workspace_manager=_FakeWorkspaceManager(),
        control_manager=_FakeControlManager(enabled=True),
        max_iterations=3,
        adaptive_iterations=True,
        trace_sink=_FakeTraceSink(),
        trace_file=str(tmp_path / "trace.jsonl"),
    )

    result = orchestrator.run(
        run_id="run-1",
        target_instruction_file="/task/target.md",
        attack_instruction_file=None,
    )

    assert result.decision == "fail"
    assert orchestrator.target_runner.run_calls == [("run-1", "/task/target.md", 1)]

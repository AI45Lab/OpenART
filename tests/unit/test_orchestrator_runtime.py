from __future__ import annotations

from pathlib import Path

import pytest

from framework.attackers.models import AttackerContext, AttackerResult, AttackerSpec
from framework.core.orchestrator import Orchestrator
from framework.core.runtime import launch_once
from framework.models.specs import EvaluatorResult, WorkspaceDiff


class _FakeServiceManager:
    def __init__(self, snapshots: dict[str, dict[str, str]] | None = None) -> None:
        self._snapshots = snapshots or {"gitlab": {"healthy": True}}

    def start_all(self) -> None:
        return

    def seed_all(self) -> None:
        return

    def reset_all(self) -> None:
        return

    def stop_all(self) -> None:
        return

    def snapshot_all(self) -> dict[str, dict[str, str]]:
        return self._snapshots


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
    def __init__(self, exit_code: int = 0, phase: str = "before_target") -> None:
        self.exit_code = exit_code
        self.prepare_calls = 0
        self.run_calls: list[AttackerContext] = []
        self.stop_calls = 0
        self.remove_calls = 0
        self.spec = AttackerSpec(name="test-attacker", phase=phase, instruction="/task/attack.md", cmd="python3")
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


class _FakeEvaluator:
    def __init__(self) -> None:
        self.calls = 0

    def evaluate(self, **kwargs) -> EvaluatorResult:
        self.calls += 1
        return EvaluatorResult(run_id=str(kwargs["run_id"]), decision="pass", score=1.0)


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
    def __init__(self, shared_root: Path | None = None) -> None:
        self.calls: list[tuple] = []
        self._shared_root = shared_root or Path("/tmp/shared")

    def snapshot_shared(self, run_id: str, tag: str):
        self.calls.append(("snapshot", run_id, tag))
        return {}

    def copy_shared_to_attacker_output(self, run_id: str, attacker_name: str, phase: str, index: int = 1):
        self.calls.append(("copy", run_id, attacker_name, phase, index))
        return "/tmp/output"

    def replace_shared_with_attacker_output(self, run_id: str, attacker_name: str, phase: str, index: int = 1):
        self.calls.append(("replace", run_id, attacker_name, phase, index))
        return WorkspaceDiff(added=["attack.txt"], modified=[], deleted=[])

    def apply_attacker_output_to_shared(
        self,
        run_id: str,
        attacker_name: str,
        phase: str,
        index: int = 1,
        allow_workspace_files: bool = True,
    ):
        self.calls.append(("apply", run_id, attacker_name, phase, index, allow_workspace_files))
        if not allow_workspace_files:
            return WorkspaceDiff(added=[], modified=[], deleted=[]), ["attack.txt"]
        return WorkspaceDiff(added=["attack.txt"], modified=[], deleted=[]), []

    def attacker_output_dir(self, run_id: str, attacker_name: str, phase: str, index: int = 1):
        return Path("/tmp/output")

    def attacker_internal_dir(self, run_id: str, attacker_name: str, phase: str, internal_dir_name: str, index: int = 1):
        _ = (run_id, attacker_name, phase, index)
        return Path("/tmp/output") / internal_dir_name

    def sync_attacker_internal_dir_from(
        self,
        run_id: str,
        attacker_name: str,
        phase: str,
        internal_dir_name: str,
        source_dir,
        index: int = 1,
    ):
        self.calls.append(("sync_internal", run_id, attacker_name, phase, internal_dir_name, str(source_dir), index))
        return str(Path("/tmp/output") / internal_dir_name)

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

    def finalize_from_attacker_output(self, attacker_name: str, phase: str, index: int = 1, allowed_vectors=None):
        self.calls.append(("finalize", attacker_name, phase, index, tuple(allowed_vectors or ())))
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
        service_manager=_FakeServiceManager(),
        target_runner=_FakeRunner(exit_code=0),
        attacker=attacker,
        attacker_context=(
            AttackerContext(
                run_id="run-1",
                attacker_name="test-attacker",
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
                attacker_history_dir="/workspace/.openart_feedback/attacker_outputs/test-attacker",
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
        service_manager=_FakeServiceManager(),
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
        "copy",
        "sync_internal",
        "sync_internal",
        "apply",
        "snapshot",
    ]
    assert [call[0] for call in orchestrator.control_manager.calls] == ["build_base", "copy_base", "attacker_output_dir", "finalize", "materialize"]


def test_orchestrator_can_mount_control_plane_without_materializing_workspace(tmp_path: Path) -> None:
    shared_root = tmp_path / "shared"
    shared_root.mkdir(parents=True, exist_ok=True)
    control_file = tmp_path / "control" / "target" / "final" / "CLAUDE.md"
    control_file.parent.mkdir(parents=True, exist_ok=True)
    control_file.write_text("Use the migration workflow.\n", encoding="utf-8")

    control_manager = _FakeControlManager(enabled=True)
    control_manager.final_entries = [(control_file, "CLAUDE.md")]
    workspace_manager = _FakeWorkspaceManager(shared_root=shared_root)
    target_runner = _FakeRunner(exit_code=0)

    orchestrator = Orchestrator(
        service_manager=_FakeServiceManager(),
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
        target_control_plane_mount_mode="mounted",
    )

    result = orchestrator.run(
        run_id="run-1",
        target_instruction_file="/task/target.md",
        attack_instruction_file=None,
    )

    assert result.decision == "pass"
    assert "materialize" not in [call[0] for call in control_manager.calls]
    assert (shared_root / "CLAUDE.md").exists() is False
    mounts = {(mount.container_path, mount.host_path, mount.read_only) for mount in target_runner.container.spec.mounts}
    assert ("/workspace/CLAUDE.md", str(control_file), True) in mounts


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
    assert apply_call[-1] is False


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
        service_manager=_FakeServiceManager(),
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


def test_orchestrator_stops_retry_when_service_is_unhealthy(tmp_path: Path) -> None:
    class _AlwaysFailEvaluator:
        def evaluate(self, **kwargs) -> EvaluatorResult:
            return EvaluatorResult(run_id=str(kwargs["run_id"]), decision="fail", score=0.0)

    attacker = _FakeAttacker(exit_code=0, phase="before_target")
    attacker.spec.feedback_loop = True
    orchestrator = Orchestrator(
        service_manager=_FakeServiceManager({"plane": {"healthy": False}}),
        target_runner=_FakeRunner(exit_code=0),
        attacker=attacker,
        attacker_context=_make_orchestrator(tmp_path, attacker=attacker).attacker_context,
        evaluator=_AlwaysFailEvaluator(),
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
        service_manager=_FakeServiceManager(),
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
        service_manager=_FakeServiceManager(),
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
        service_manager=_FakeServiceManager(),
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
        service_manager=_FakeServiceManager(),
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

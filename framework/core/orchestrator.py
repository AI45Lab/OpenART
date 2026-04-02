from __future__ import annotations

from pathlib import Path
from typing import Any, Optional

from framework.attackers.base import AttackerBase
from framework.attackers.models import AttackerContext, AttackerResult
from framework.components.containers import TaskContainer
from framework.components.evaluators import EvaluatorBase
from framework.components.runners import RunnerBase
from framework.components.services import ServiceManager
from framework.components.trace import TraceSinkBase
from framework.core.control_plane import ControlPlaneManager
from framework.core.helpers import capture_workspace_listing, write_json_artifact, write_text_artifact
from framework.core.workspace import WorkspaceManager
from framework.models.specs import EvaluatorResult


class Orchestrator:
    def __init__(
        self,
        service_manager: ServiceManager,
        target_runner: RunnerBase,
        attacker: Optional[AttackerBase],
        attacker_context: Optional[AttackerContext],
        evaluator: EvaluatorBase,
        task_container: TaskContainer,
        workspace_manager: WorkspaceManager,
        control_manager: ControlPlaneManager,
        trace_sink: TraceSinkBase,
        trace_file: str,
    ) -> None:
        self.service_manager = service_manager
        self.target_runner = target_runner
        self.attacker = attacker
        self.attacker_context = attacker_context
        self.evaluator = evaluator
        self.task_container = task_container
        self.workspace_manager = workspace_manager
        self.control_manager = control_manager
        self.trace_sink = trace_sink
        self.trace_file = trace_file
        self._target_prepared = False
        self._attacker_prepared = False
        self._control_prepared = False

    def setup(self) -> None:
        self.service_manager.start_all()
        self.service_manager.seed_all()
        self.task_container.build()
        self.task_container.create()
        self.task_container.start()
        self.task_container.prepare_task_env()
        self._capture_task_workspace_listing("prepared")
        self.workspace_manager.snapshot_shared(self.run_id_from_trace(), "prepared")
        self._prepare_control_plane()
        self._write_workspace_flow_metadata()

    def run(
        self,
        run_id: str,
        target_instruction_file: str,
        attack_instruction_file: str | None,
    ) -> EvaluatorResult:
        self._prepare_control_plane()
        if self._should_run_attacker("before_target", attack_instruction_file):
            attacker_result = self._run_attacker_phase(run_id, "before_target")
            if attacker_result is not None and attacker_result.exit_code != 0:
                return self._runner_failure_result(run_id, "attack", attacker_result.exit_code)
            self._materialize_control_after_attacker(run_id, "before_target", attacker_result)
        else:
            self._materialize_base_control(run_id)

        self._prepare_target_runner()
        self._capture_task_workspace_listing("before_target")
        target_exit_code = self.target_runner.run(run_id, target_instruction_file)
        self._capture_task_workspace_listing("after_target")
        if target_exit_code != 0:
            return self._runner_failure_result(run_id, "target", target_exit_code)

        if self._should_run_attacker("after_target", attack_instruction_file):
            attacker_result = self._run_attacker_phase(run_id, "after_target")
            if attacker_result is not None and attacker_result.exit_code != 0:
                return self._runner_failure_result(run_id, "attack", attacker_result.exit_code)
            self._materialize_control_after_attacker(run_id, "after_target", attacker_result)

        task_snapshot = self.task_container.snapshot()
        service_snapshots = self.service_manager.snapshot_all()
        self._write_evaluator_inputs(task_snapshot, service_snapshots)
        self.trace_sink.flush()
        return self.evaluator.evaluate(
            run_id=run_id,
            trace_file=self.trace_file,
            task_snapshot=task_snapshot,
            service_snapshots=service_snapshots,
        )

    def teardown(self) -> None:
        self.service_manager.reset_all()
        self.service_manager.stop_all()
        self.target_runner.stop()
        self.target_runner.remove(force=True)
        if self.attacker is not None:
            self.attacker.stop()
            self.attacker.remove(force=True)
        self.task_container.stop()
        self.task_container.remove(force=True)

    def run_id_from_trace(self) -> str:
        return Path(self.trace_file).resolve().parent.name

    def _should_run_attacker(self, phase: str, attack_instruction_file: str | None) -> bool:
        if self.attacker is None or self.attacker_context is None or not attack_instruction_file:
            return False
        return self.attacker.spec.phase == phase

    def _prepare_target_runner(self) -> None:
        if self._target_prepared:
            return
        self.target_runner.prepare()
        self._target_prepared = True

    def _prepare_attacker(self) -> None:
        if self.attacker is None or self._attacker_prepared:
            return
        self.attacker.prepare()
        self._attacker_prepared = True

    def _prepare_control_plane(self) -> None:
        if self._control_prepared:
            return
        self.control_manager.build_base()
        self._control_prepared = True

    def _run_attacker_phase(self, run_id: str, phase: str) -> AttackerResult | None:
        if self.attacker is None or self.attacker_context is None:
            return None

        context = self.attacker_context
        attacker_name = context.attacker_name
        self._capture_task_workspace_listing("before_attack")
        self.workspace_manager.snapshot_shared(run_id, f"pre_{phase}")
        self.workspace_manager.copy_shared_to_attacker_output(run_id, attacker_name, phase, 1)
        if context.output_target_control_dir:
            self.control_manager.copy_base_to_attacker_output(attacker_name, phase, 1)
        self._prepare_attacker()
        result = self.attacker.run(context)
        self._capture_attacker_support_artifacts(attacker_name, phase, result)
        if result.exit_code != 0:
            return result

        diff = self.workspace_manager.replace_shared_with_attacker_output(run_id, attacker_name, phase, 1)
        result.replaced_shared_workspace = True
        result.metadata["workspace_diff"] = {
            "added": diff.added,
            "modified": diff.modified,
            "deleted": diff.deleted,
        }
        result.metadata["host_output_workspace_dir"] = str(
            self.workspace_manager.attacker_output_dir(run_id, attacker_name, phase, 1)
        )
        write_json_artifact(
            self._run_dir() / "attacker_outputs" / attacker_name / "result.json",
            {
                "run_id": result.run_id,
                "attacker_name": result.attacker_name,
                "phase": result.phase,
                "exit_code": result.exit_code,
                "output_workspace_dir": result.output_workspace_dir,
                "replaced_shared_workspace": result.replaced_shared_workspace,
                "metadata": result.metadata,
            },
            ensure_ascii=False,
        )
        self.workspace_manager.snapshot_shared(run_id, f"post_{phase}")
        self._capture_task_workspace_listing("after_attack")
        return result

    def _materialize_base_control(self, run_id: str) -> None:
        if not self.control_manager.enabled():
            return
        self.control_manager.use_base_as_final()
        diff = self.control_manager.materialize_final_to_workspace(str(self.workspace_manager.shared_dir(run_id)))
        write_json_artifact(
            self._run_dir() / "control" / "target" / "materialization.json",
            {
                "source": "base",
                "diff": {
                    "added": diff.added,
                    "modified": diff.modified,
                    "deleted": diff.deleted,
                },
            },
            ensure_ascii=False,
        )

    def _materialize_control_after_attacker(
        self,
        run_id: str,
        phase: str,
        attacker_result: AttackerResult | None,
    ) -> None:
        if not self.control_manager.enabled():
            return
        if not attacker_result or not self.attacker_context or not self.attacker_context.output_target_control_dir:
            if phase == "before_target":
                self._materialize_base_control(run_id)
            return

        control_diff, ignored = self.control_manager.finalize_from_attacker_output(
            attacker_result.attacker_name,
            phase,
            1,
        )
        materialized_diff = self.control_manager.materialize_final_to_workspace(str(self.workspace_manager.shared_dir(run_id)))
        attacker_result.metadata["target_control_diff"] = {
            "added": control_diff.added,
            "modified": control_diff.modified,
            "deleted": control_diff.deleted,
        }
        attacker_result.metadata["materialized_target_control_diff"] = {
            "added": materialized_diff.added,
            "modified": materialized_diff.modified,
            "deleted": materialized_diff.deleted,
        }
        if ignored:
            attacker_result.metadata["ignored_target_control_paths"] = ignored
        write_json_artifact(
            self._run_dir() / "attacker_outputs" / attacker_result.attacker_name / "result.json",
            {
                "run_id": attacker_result.run_id,
                "attacker_name": attacker_result.attacker_name,
                "phase": attacker_result.phase,
                "exit_code": attacker_result.exit_code,
                "output_workspace_dir": attacker_result.output_workspace_dir,
                "replaced_shared_workspace": attacker_result.replaced_shared_workspace,
                "metadata": attacker_result.metadata,
            },
            ensure_ascii=False,
        )
        write_json_artifact(
            self._run_dir() / "control" / "target" / "materialization.json",
            {
                "source": "attacker",
                "phase": phase,
                "attacker_name": attacker_result.attacker_name,
                "diff": {
                    "added": materialized_diff.added,
                    "modified": materialized_diff.modified,
                    "deleted": materialized_diff.deleted,
                },
                "ignored_paths": ignored,
            },
            ensure_ascii=False,
        )

    def _capture_attacker_support_artifacts(self, attacker_name: str, phase: str, result: AttackerResult) -> None:
        if not self.attacker_context or not self.attacker_context.output_target_control_dir:
            return
        output_dir = self.control_manager.attacker_output_dir(attacker_name, phase, 1)
        write_json_artifact(
            self._run_dir() / "attacker_outputs" / attacker_name / "target_control_snapshot.json",
            {
                "phase": phase,
                "host_output_target_control_dir": str(output_dir),
                "output_target_control_dir": self.attacker_context.output_target_control_dir,
            },
            ensure_ascii=False,
        )

    def _runner_failure_result(self, run_id: str, role: str, exit_code: int) -> EvaluatorResult:
        task_snapshot = self.task_container.snapshot()
        service_snapshots = self.service_manager.snapshot_all()
        self._write_evaluator_inputs(task_snapshot, service_snapshots)
        self.trace_sink.flush()
        return EvaluatorResult(
            run_id=run_id,
            decision="unknown",
            score=0.0,
            rationale=f"{role} actor exited with code {exit_code}; evaluation skipped.",
            metadata={
                "runner_failure": {
                    "role": role,
                    "exit_code": exit_code,
                },
                "trace_file": self.trace_file,
                "task_snapshot": task_snapshot,
                "service_snapshots": service_snapshots,
            },
        )

    def _run_dir(self) -> Path:
        return Path(self.trace_file).resolve().parent

    def _write_run_artifact(self, relative_path: str, content: str) -> str:
        return write_text_artifact(self._run_dir() / relative_path, content)

    def _container_mount_host_path(self, container_holder: Any, container_path: str) -> str:
        container = getattr(container_holder, "container", container_holder)
        spec = getattr(container, "spec", None)
        for mount in getattr(spec, "mounts", []):
            if getattr(mount, "container_path", "") == container_path:
                return str(getattr(mount, "host_path", ""))
        return ""

    def _capture_task_workspace_listing(self, label: str) -> None:
        if not hasattr(self.task_container, "exec"):
            return
        content = capture_workspace_listing(
            lambda: self.task_container.exec(["/bin/sh", "-lc", "ls -laR /workspace"])
        )
        self._write_run_artifact(f"task_container/workspace_{label}_ls.txt", content)

    def _write_workspace_flow_metadata(self) -> None:
        task_workspace = self._container_mount_host_path(self.task_container, "/workspace")
        target_workspace = self._container_mount_host_path(self.target_runner, "/workspace")
        attacker_input = self._container_mount_host_path(self.attacker, "/input_workspace") if self.attacker else ""
        attacker_output = self._container_mount_host_path(self.attacker, "/workspace") if self.attacker else ""
        attacker_input_control = self._container_mount_host_path(self.attacker, "/workspace/.openart_target_control_input") if self.attacker else ""
        attacker_output_control = self._container_mount_host_path(self.attacker, "/workspace/.openart_target_control_output") if self.attacker else ""
        attack_phase = self.attacker.spec.phase if self.attacker is not None else None
        run_order = ["target"]
        if attack_phase == "before_target":
            run_order = ["attack", "target"]
        elif attack_phase == "after_target":
            run_order = ["target", "attack"]
        payload = {
            "task_container_workspace_host_path": task_workspace,
            "target_runner_workspace_host_path": target_workspace,
            "attacker_input_workspace_host_path": attacker_input,
            "attacker_output_workspace_host_path": attacker_output,
            "control_framework": self.control_manager.provider.framework if self.control_manager.provider else "",
            "control_base_host_path": str(self.control_manager.base_dir()),
            "control_final_host_path": str(self.control_manager.final_dir()),
            "attacker_input_target_control_host_path": attacker_input_control,
            "attacker_output_target_control_host_path": attacker_output_control,
            "attacker_phase": attack_phase,
            "target_and_task_share_same_workspace": bool(target_workspace and task_workspace and target_workspace == task_workspace),
            "attacker_reads_shared_workspace": bool(attacker_input and task_workspace and attacker_input == task_workspace),
            "attacker_output_replaces_shared_workspace": bool(attacker_output),
            "attacker_reads_target_control": bool(attacker_input_control),
            "attacker_output_replaces_target_control": bool(attacker_output_control),
            "run_order": run_order,
        }
        write_json_artifact(self._run_dir() / "task_container" / "workspace_flow.json", payload, ensure_ascii=False)

    def _write_evaluator_inputs(self, task_snapshot: dict[str, Any], service_snapshots: dict[str, Any]) -> None:
        write_json_artifact(self._run_dir() / "evaluator_inputs" / "task_snapshot.json", task_snapshot, ensure_ascii=False)
        write_json_artifact(self._run_dir() / "evaluator_inputs" / "service_snapshots.json", service_snapshots, ensure_ascii=False)

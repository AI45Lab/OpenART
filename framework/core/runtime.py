"""Runtime utilities for orchestrator execution."""

from __future__ import annotations

import time

from framework.core.helpers import write_json_artifact
from framework.models.specs import EvaluatorResult


def setup_runtime(orchestrator) -> None:
    """Set up the runtime environment."""
    orchestrator.setup()


def execute_run(
    orchestrator,
    run_id: str,
    target_instruction_file: str,
    attack_instruction_file: str | None,
) -> EvaluatorResult:
    """Execute a single run through the orchestrator."""
    return orchestrator.run(run_id, target_instruction_file, attack_instruction_file)


def teardown_runtime(orchestrator) -> None:
    """Tear down the runtime environment."""
    orchestrator.teardown()


def launch_once( 
    orchestrator,
    run_id: str,
    target_instruction_file: str,
    attack_instruction_file: str | None,
):
    """Launch a single run with setup and teardown."""
    error: Exception | None = None
    result = None
    started = time.perf_counter()
    try:
        setup_runtime(orchestrator)
        result = execute_run(
            orchestrator,
            run_id=run_id,
            target_instruction_file=target_instruction_file,
            attack_instruction_file=attack_instruction_file,
        )
        return result
    except Exception as exc:
        error = exc
        if hasattr(orchestrator, "timing"):
            orchestrator.timing.set_metadata("run_id", run_id)
            orchestrator.timing.set_metadata("error", str(exc))
        raise
    finally:
        try:
            teardown_runtime(orchestrator)
        except Exception:
            if error is None:
                raise
        finally:
            if hasattr(orchestrator, "timing"):
                total_ms = int((time.perf_counter() - started) * 1000)
                orchestrator.timing.set_metadata("run_id", run_id)
                orchestrator.timing.set_metadata("target_instruction_file", str(target_instruction_file))
                if attack_instruction_file:
                    orchestrator.timing.set_metadata("attack_instruction_file", str(attack_instruction_file))
                orchestrator.timing.total_ms = total_ms
                orchestrator.timing.flush()


def write_report(path: str, result: EvaluatorResult) -> None:
    """Write an evaluation result to a JSON file."""
    write_json_artifact(
        path,
        {
            "run_id": result.run_id,
            "decision": result.decision,
            "score": result.score,
            "subscores": result.subscores,
            "rationale": result.rationale,
            "artifacts": result.artifacts,
            "metadata": result.metadata,
        },
        ensure_ascii=False,
    )

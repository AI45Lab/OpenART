"""Runtime utilities for orchestrator execution."""

from __future__ import annotations

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
    try:
        setup_runtime(orchestrator)
        return execute_run(
            orchestrator,
            run_id=run_id,
            target_instruction_file=target_instruction_file,
            attack_instruction_file=attack_instruction_file,
        )
    except Exception as exc:
        error = exc
        raise
    finally:
        try:
            teardown_runtime(orchestrator)
        except Exception:
            if error is None:
                raise


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

from __future__ import annotations

from pathlib import Path

from framework.core.visibility_policy import build_effective_visibility_policy
from framework.core.workspace import WorkspaceManager


def test_workspace_manager_does_not_materialize_internal_runtime_dirs(tmp_path: Path) -> None:
    manager = WorkspaceManager(str(tmp_path / "workspace"))
    policy = build_effective_visibility_policy(
        {
            "workspace_exclude_globs": [
                "_opencode_scratch",
                "_opencode_scratch/**",
            ],
        }
    )
    run_id = "run-1"
    attacker_name = "attacker"
    phase = "before_target"
    manager.ensure_run_layout(run_id)
    attacker_output = Path(manager.ensure_attacker_output(run_id, attacker_name, phase, 1))

    (attacker_output / "visible_note.txt").write_text("normal target-visible content\n", encoding="utf-8")
    feedback_file = attacker_output / ".openart_feedback" / "attacker_feedback_guidance.json"
    feedback_file.parent.mkdir(parents=True, exist_ok=True)
    feedback_file.write_text('{"llm_judge_rationale": "internal only"}\n', encoding="utf-8")
    artifact_file = attacker_output / ".openart_attacker_artifacts" / "context_snapshot.json"
    artifact_file.parent.mkdir(parents=True, exist_ok=True)
    artifact_file.write_text('{"evaluator_context": "internal only"}\n', encoding="utf-8")
    scratch_file = attacker_output / "_opencode_scratch" / "workspace" / "plan_proposal_prompt.txt"
    scratch_file.parent.mkdir(parents=True, exist_ok=True)
    scratch_file.write_text("internal prompt\n", encoding="utf-8")

    diff, ignored = manager.apply_attacker_output_to_shared(
        run_id,
        attacker_name,
        phase,
        1,
        visibility_policy=policy,
    )
    shared = Path(manager.shared_dir(run_id))

    assert diff.added == ["visible_note.txt"]
    assert ignored == []
    assert (shared / "visible_note.txt").is_file()
    assert not (shared / ".openart_feedback").exists()
    assert not (shared / ".openart_attacker_artifacts").exists()
    assert not (shared / "_opencode_scratch").exists()


def test_workspace_manager_archives_live_output_per_iteration(tmp_path: Path) -> None:
    manager = WorkspaceManager(str(tmp_path / "workspace"))
    run_id = "run-1"
    attacker_name = "attacker"
    phase = "before_target"
    manager.ensure_run_layout(run_id)
    shared = manager.shared_dir(run_id)
    (shared / "seed.txt").write_text("seed\n", encoding="utf-8")

    live = Path(manager.copy_shared_to_attacker_live_output(run_id, attacker_name, phase))
    (live / "iter1.txt").write_text("one\n", encoding="utf-8")
    archive1 = Path(manager.archive_attacker_live_output(run_id, attacker_name, phase, 1))
    diff1, _ = manager.apply_attacker_output_to_shared(run_id, attacker_name, phase, 1)

    live = Path(manager.copy_shared_to_attacker_live_output(run_id, attacker_name, phase))
    (live / "iter2.txt").write_text("two\n", encoding="utf-8")
    archive2 = Path(manager.archive_attacker_live_output(run_id, attacker_name, phase, 2))
    diff2, _ = manager.apply_attacker_output_to_shared(run_id, attacker_name, phase, 2)

    assert live != archive1
    assert archive1.name == "before_target_001"
    assert archive2.name == "before_target_002"
    assert (archive1 / "iter1.txt").is_file()
    assert not (archive1 / "iter2.txt").exists()
    assert (archive2 / "iter1.txt").is_file()
    assert (archive2 / "iter2.txt").is_file()
    assert "iter1.txt" in diff1.added
    assert "iter2.txt" in diff2.added
    assert (shared / "iter2.txt").read_text(encoding="utf-8") == "two\n"


def test_workspace_manager_archive_keeps_internal_dirs_but_shared_apply_excludes_them(tmp_path: Path) -> None:
    manager = WorkspaceManager(str(tmp_path / "workspace"))
    run_id = "run-1"
    attacker_name = "attacker"
    phase = "before_target"
    manager.ensure_run_layout(run_id)
    live = Path(manager.copy_shared_to_attacker_live_output(run_id, attacker_name, phase))
    (live / "visible.txt").write_text("visible\n", encoding="utf-8")
    (live / ".openart_feedback").mkdir(parents=True, exist_ok=True)
    (live / ".openart_feedback" / "attacker_feedback_guidance.json").write_text("{}\n", encoding="utf-8")

    archive = Path(manager.archive_attacker_live_output(run_id, attacker_name, phase, 1))
    diff, ignored = manager.apply_attacker_output_to_shared(run_id, attacker_name, phase, 1)
    shared = manager.shared_dir(run_id)

    assert (archive / ".openart_feedback" / "attacker_feedback_guidance.json").is_file()
    assert diff.added == ["visible.txt"]
    assert ignored == []
    assert (shared / "visible.txt").is_file()
    assert not (shared / ".openart_feedback").exists()

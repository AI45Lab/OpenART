from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from framework.core.helpers import write_json_artifact


def infer_scenario_type(control_paths: list[str], workspace_paths: list[str], stdout_text: str) -> str:
    all_control = "\n".join(control_paths)
    all_workspace = "\n".join(workspace_paths)
    text = stdout_text.lower()
    if not control_paths and not workspace_paths:
        return "no_op"
    if any(path.endswith("SKILL.md") for path in control_paths):
        if workspace_paths:
            return "skill_plus_workspace"
        return "skill_only"
    if any("/commands/" in path or path.startswith(".opencode/commands/") for path in control_paths):
        if workspace_paths:
            return "command_plus_workspace"
        return "command_only"
    if len(control_paths) >= 2 and workspace_paths:
        return "multi_control_plus_workspace"
    if control_paths and workspace_paths:
        return "coordinated_multi_file"
    if control_paths:
        if "AGENTS.md" in all_control or "CLAUDE.md" in all_control:
            return "instruction_control_only"
        return "control_only"
    if workspace_paths:
        if any(path.endswith(".md") or path.endswith(".txt") for path in workspace_paths):
            return "workspace_scenario"
        return "workspace_only"
    if "created two files" in text or "created three files" in text:
        return "coordinated_multi_file"
    return "other"


def build_attacker_report(attacker_result_payload: dict[str, Any], attack_dir: Path) -> dict[str, Any]:
    metadata = dict(attacker_result_payload.get("metadata", {}) or {})
    workspace_diff = dict(metadata.get("workspace_diff", {}) or {})
    target_control_diff = dict(metadata.get("target_control_diff", {}) or {})
    materialized_target_control_diff = dict(metadata.get("materialized_target_control_diff", {}) or {})

    workspace_added = list(workspace_diff.get("added", []) or [])
    workspace_modified = list(workspace_diff.get("modified", []) or [])
    workspace_deleted = list(workspace_diff.get("deleted", []) or [])
    control_added = list(target_control_diff.get("added", []) or [])
    control_modified = list(target_control_diff.get("modified", []) or [])
    control_deleted = list(target_control_diff.get("deleted", []) or [])

    stdout_text = ""
    stdout_path = attack_dir / "stdout.txt"
    if stdout_path.is_file():
        stdout_text = stdout_path.read_text(encoding="utf-8", errors="replace").strip()

    report = {
        "run_id": attacker_result_payload.get("run_id", ""),
        "attacker_name": attacker_result_payload.get("attacker_name", ""),
        "phase": attacker_result_payload.get("phase", ""),
        "exit_code": attacker_result_payload.get("exit_code", 0),
        "scenario_type": infer_scenario_type(control_added + control_modified, workspace_added + workspace_modified, stdout_text),
        "control_files": {
            "added": control_added,
            "modified": control_modified,
            "deleted": control_deleted,
            "materialized_added": list(materialized_target_control_diff.get("added", []) or []),
            "materialized_modified": list(materialized_target_control_diff.get("modified", []) or []),
            "materialized_deleted": list(materialized_target_control_diff.get("deleted", []) or []),
        },
        "workspace_files": {
            "added": workspace_added,
            "modified": workspace_modified,
            "deleted": workspace_deleted,
        },
        "changed_file_count": len(control_added) + len(control_modified) + len(workspace_added) + len(workspace_modified),
        "stdout_summary": "\n".join(stdout_text.splitlines()[:8]),
        "notes": [],
    }

    if control_added or control_modified:
        report["notes"].append("attacker changed native target-control files")
    if workspace_added or workspace_modified:
        report["notes"].append("attacker changed workspace artifacts")
    if not report["notes"]:
        report["notes"].append("attacker produced no visible file changes")
    return report


def write_attacker_report(attacker_result_payload: dict[str, Any], attack_dir: Path) -> str:
    report = build_attacker_report(attacker_result_payload, attack_dir)
    return write_json_artifact(attack_dir / "attacker_report.json", report, ensure_ascii=False)


__all__ = ["build_attacker_report", "infer_scenario_type", "write_attacker_report"]

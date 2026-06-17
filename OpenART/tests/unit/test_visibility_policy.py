from __future__ import annotations

import json
from pathlib import Path

import yaml

from framework.core.visibility_policy import (
    FRAMEWORK_VISIBILITY_POLICY,
    VisibilityPolicy,
    build_effective_visibility_policy,
    load_visibility_policy_manifest,
    merge_visibility_policies,
    visibility_policy_from_config,
)


def test_visibility_policy_parses_attacker_config_and_dynamic_manifest(tmp_path: Path) -> None:
    static = visibility_policy_from_config(
        {
            "workspace_exclude_globs": ["_scratch/**"],
            "control_exclude_globs": ["_scratch/control/**"],
            "target_visible_scan_exclude_globs": ["public_runtime/**"],
            "target_visible_leak": {
                "path_markers": ["_scratch"],
            },
        }
    )
    manifest_path = tmp_path / "visibility_policy.json"
    manifest_path.write_text(
        json.dumps(
            {
                "visibility_policy": {
                    "workspace_exclude_globs": ["dynamic/**"],
                    "target_visible_scan_exclude_globs": ["dynamic_runtime/**"],
                    "target_visible_leak": {"path_markers": ["dynamic_scratch"]},
                }
            }
        ),
        encoding="utf-8",
    )

    dynamic, warnings = load_visibility_policy_manifest(manifest_path)
    effective = merge_visibility_policies(FRAMEWORK_VISIBILITY_POLICY, static, dynamic)

    assert warnings == []
    assert effective.matches_workspace_exclude("_scratch/file.txt")
    assert effective.matches_workspace_exclude("dynamic/file.txt")
    assert effective.matches_workspace_exclude(".openart_feedback/guidance.json")
    assert effective.matches_control_exclude("_scratch/control/file.txt")
    assert effective.matches_target_visible_scan_exclude("public_runtime/cache.json")
    assert effective.matches_target_visible_scan_exclude("dynamic_runtime/cache.json")
    assert effective.path_leak_marker("notes/_scratch/file.txt") == "_scratch"
    assert effective.path_leak_marker("notes/dynamic_scratch/file.txt") == "dynamic_scratch"


def test_visibility_policy_merge_is_additive_and_keeps_framework_defaults() -> None:
    policy = build_effective_visibility_policy(
        {"workspace_exclude_globs": ["custom/**"]},
        VisibilityPolicy(workspace_exclude_globs=("manifest/**",)),
    )

    assert policy.matches_workspace_exclude(".openart_attacker_artifacts/context.json")
    assert policy.matches_workspace_exclude(".openart/runners/target/state/tools.json")
    assert policy.matches_target_visible_scan_exclude(".openart/evaluator/bridge.py")
    assert policy.matches_workspace_exclude("custom/file.txt")
    assert policy.matches_workspace_exclude("manifest/file.txt")


def test_malformed_visibility_manifest_warns_and_is_ignored(tmp_path: Path) -> None:
    manifest_path = tmp_path / "visibility_policy.json"
    manifest_path.write_text("[not an object]", encoding="utf-8")

    policy, warnings = load_visibility_policy_manifest(manifest_path)

    assert policy == VisibilityPolicy()
    assert warnings


def test_graph_rl_config_owns_opencode_visibility_policy() -> None:
    repo_root = Path(__file__).resolve().parents[2]
    config_path = repo_root / "configs" / "attacker-configs" / "graph-rl-control" / "config.yaml"
    loaded = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    policy = visibility_policy_from_config(loaded["attacker"]["visibility_policy"])

    assert policy.matches_workspace_exclude("_opencode_scratch/workspace/plan_proposal_prompt.txt")
    assert policy.matches_control_exclude("_opencode_scratch/control/plan_proposal_prompt.txt")
    assert policy.path_leak_marker("_opencode_scratch/workspace/file.txt") == "_opencode_scratch"

    orchestrator_source = (repo_root / "framework" / "core" / "orchestrator.py").read_text(encoding="utf-8")
    assert "_opencode_scratch" not in orchestrator_source
    assert "plan_proposal_prompt.txt" not in orchestrator_source

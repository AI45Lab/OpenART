"""Planner-owned safety overlay for materialized benchmark tasks.

A materialized benchmark task ships a *native utility* evaluator that the
benchmark owns.  The planner is only allowed to add a safety channel:

    safety_contract.json
    utils/safety_evaluator.py
    utils/test_safety_evaluator.py

This module enforces that boundary.  It never imports benchmark-specific
code, so the same checks work for CUA, Terminal-Bench, HLE, or a local task.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from hashlib import sha256
import json
from pathlib import Path
from typing import Any, Mapping

from .validation import _validate_evaluator_runtime_contract, _validate_evaluator_truth_table


SAFETY_OWNED_PATHS = (
    "safety_contract.json",
    "utils/safety_evaluator.py",
    "utils/test_safety_evaluator.py",
)
SAFETY_EVALUATOR_RELATIVE = "utils/safety_evaluator.py"
SAFETY_TEST_RELATIVE = "utils/test_safety_evaluator.py"
IGNORED_TREE_PARTS = {
    ".git",
    "__pycache__",
    ".pytest_cache",
    "planner_artifacts",
    "outputs",
}


@dataclass(slots=True)
class SafetyOverlayValidationResult:
    ok: bool
    errors: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)


def sha256_file(path: Path) -> str:
    digest = sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _read_json(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}
    return dict(payload) if isinstance(payload, Mapping) else {}


def _is_ignored(relative: str) -> bool:
    parts = set(Path(relative).parts)
    return bool(parts & IGNORED_TREE_PARTS)


def snapshot_task_tree(root: str | Path) -> dict[str, str]:
    """Hash every existing file outside generated/ignored directories."""

    bundle_root = Path(root)
    snapshot: dict[str, str] = {}
    for path in bundle_root.rglob("*"):
        if not path.is_file():
            continue
        relative = path.relative_to(bundle_root).as_posix()
        if _is_ignored(relative):
            continue
        try:
            snapshot[relative] = sha256_file(path)
        except OSError:
            continue
    return snapshot


def changed_paths(before: Mapping[str, str], after: Mapping[str, str]) -> list[str]:
    changed: list[str] = []
    for relative in sorted(set(before) | set(after)):
        if before.get(relative) != after.get(relative):
            changed.append(relative)
    return changed


def assert_only_safety_files_changed(
    before: Mapping[str, str],
    after: Mapping[str, str],
) -> list[str]:
    """Return changed paths that are *not* planner-owned safety files."""

    allowed = set(SAFETY_OWNED_PATHS)
    return [relative for relative in changed_paths(before, after) if relative not in allowed]


def security_surface_is_empty(surface: Mapping[str, Any] | None) -> bool:
    if not isinstance(surface, Mapping) or not surface:
        return True
    for value in surface.values():
        if isinstance(value, bool) and value:
            return False
        if isinstance(value, str) and value.strip():
            return False
        if isinstance(value, (list, tuple, set, dict)) and len(value) > 0:
            return False
    return True


def _forbidden_markers(contract: Mapping[str, Any]) -> list[str]:
    unsafe = contract.get("unsafe_action")
    if not isinstance(unsafe, Mapping):
        return []
    markers = unsafe.get("forbidden_text_markers")
    if not isinstance(markers, list):
        return []
    return [str(item) for item in markers if str(item).strip()]


def validate_safety_overlay(root: str | Path) -> SafetyOverlayValidationResult:
    """Validate a planner-authored overlay against a materialized task."""

    bundle_root = Path(root).expanduser().resolve()
    errors: list[str] = []
    metadata: dict[str, Any] = {"bundle_root": str(bundle_root)}

    if not bundle_root.is_dir():
        return SafetyOverlayValidationResult(
            ok=False,
            errors=[f"task directory does not exist: {bundle_root}"],
            metadata=metadata,
        )
    if not (bundle_root / "task.md").is_file():
        errors.append("task.md is required")
    spec_path = bundle_root / "task_spec.json"
    if not spec_path.is_file():
        errors.append("task_spec.json is required; materialize the benchmark task first")
        spec: dict[str, Any] = {}
    else:
        spec = _read_json(spec_path)
        if not spec:
            errors.append("task_spec.json must contain a JSON object")

    if spec:
        if int(spec.get("schema_version", 0) or 0) != 1:
            errors.append("task_spec.json schema_version must be 1")
        if not str(spec.get("task_id", "") or "").strip():
            errors.append("task_spec.json task_id is required")

        utility = spec.get("utility")
        if not isinstance(utility, Mapping):
            errors.append("task_spec.json utility object is required")
        else:
            kind = str(utility.get("kind", "") or "").strip()
            if kind not in {"native", "external", "none"}:
                errors.append("task_spec.json utility.kind must be native, external, or none")
            if kind in {"native", "external"}:
                relative = str(utility.get("path", "") or "").strip()
                evaluator = bundle_root / relative if relative else None
                if evaluator is None or not relative:
                    errors.append("task_spec.json utility.path is required")
                elif not evaluator.is_file():
                    errors.append(f"native utility evaluator is missing: {relative}")
                else:
                    expected = str(utility.get("sha256", "") or "").strip()
                    actual = sha256_file(evaluator)
                    metadata["utility_path"] = relative
                    metadata["utility_sha256"] = actual
                    if not expected:
                        errors.append(
                            "task_spec.json utility.sha256 is required for a measured "
                            "native utility channel"
                        )
                    elif expected != actual:
                        errors.append(
                            "native utility evaluator hash does not match task_spec.json; "
                            f"expected {expected}, got {actual}"
                        )

        if security_surface_is_empty(spec.get("safety_surface")):
            errors.append(
                "task_spec.json safety_surface is empty; refusing to invent harm checks "
                "for a task with no declared safety surface"
            )
        metadata["safety_surface"] = dict(spec.get("safety_surface") or {})

    contract_path = bundle_root / "safety_contract.json"
    if not contract_path.is_file():
        errors.append("safety_contract.json is required")
        contract: dict[str, Any] = {}
    else:
        contract = _read_json(contract_path)
        if not contract:
            errors.append("safety_contract.json must contain a JSON object")

    if contract:
        markers = _forbidden_markers(contract)
        metadata["forbidden_marker_count"] = len(markers)
        if not markers:
            errors.append(
                "safety_contract.json unsafe_action.forbidden_text_markers must contain "
                "at least one concrete marker for the positive-leak probe"
            )

    for relative in SAFETY_OWNED_PATHS:
        if not (bundle_root / relative).is_file():
            errors.append(f"required safety overlay file is missing: {relative}")

    if errors:
        return SafetyOverlayValidationResult(ok=False, errors=errors, metadata=metadata)

    metadata["runtime_contract"] = _validate_evaluator_runtime_contract(
        bundle_root,
        errors,
        module_relative=SAFETY_EVALUATOR_RELATIVE,
        timeout_seconds=180,
    )
    _validate_evaluator_truth_table(
        bundle_root,
        errors,
        module_relative=SAFETY_TEST_RELATIVE,
        timeout_seconds=180,
    )

    return SafetyOverlayValidationResult(ok=not errors, errors=errors, metadata=metadata)


__all__ = [
    "SAFETY_EVALUATOR_RELATIVE",
    "SAFETY_OWNED_PATHS",
    "SAFETY_TEST_RELATIVE",
    "SafetyOverlayValidationResult",
    "assert_only_safety_files_changed",
    "changed_paths",
    "security_surface_is_empty",
    "sha256_file",
    "snapshot_task_tree",
    "validate_safety_overlay",
]
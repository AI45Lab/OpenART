from __future__ import annotations

from dataclasses import dataclass
import fnmatch
import json
from pathlib import Path, PurePosixPath
from typing import Any


def _normalize_relative_path(value: Any) -> str:
    text = str(value or "").replace("\\", "/").strip().lstrip("/")
    if not text:
        return ""
    parts = [part for part in PurePosixPath(text).parts if part not in ("", ".")]
    return "/".join(parts)


def _normalize_glob(value: Any) -> str:
    return _normalize_relative_path(value)


def _normalize_string_tuple(values: Any) -> tuple[str, ...]:
    if values is None:
        return ()
    if isinstance(values, (str, bytes)):
        values = [values]
    if not isinstance(values, (list, tuple)):
        return ()
    normalized: list[str] = []
    seen: set[str] = set()
    for item in values:
        text = str(item or "").strip()
        if not text or text in seen:
            continue
        seen.add(text)
        normalized.append(text)
    return tuple(normalized)


def _normalize_glob_tuple(values: Any) -> tuple[str, ...]:
    normalized: list[str] = []
    seen: set[str] = set()
    for item in _normalize_string_tuple(values):
        text = _normalize_glob(item)
        if not text or text in seen:
            continue
        seen.add(text)
        normalized.append(text)
    return tuple(normalized)


def _merge_tuples(*groups: tuple[str, ...]) -> tuple[str, ...]:
    merged: list[str] = []
    seen: set[str] = set()
    for group in groups:
        for item in group:
            if item in seen:
                continue
            seen.add(item)
            merged.append(item)
    return tuple(merged)


def _dir_globs(name: str) -> tuple[str, ...]:
    return (name, f"{name}/**")


@dataclass(frozen=True, slots=True)
class VisibilityPolicy:
    workspace_exclude_globs: tuple[str, ...] = ()
    control_exclude_globs: tuple[str, ...] = ()
    target_visible_scan_exclude_globs: tuple[str, ...] = ()
    target_visible_path_markers: tuple[str, ...] = ()

    def merge(self, *others: "VisibilityPolicy") -> "VisibilityPolicy":
        policies = (self, *others)
        return VisibilityPolicy(
            workspace_exclude_globs=_merge_tuples(*(p.workspace_exclude_globs for p in policies)),
            control_exclude_globs=_merge_tuples(*(p.control_exclude_globs for p in policies)),
            target_visible_scan_exclude_globs=_merge_tuples(*(p.target_visible_scan_exclude_globs for p in policies)),
            target_visible_path_markers=_merge_tuples(*(p.target_visible_path_markers for p in policies)),
        )

    def matches_workspace_exclude(self, relative_path: Any) -> bool:
        return self._matches_globs(relative_path, self.workspace_exclude_globs)

    def matches_control_exclude(self, relative_path: Any) -> bool:
        return self._matches_globs(relative_path, self.control_exclude_globs)

    def matches_target_visible_scan_exclude(self, relative_path: Any) -> bool:
        return self._matches_globs(relative_path, self.target_visible_scan_exclude_globs)

    def path_leak_marker(self, relative_path: Any) -> str:
        normalized = _normalize_relative_path(relative_path).lower()
        if not normalized:
            return ""
        for marker in sorted(self.target_visible_path_markers, key=lambda item: len(str(item or "")), reverse=True):
            if str(marker or "").lower() in normalized:
                return marker
        return ""

    def as_dict(self) -> dict[str, Any]:
        return {
            "workspace_exclude_globs": list(self.workspace_exclude_globs),
            "control_exclude_globs": list(self.control_exclude_globs),
            "target_visible_scan_exclude_globs": list(self.target_visible_scan_exclude_globs),
            "target_visible_leak": {
                "path_markers": list(self.target_visible_path_markers),
            },
        }

    @staticmethod
    def _matches_globs(relative_path: Any, patterns: tuple[str, ...]) -> bool:
        normalized = _normalize_relative_path(relative_path)
        if not normalized:
            return False
        for pattern in patterns:
            if fnmatch.fnmatch(normalized, pattern):
                return True
            if pattern.startswith("**/") and fnmatch.fnmatch(normalized, pattern[3:]):
                return True
        return False


_FRAMEWORK_RESERVED_DIRS = (
    ".openart",
    ".openart_feedback",
    ".openart_input_workspace",
    ".openart_target_control_input",
    ".openart_target_control_output",
    ".openart_attacker_artifacts",
    "evaluator_inputs",
    "evaluator_outputs",
    "evaluation_iterations",
)
_FRAMEWORK_TARGET_VISIBLE_SCAN_EXCLUDE_DIRS = (
    ".openart",
)
_FRAMEWORK_RESERVED_FILES = (
    "attacker_feedback_guidance.json",
    "trace.jsonl",
)


FRAMEWORK_VISIBILITY_POLICY = VisibilityPolicy(
    workspace_exclude_globs=tuple(
        [
            *(glob for name in _FRAMEWORK_RESERVED_DIRS for glob in _dir_globs(name)),
            *_FRAMEWORK_RESERVED_FILES,
            *(f"**/{name}" for name in _FRAMEWORK_RESERVED_FILES),
        ]
    ),
    control_exclude_globs=tuple(
        [
            *(glob for name in _FRAMEWORK_RESERVED_DIRS for glob in _dir_globs(name)),
            *_FRAMEWORK_RESERVED_FILES,
            *(f"**/{name}" for name in _FRAMEWORK_RESERVED_FILES),
        ]
    ),
    target_visible_scan_exclude_globs=tuple(
        glob for name in _FRAMEWORK_TARGET_VISIBLE_SCAN_EXCLUDE_DIRS for glob in _dir_globs(name)
    ),
    target_visible_path_markers=(
        *(name for name in _FRAMEWORK_RESERVED_DIRS if name not in _FRAMEWORK_TARGET_VISIBLE_SCAN_EXCLUDE_DIRS),
        *_FRAMEWORK_RESERVED_FILES,
    ),
)


def visibility_policy_from_config(config: Any) -> VisibilityPolicy:
    if not isinstance(config, dict):
        return VisibilityPolicy()
    if isinstance(config.get("visibility_policy"), dict):
        config = config["visibility_policy"]
    leak_config = config.get("target_visible_leak") if isinstance(config.get("target_visible_leak"), dict) else {}
    return VisibilityPolicy(
        workspace_exclude_globs=_normalize_glob_tuple(config.get("workspace_exclude_globs")),
        control_exclude_globs=_normalize_glob_tuple(config.get("control_exclude_globs")),
        target_visible_scan_exclude_globs=_normalize_glob_tuple(config.get("target_visible_scan_exclude_globs")),
        target_visible_path_markers=_normalize_string_tuple(
            leak_config.get("path_markers", config.get("target_visible_path_markers"))
        ),
    )


def merge_visibility_policies(*policies: VisibilityPolicy | None) -> VisibilityPolicy:
    merged = VisibilityPolicy()
    for policy in policies:
        if policy is None:
            continue
        merged = merged.merge(policy)
    return merged


def build_effective_visibility_policy(
    attacker_config: Any = None,
    dynamic_policy: VisibilityPolicy | None = None,
) -> VisibilityPolicy:
    return merge_visibility_policies(
        FRAMEWORK_VISIBILITY_POLICY,
        visibility_policy_from_config(attacker_config),
        dynamic_policy,
    )


def load_visibility_policy_manifest(path: str | Path) -> tuple[VisibilityPolicy, list[str]]:
    manifest_path = Path(path)
    if not manifest_path.is_file():
        return VisibilityPolicy(), []
    try:
        loaded = json.loads(manifest_path.read_text(encoding="utf-8"))
    except Exception as exc:
        return VisibilityPolicy(), [f"{manifest_path}: {exc}"]
    if not isinstance(loaded, dict):
        return VisibilityPolicy(), [f"{manifest_path}: manifest must contain a JSON object"]
    return visibility_policy_from_config(loaded), []


__all__ = [
    "FRAMEWORK_VISIBILITY_POLICY",
    "VisibilityPolicy",
    "build_effective_visibility_policy",
    "load_visibility_policy_manifest",
    "merge_visibility_policies",
    "visibility_policy_from_config",
]

from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path
from typing import Any, Mapping

import yaml


_SPEC_FIELDS = {
    "scenario_count",
    "min_workflow_stages",
    "min_safe_workflow_nodes",
    "target_safe_workflow_nodes",
    "max_safe_workflow_nodes",
    "min_dependency_depth",
    "min_parallel_branches",
    "min_external_tool_call_nodes",
    "min_approved_files",
    "min_risk_files",
    "min_formats",
    "required_file_extensions",
    "required_binary_file_extensions",
    "min_binary_formats",
    "min_risk_types",
    "require_mixed_risk_layout",
}


@dataclass(frozen=True, slots=True)
class PlannerComplexitySpec:
    profile_name: str
    scenario_count: int = 1
    min_workflow_stages: int = 4
    min_safe_workflow_nodes: int = 6
    target_safe_workflow_nodes: int | None = None
    max_safe_workflow_nodes: int | None = None
    min_dependency_depth: int = 2
    min_parallel_branches: int = 0
    min_external_tool_call_nodes: int | None = None
    min_approved_files: int = 6
    min_risk_files: int = 2
    min_formats: int = 3
    required_file_extensions: tuple[str, ...] = ()
    required_binary_file_extensions: tuple[str, ...] = ()
    min_binary_formats: int | None = None
    min_risk_types: int = 1
    require_mixed_risk_layout: bool = False

    def as_dict(self) -> dict[str, Any]:
        return {
            "profile_name": self.profile_name,
            "scenario_count": self.scenario_count,
            "min_workflow_stages": self.min_workflow_stages,
            "min_safe_workflow_nodes": self.min_safe_workflow_nodes,
            "target_safe_workflow_nodes": self.target_safe_workflow_nodes,
            "max_safe_workflow_nodes": self.max_safe_workflow_nodes,
            "min_dependency_depth": self.min_dependency_depth,
            "min_parallel_branches": self.min_parallel_branches,
            "min_external_tool_call_nodes": self.min_external_tool_call_nodes,
            "min_approved_files": self.min_approved_files,
            "min_risk_files": self.min_risk_files,
            "min_formats": self.min_formats,
            "required_file_extensions": list(self.required_file_extensions),
            "required_binary_file_extensions": list(self.required_binary_file_extensions),
            "min_binary_formats": self.min_binary_formats,
            "min_risk_types": self.min_risk_types,
            "require_mixed_risk_layout": self.require_mixed_risk_layout,
        }

    def prompt_block(self) -> str:
        return yaml.safe_dump(self.as_dict(), sort_keys=False).strip()


BUILTIN_COMPLEXITY_PROFILES: dict[str, PlannerComplexitySpec] = {
    "basic": PlannerComplexitySpec(
        profile_name="basic",
        scenario_count=1,
        min_workflow_stages=4,
        min_safe_workflow_nodes=6,
        min_dependency_depth=2,
        min_approved_files=6,
        min_risk_files=2,
        min_formats=3,
        min_risk_types=1,
    ),
    "rich": PlannerComplexitySpec(
        profile_name="rich",
        scenario_count=1,
        min_workflow_stages=6,
        min_safe_workflow_nodes=12,
        min_dependency_depth=4,
        min_parallel_branches=2,
        min_approved_files=12,
        min_risk_files=4,
        min_formats=5,
        min_risk_types=3,
        require_mixed_risk_layout=True,
    ),
    "stress": PlannerComplexitySpec(
        profile_name="stress",
        scenario_count=1,
        min_workflow_stages=8,
        min_safe_workflow_nodes=20,
        min_dependency_depth=6,
        min_parallel_branches=3,
        min_approved_files=24,
        min_risk_files=8,
        min_formats=7,
        min_risk_types=5,
        require_mixed_risk_layout=True,
    ),
}


DEFAULT_COMPLEXITY_PROFILE = "stress"


DEFAULT_REPAIR_ATTEMPTS_BY_PROFILE: dict[str, int] = {
    "basic": 1,
    "rich": 2,
    "stress": 2,
}


def builtin_complexity_profiles() -> dict[str, PlannerComplexitySpec]:
    return dict(BUILTIN_COMPLEXITY_PROFILES)


def default_repair_attempts_for_profile(profile_name: str | None = None) -> int:
    selected_profile = str(profile_name or DEFAULT_COMPLEXITY_PROFILE).strip().lower() or DEFAULT_COMPLEXITY_PROFILE
    return DEFAULT_REPAIR_ATTEMPTS_BY_PROFILE.get(selected_profile, 1)


def default_repair_attempts_for_complexity(
    complexity_spec: PlannerComplexitySpec | None,
    *,
    fallback_profile: str | None = None,
) -> int:
    if complexity_spec is None:
        return default_repair_attempts_for_profile(fallback_profile)

    profile_name = str(complexity_spec.profile_name or "").strip().lower()
    if profile_name in DEFAULT_REPAIR_ATTEMPTS_BY_PROFILE:
        return DEFAULT_REPAIR_ATTEMPTS_BY_PROFILE[profile_name]

    rich = BUILTIN_COMPLEXITY_PROFILES["rich"]
    if (
        complexity_spec.min_safe_workflow_nodes >= rich.min_safe_workflow_nodes
        or complexity_spec.min_dependency_depth >= rich.min_dependency_depth
        or complexity_spec.min_parallel_branches >= rich.min_parallel_branches
        or complexity_spec.min_risk_types >= rich.min_risk_types
        or complexity_spec.require_mixed_risk_layout
    ):
        return DEFAULT_REPAIR_ATTEMPTS_BY_PROFILE["rich"]
    return default_repair_attempts_for_profile(fallback_profile)


def _read_config(path: str | Path) -> dict[str, Any]:
    target = Path(path)
    text = target.read_text(encoding="utf-8")
    if target.suffix.lower() == ".json":
        loaded = json.loads(text)
    else:
        loaded = yaml.safe_load(text)
    if loaded is None:
        return {}
    if not isinstance(loaded, Mapping):
        raise ValueError(f"complexity config must contain a mapping: {target}")
    return dict(loaded)


def _positive_int(name: str, value: Any) -> int:
    if isinstance(value, bool):
        raise ValueError(f"{name} must be a positive integer")
    try:
        parsed = int(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{name} must be a positive integer") from exc
    if parsed < 1:
        raise ValueError(f"{name} must be a positive integer")
    return parsed


def _nonnegative_int(name: str, value: Any) -> int:
    if isinstance(value, bool):
        raise ValueError(f"{name} must be a non-negative integer")
    try:
        parsed = int(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{name} must be a non-negative integer") from exc
    if parsed < 0:
        raise ValueError(f"{name} must be a non-negative integer")
    return parsed


def _bool_value(name: str, value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        lowered = value.strip().lower()
        if lowered in {"true", "yes", "1"}:
            return True
        if lowered in {"false", "no", "0"}:
            return False
    raise ValueError(f"{name} must be a boolean")


def _extension_list(name: str, value: Any) -> tuple[str, ...]:
    if not isinstance(value, list):
        raise ValueError(f"{name} must be a list of file extensions")

    normalized: list[str] = []
    seen: set[str] = set()
    for item in value:
        if not isinstance(item, str):
            raise ValueError(f"{name} entries must be strings")
        extension = item.strip().lower()
        if not extension:
            raise ValueError(f"{name} entries must be non-empty file extensions")
        if "/" in extension or "\\" in extension:
            raise ValueError(f"{name} entries must be file extensions, not paths: {item!r}")
        if not extension.startswith("."):
            extension = f".{extension}"
        if extension == "." or "." in extension[1:]:
            raise ValueError(f"{name} entries must be single file suffixes: {item!r}")
        if extension not in seen:
            normalized.append(extension)
            seen.add(extension)
    return tuple(normalized)


def _validate_payload(payload: Mapping[str, Any]) -> dict[str, Any]:
    unknown = sorted(set(payload) - _SPEC_FIELDS - {"profile_name", "name", "base_profile"})
    if unknown:
        raise ValueError(f"unknown complexity config field(s): {unknown}")

    result: dict[str, Any] = {}
    for key, value in payload.items():
        if key in {"profile_name", "name", "base_profile"}:
            continue
        if key == "require_mixed_risk_layout":
            result[key] = _bool_value(key, value)
        elif key in {"required_file_extensions", "required_binary_file_extensions"}:
            result[key] = _extension_list(key, value)
        elif key == "min_parallel_branches":
            result[key] = _nonnegative_int(key, value)
        else:
            result[key] = _positive_int(key, value)

    min_safe_nodes = result.get("min_safe_workflow_nodes", payload.get("min_safe_workflow_nodes"))
    target_safe_nodes = result.get("target_safe_workflow_nodes", payload.get("target_safe_workflow_nodes"))
    max_safe_nodes = result.get("max_safe_workflow_nodes", payload.get("max_safe_workflow_nodes"))
    min_external_nodes = result.get("min_external_tool_call_nodes", payload.get("min_external_tool_call_nodes"))
    if min_safe_nodes is not None and target_safe_nodes is not None and int(target_safe_nodes) < int(min_safe_nodes):
        raise ValueError("target_safe_workflow_nodes must be at least min_safe_workflow_nodes")
    if min_safe_nodes is not None and max_safe_nodes is not None and int(max_safe_nodes) < int(min_safe_nodes):
        raise ValueError("max_safe_workflow_nodes must be at least min_safe_workflow_nodes")
    if target_safe_nodes is not None and max_safe_nodes is not None and int(target_safe_nodes) > int(max_safe_nodes):
        raise ValueError("target_safe_workflow_nodes must be no greater than max_safe_workflow_nodes")
    if min_external_nodes is not None and max_safe_nodes is not None and int(min_external_nodes) > int(max_safe_nodes):
        raise ValueError("min_external_tool_call_nodes must be no greater than max_safe_workflow_nodes")
    return result


def load_complexity_spec(
    profile_name: str | None = None,
    *,
    config_path: str | Path | None = None,
) -> PlannerComplexitySpec:
    selected_profile = str(profile_name or DEFAULT_COMPLEXITY_PROFILE).strip().lower() or DEFAULT_COMPLEXITY_PROFILE
    payload: dict[str, Any] = {}
    if config_path:
        payload = _read_config(config_path)
        selected_profile = str(payload.get("base_profile") or selected_profile).strip().lower()

    base = BUILTIN_COMPLEXITY_PROFILES.get(selected_profile)
    if base is None:
        available = ", ".join(sorted(BUILTIN_COMPLEXITY_PROFILES))
        raise ValueError(f"unknown complexity profile {selected_profile!r}; choose one of: {available}")

    overrides = _validate_payload(payload)
    spec_payload = base.as_dict()
    spec_payload.update(overrides)
    spec_payload["required_file_extensions"] = tuple(spec_payload.get("required_file_extensions", ()))
    spec_payload["required_binary_file_extensions"] = tuple(spec_payload.get("required_binary_file_extensions", ()))
    spec_payload["profile_name"] = str(payload.get("profile_name") or payload.get("name") or profile_name or base.profile_name)
    min_safe_nodes = int(spec_payload["min_safe_workflow_nodes"])
    target_safe_nodes = spec_payload.get("target_safe_workflow_nodes")
    max_safe_nodes = spec_payload.get("max_safe_workflow_nodes")
    min_external_nodes = spec_payload.get("min_external_tool_call_nodes")
    if target_safe_nodes is not None and int(target_safe_nodes) < min_safe_nodes:
        raise ValueError("target_safe_workflow_nodes must be at least min_safe_workflow_nodes")
    if max_safe_nodes is not None and int(max_safe_nodes) < min_safe_nodes:
        raise ValueError("max_safe_workflow_nodes must be at least min_safe_workflow_nodes")
    if target_safe_nodes is not None and max_safe_nodes is not None and int(target_safe_nodes) > int(max_safe_nodes):
        raise ValueError("target_safe_workflow_nodes must be no greater than max_safe_workflow_nodes")
    if min_external_nodes is not None and max_safe_nodes is not None and int(min_external_nodes) > int(max_safe_nodes):
        raise ValueError("min_external_tool_call_nodes must be no greater than max_safe_workflow_nodes")
    return PlannerComplexitySpec(**spec_payload)

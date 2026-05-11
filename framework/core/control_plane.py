from __future__ import annotations

from dataclasses import dataclass
import fnmatch
import json
import os
import re
import shutil
from pathlib import Path
from typing import Any

from framework.models.specs import WorkspaceDiff


@dataclass(frozen=True, slots=True)
class ControlSurfaceSpec:
    kind: str
    vector: str
    path_template: str
    description: str
    injection_mode: str = "replace"


@dataclass(frozen=True, slots=True)
class ControlPlaneProvider:
    framework: str
    source_patterns: tuple[str, ...]
    allowed_patterns: tuple[str, ...]
    attacker_allowed_patterns: tuple[str, ...]
    attacker_vector_patterns: dict[str, tuple[str, ...]]
    default_attacker_vectors: tuple[str, ...]
    attacker_surfaces: tuple[ControlSurfaceSpec, ...]

    def collect_task_files(self, task_root: Path) -> list[tuple[Path, str]]:
        seen: set[str] = set()
        files: list[tuple[Path, str]] = []
        for pattern in self.source_patterns:
            if any(char in pattern for char in "*?["):
                candidates = sorted(task_root.glob(pattern))
            else:
                candidates = [task_root / pattern]
            for candidate in candidates:
                if not candidate.exists() or not candidate.is_file():
                    continue
                rel = candidate.relative_to(task_root).as_posix()
                if rel in seen or not self.is_allowed_relative_path(rel):
                    continue
                seen.add(rel)
                files.append((candidate, rel))
        return files

    def is_allowed_relative_path(self, relative_path: str) -> bool:
        normalized = relative_path.strip().lstrip("/")
        if not normalized:
            return False
        return any(fnmatch.fnmatch(normalized, pattern) for pattern in self.allowed_patterns)

    def attacker_patterns_for_vectors(self, enabled_vectors: tuple[str, ...] | None = None) -> tuple[str, ...]:
        if enabled_vectors is None:
            return self.attacker_allowed_patterns
        patterns: list[str] = []
        for vector in enabled_vectors:
            name = str(vector or "").strip().lower()
            if not name:
                continue
            patterns.extend(self.attacker_vector_patterns.get(name, ()))
        deduped: list[str] = []
        seen: set[str] = set()
        for pattern in patterns:
            if pattern in seen:
                continue
            seen.add(pattern)
            deduped.append(pattern)
        return tuple(deduped)

    def is_attacker_allowed_relative_path(self, relative_path: str, enabled_vectors: tuple[str, ...] | None = None) -> bool:
        normalized = relative_path.strip().lstrip("/")
        if not normalized:
            return False
        patterns = self.attacker_patterns_for_vectors(enabled_vectors)
        return any(fnmatch.fnmatch(normalized, pattern) for pattern in patterns)

    def attacker_surfaces_for_vectors(self, enabled_vectors: tuple[str, ...] | None = None) -> tuple[ControlSurfaceSpec, ...]:
        if enabled_vectors is None:
            allowed = {str(item).strip().lower() for item in self.default_attacker_vectors if str(item).strip()}
        else:
            allowed = {str(item).strip().lower() for item in enabled_vectors if str(item).strip()}
        return tuple(surface for surface in self.attacker_surfaces if surface.vector in allowed)


_PLACEHOLDER_PATTERN = re.compile(r"<[a-zA-Z][a-zA-Z0-9_-]*>")


def _path_template_to_source_patterns(path_template: str) -> list[str]:
    """Convert a path_template into source file globs.
    Paths with <placeholder> match all files under the parent directory.
    ' or '-separated templates are split and each part is handled individually.
    """
    template = str(path_template or "").strip()
    if not template:
        return []
    if " or " in template:
        patterns: list[str] = []
        for part in (p.strip() for p in template.split(" or ")):
            patterns.extend(_path_template_to_source_patterns(part))
        return patterns
    m = _PLACEHOLDER_PATTERN.search(template)
    if m:
        prefix = template[:m.start()].rstrip("/")
        return [f"{prefix}/**/*"] if prefix else ["**/*"]
    return [template]


def _path_template_to_allowed_pattern(path_template: str) -> list[str]:
    """Convert a path_template into allowed (directory-level) patterns."""
    template = str(path_template or "").strip()
    if not template:
        return []
    if " or " in template:
        patterns: list[str] = []
        for part in (p.strip() for p in template.split(" or ")):
            patterns.extend(_path_template_to_allowed_pattern(part))
        return patterns
    m = _PLACEHOLDER_PATTERN.search(template)
    if m:
        prefix = template[:m.start()].rstrip("/")
        return [f"{prefix}/**"] if prefix else ["**"]
    return [template]


def _path_template_to_allowed_pattern(path_template: str) -> list[str]:
    """Convert a path_template into allowed (directory-level) patterns.

    Examples:
        .opencode/skills/<skill-name>/SKILL.md  ->  .opencode/skills/**
        CLAUDE.md                                ->  CLAUDE.md
    """
    template = str(path_template or "").strip()
    if not template:
        return []
    if " or " in template:
        parts = [p.strip() for p in template.split(" or ")]
        patterns: list[str] = []
        for part in parts:
            patterns.extend(_path_template_to_allowed_pattern(part))
        return patterns
    m = _PLACEHOLDER_PATTERN.search(template)
    if m:
        prefix = template[:m.start()].rstrip("/")
        return [f"{prefix}/**"] if prefix else ["**"]
    return [template]


def _path_template_to_vector_pattern(path_template: str) -> list[str]:
    """Convert a path_template into a vector glob pattern."""
    return _path_template_to_allowed_pattern(path_template)


def build_provider_from_attack_surfaces(
    framework: str,
    surfaces: list[dict[str, str]],
) -> ControlPlaneProvider:
    """Build a ControlPlaneProvider from target-config attack_surfaces.

    Each surface dict must have keys: vector, kind, path_template, description.
    All patterns are auto-derived from the path_template.
    """
    framework = str(framework or "").strip().lower()
    specs: list[ControlSurfaceSpec] = []
    vectors: list[str] = []
    source_patterns: list[str] = []
    allowed_patterns: list[str] = []
    attacker_allowed_patterns: list[str] = []
    attacker_vector_patterns: dict[str, tuple[str, ...]] = {}

    for item in surfaces:
        vector = str(item.get("vector", "") or "").strip().lower()
        kind = str(item.get("kind", "") or "").strip().lower()
        path_template = str(item.get("path_template", "") or "").strip()
        description = str(item.get("description", "") or "").strip()
        injection_mode = str(item.get("injection_mode", "") or "").strip().lower()
        if injection_mode not in {"replace", "append", "merge"}:
            injection_mode = "replace"
        if not vector or not kind or not path_template:
            continue
        specs.append(ControlSurfaceSpec(kind=kind, vector=vector, path_template=path_template, description=description, injection_mode=injection_mode))
        vectors.append(vector)

        src_pats = _path_template_to_source_patterns(path_template)
        allowed_pats = _path_template_to_allowed_pattern(path_template)
        vec_pats = _path_template_to_vector_pattern(path_template)

        for p in src_pats:
            if p not in source_patterns:
                source_patterns.append(p)
        for p in allowed_pats:
            if p not in allowed_patterns:
                allowed_patterns.append(p)
        for p in vec_pats:
            if p not in attacker_allowed_patterns:
                attacker_allowed_patterns.append(p)
        attacker_vector_patterns[vector] = tuple(vec_pats)

    return ControlPlaneProvider(
        framework=framework,
        source_patterns=tuple(source_patterns),
        allowed_patterns=tuple(allowed_patterns),
        attacker_allowed_patterns=tuple(attacker_allowed_patterns),
        attacker_vector_patterns=attacker_vector_patterns,
        default_attacker_vectors=tuple(vectors),
        attacker_surfaces=tuple(specs),
    )


def derive_probe_paths_from_attack_surfaces(surfaces: list[dict[str, str]]) -> list[str]:
    """Derive /workspace/-prefixed probe paths from attack_surfaces path_templates.

    Extracts directory prefixes so the target prompt tells the agent exactly
    which paths to inspect — keeping them in sync with attack_surfaces.

    Examples:
        .hermes/skills/<skill-name>/SKILL.md  →  /workspace/.hermes/skills/
        CLAUDE.md                              →  /workspace/CLAUDE.md
        GEMINI.md or <subdir>/GEMINI.md        →  /workspace/GEMINI.md
    """
    paths: list[str] = []

    for item in surfaces:
        template = str(item.get("path_template", "") or "").strip()
        if not template:
            continue
        # Split on ' or ' and handle each part
        for part in (p.strip() for p in template.split(" or ")):
            m = _PLACEHOLDER_PATTERN.search(part)
            if m:
                # Directory path: prefix before <placeholder>
                prefix = part[:m.start()].rstrip("/")
                if prefix:
                    paths.append(f"/workspace/{prefix}/")
                # Skip empty prefix (e.g. <subdir>/GEMINI.md → ** which is too broad)
            else:
                # File path: use as-is
                paths.append(f"/workspace/{part}")

    # Deduplicate, sort, keep order stable
    seen: set[str] = set()
    result: list[str] = []
    for p in paths:
        if p not in seen:
            seen.add(p)
            result.append(p)
    result.sort()
    return result


class ControlPlaneProviderRegistry:
    """Registry for framework-native control plane providers."""

    def __init__(self) -> None:
        self._providers: dict[str, ControlPlaneProvider] = {}

    def register(self, name: str, provider: ControlPlaneProvider) -> None:
        key = str(name or "").strip().lower()
        if not key:
            raise ValueError("control plane provider name is required")
        self._providers[key] = provider

    def get(self, name: str) -> ControlPlaneProvider:
        key = str(name or "").strip().lower()
        if key not in self._providers:
            raise KeyError(f"Unknown control plane provider: {name}")
        return self._providers[key]

    def get_optional(self, name: str) -> ControlPlaneProvider | None:
        key = str(name or "").strip().lower()
        if not key:
            return None
        return self._providers.get(key)

    def names(self) -> tuple[str, ...]:
        return tuple(sorted(self._providers.keys()))


def create_default_control_plane_provider_registry() -> ControlPlaneProviderRegistry:
    """Creates an empty registry. Providers are built from target config attack_surfaces at runtime."""
    return ControlPlaneProviderRegistry()


_DEFAULT_CONTROL_PLANE_PROVIDER_REGISTRY = create_default_control_plane_provider_registry()


def register_control_plane_provider(name: str, provider: ControlPlaneProvider) -> None:
    _DEFAULT_CONTROL_PLANE_PROVIDER_REGISTRY.register(name, provider)


def _normalize_string_tuple(values: Any) -> tuple[str, ...]:
    if values is None:
        return ()
    if isinstance(values, (str, bytes)):
        text = str(values).strip()
        return (text,) if text else ()
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


def _normalize_vector_patterns(values: Any) -> dict[str, tuple[str, ...]]:
    if not isinstance(values, dict):
        return {}
    normalized: dict[str, tuple[str, ...]] = {}
    for key, patterns in values.items():
        name = str(key or "").strip().lower()
        if not name:
            continue
        normalized_patterns = _normalize_string_tuple(patterns)
        if normalized_patterns:
            normalized[name] = normalized_patterns
    return normalized


def _normalize_surface_specs(values: Any) -> tuple[ControlSurfaceSpec, ...]:
    if not isinstance(values, list):
        return ()
    surfaces: list[ControlSurfaceSpec] = []
    for item in values:
        if not isinstance(item, dict):
            continue
        kind = str(item.get("kind") or "").strip().lower()
        vector = str(item.get("vector") or "").strip().lower()
        path_template = str(item.get("path_template") or "").strip()
        description = str(item.get("description") or "").strip()
        if not kind or not vector or not path_template:
            continue
        surfaces.append(
            ControlSurfaceSpec(
                kind=kind,
                vector=vector,
                path_template=path_template,
                description=description,
            )
        )
    return tuple(surfaces)


def _provider_from_config(
    framework: str,
    config: dict[str, Any],
    registry: ControlPlaneProviderRegistry,
) -> ControlPlaneProvider | None:
    if not config:
        return registry.get_optional(framework)
    if config.get("enabled") is False:
        return None

    base_name = str(config.get("provider") or framework or "").strip().lower()
    base_provider = registry.get_optional(base_name) if base_name else None
    if not any(
        key in config
        for key in (
            "framework",
            "source_patterns",
            "allowed_patterns",
            "attacker_allowed_patterns",
            "attacker_vector_patterns",
            "default_attacker_vectors",
            "attacker_surfaces",
        )
    ):
        return base_provider

    return ControlPlaneProvider(
        framework=str(
            config.get("framework")
            or (base_provider.framework if base_provider else "")
            or base_name
            or framework
        ).strip().lower(),
        source_patterns=_normalize_string_tuple(config.get("source_patterns")) or (
            base_provider.source_patterns if base_provider else ()
        ),
        allowed_patterns=_normalize_string_tuple(config.get("allowed_patterns")) or (
            base_provider.allowed_patterns if base_provider else ()
        ),
        attacker_allowed_patterns=_normalize_string_tuple(config.get("attacker_allowed_patterns")) or (
            base_provider.attacker_allowed_patterns if base_provider else ()
        ),
        attacker_vector_patterns=_normalize_vector_patterns(config.get("attacker_vector_patterns")) or (
            dict(base_provider.attacker_vector_patterns) if base_provider else {}
        ),
        default_attacker_vectors=_normalize_string_tuple(config.get("default_attacker_vectors")) or (
            base_provider.default_attacker_vectors if base_provider else ()
        ),
        attacker_surfaces=_normalize_surface_specs(config.get("attacker_surfaces")) or (
            base_provider.attacker_surfaces if base_provider else ()
        ),
    )


def create_control_plane_provider(
    framework: str,
    registry: ControlPlaneProviderRegistry | None = None,
    config: str | dict[str, Any] | None = None,
) -> ControlPlaneProvider | None:
    active_registry = registry or _DEFAULT_CONTROL_PLANE_PROVIDER_REGISTRY
    if isinstance(config, str):
        provider_name = str(config).strip().lower()
        if provider_name:
            return active_registry.get_optional(provider_name)
    if isinstance(config, dict):
        return _provider_from_config(framework, config, active_registry)
    return active_registry.get_optional(framework)


class ControlPlaneManager:
    MANIFEST_FILE_NAME = ".openart-target-control-manifest.json"

    def __init__(self, root_dir: str, source_root: str, provider: ControlPlaneProvider | None) -> None:
        self.root_dir = Path(root_dir)
        self.source_root = Path(source_root)
        self.provider = provider

    def enabled(self) -> bool:
        return self.provider is not None

    def ensure_layout(self) -> None:
        self.base_dir().mkdir(parents=True, exist_ok=True)
        self.final_dir().mkdir(parents=True, exist_ok=True)
        self.attackers_dir().mkdir(parents=True, exist_ok=True)
        self.snapshots_dir().mkdir(parents=True, exist_ok=True)

    def base_dir(self) -> Path:
        return self.root_dir / "base"

    def final_dir(self) -> Path:
        return self.root_dir / "final"

    def attackers_dir(self) -> Path:
        return self.root_dir / "attackers"

    def snapshots_dir(self) -> Path:
        return self.root_dir / "snapshots"

    def manifest_path(self) -> Path:
        return self.base_dir() / self.MANIFEST_FILE_NAME

    def final_allowed_file_entries(self) -> list[tuple[Path, str]]:
        if not self.enabled() or not self.final_dir().exists():
            return []
        files: list[tuple[Path, str]] = []
        for path in sorted(self.final_dir().rglob("*")):
            if not path.is_file():
                continue
            rel = path.relative_to(self.final_dir()).as_posix()
            if not self.provider.is_allowed_relative_path(rel):
                continue
            files.append((path, rel))
        return files

    def attacker_output_dir(self, attacker_name: str, phase: str, index: int = 1) -> Path:
        return self.attackers_dir() / attacker_name / f"{phase}_{index:03d}"

    def ensure_attacker_output(self, attacker_name: str, phase: str, index: int = 1) -> str:
        path = self.attacker_output_dir(attacker_name, phase, index)
        self._clear_dir_contents(path)
        return str(path)

    def build_base(self) -> list[str]:
        self.ensure_layout()
        base_dir = self.base_dir()
        self._clear_dir_contents(base_dir)
        if not self.enabled():
            return []
        copied: list[str] = []
        for source_path, relative_path in self.provider.collect_task_files(self.source_root):
            target_path = base_dir / relative_path
            target_path.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source_path, target_path)
            copied.append(relative_path)
        self._write_attacker_manifest(base_dir, copied)
        self._write_snapshot(self.snapshots_dir() / "base.json", base_dir, tag="base")
        return copied

    def use_base_as_final(self) -> WorkspaceDiff:
        self.ensure_layout()
        diff = self._diff_dirs(self.base_dir(), self.final_dir())
        self._clear_dir_contents(self.final_dir())
        self._copy_dir_contents(self.base_dir(), self.final_dir())
        self._write_snapshot(self.snapshots_dir() / "final.json", self.final_dir(), tag="final")
        return diff

    def copy_base_to_attacker_output(self, attacker_name: str, phase: str, index: int = 1) -> str:
        output_dir = self.attacker_output_dir(attacker_name, phase, index)
        self._clear_dir_contents(output_dir)
        self._copy_dir_contents(self.base_dir(), output_dir)
        return str(output_dir)

    def finalize_from_attacker_output(
        self,
        attacker_name: str,
        phase: str,
        index: int = 1,
        allowed_vectors: tuple[str, ...] | None = None,
    ) -> tuple[WorkspaceDiff, list[str]]:
        self.ensure_layout()
        output_dir = self.attacker_output_dir(attacker_name, phase, index)
        final_dir = self.final_dir()
        ignored = self._disallowed_relative_paths(output_dir, attacker=True, allowed_vectors=allowed_vectors)
        diff = self._diff_dirs(self.base_dir(), output_dir, filter_allowed=True, attacker=True, allowed_vectors=allowed_vectors)
        self._clear_dir_contents(final_dir)
        self._copy_dir_contents(self.base_dir(), final_dir)
        self._delete_allowed_files(final_dir, attacker=True, allowed_vectors=allowed_vectors)
        self._copy_allowed_dir_contents(output_dir, final_dir, attacker=True, allowed_vectors=allowed_vectors)
        self._handle_append_files(output_dir, final_dir, diff.added, allowed_vectors)
        self._write_snapshot(self.snapshots_dir() / "final.json", final_dir, tag="final")
        return diff, ignored

    def _handle_append_files(self, output_dir: Path, final_dir: Path, added_paths: list[str], allowed_vectors: tuple[str, ...] | None) -> None:
        if not self.enabled() or self.provider is None:
            return
        append_vectors: set[str] = set()
        for surface in self.provider.attacker_surfaces:
            if surface.injection_mode in {"append", "merge"}:
                append_vectors.add(surface.vector)
        if not append_vectors:
            return
        allowed = set(allowed_vectors) if allowed_vectors else set()
        for added in added_paths:
            output_file = output_dir / added
            if not output_file.is_file():
                continue
            for surface in self.provider.attacker_surfaces:
                if surface.vector not in allowed and allowed:
                    continue
                if surface.injection_mode not in {"append", "merge"}:
                    continue
                pattern = _path_template_to_vector_pattern(surface.path_template)
                if any(fnmatch.fnmatch(added, p) for p in pattern):
                    final_file = final_dir / added
                    existing = final_file.read_text(encoding="utf-8") if final_file.is_file() else ""
                    appended = output_file.read_text(encoding="utf-8")
                    final_file.write_text(existing + "\n" + appended, encoding="utf-8")
                    break

    def materialize_final_to_workspace(self, workspace_dir: str) -> WorkspaceDiff:
        shared_root = Path(workspace_dir)
        shared_root.mkdir(parents=True, exist_ok=True)
        diff = self._diff_dirs(shared_root, self.final_dir(), filter_allowed=True)
        self._delete_allowed_files(shared_root)
        self._copy_allowed_dir_contents(self.final_dir(), shared_root)
        self._materialize_home_files(shared_root)
        self._write_snapshot(self.snapshots_dir() / "materialized.json", shared_root, tag="materialized")
        return diff

    def _materialize_home_files(self, workspace_root: Path) -> None:
        home_dir = os.environ.get("HOME", "")
        if not home_dir or not self.enabled():
            return
        home_prefix = "HOME/"
        for path in sorted(workspace_root.rglob("*")):
            if not path.is_file():
                continue
            rel = path.relative_to(workspace_root).as_posix()
            if not rel.startswith(home_prefix):
                continue
            rel_path = rel[len(home_prefix):]
            dest = Path(home_dir) / rel_path
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(path, dest)
            path.unlink(missing_ok=True)
        for path in sorted(workspace_root.rglob("*"), reverse=True):
            if path.is_dir() and path.relative_to(workspace_root).as_posix() == "HOME":
                try:
                    shutil.rmtree(path)
                except OSError:
                    pass

    def _disallowed_relative_paths(self, root: Path, *, attacker: bool = False, allowed_vectors: tuple[str, ...] | None = None) -> list[str]:
        if not self.enabled() or not root.exists():
            return []
        disallowed: list[str] = []
        for path in sorted(root.rglob("*")):
            if not path.is_file():
                continue
            rel = path.relative_to(root).as_posix()
            allowed = self.provider.is_attacker_allowed_relative_path(rel, allowed_vectors) if attacker else self.provider.is_allowed_relative_path(rel)
            if not allowed:
                disallowed.append(rel)
        return disallowed

    def _delete_allowed_files(self, root: Path, *, attacker: bool = False, allowed_vectors: tuple[str, ...] | None = None) -> None:
        if not self.enabled() or not root.exists():
            return
        for path in sorted(root.rglob("*"), reverse=True):
            if not path.is_file():
                continue
            rel = path.relative_to(root).as_posix()
            allowed = self.provider.is_attacker_allowed_relative_path(rel, allowed_vectors) if attacker else self.provider.is_allowed_relative_path(rel)
            if allowed:
                path.unlink(missing_ok=True)
        for path in sorted(root.rglob("*"), reverse=True):
            if path.is_dir():
                try:
                    path.rmdir()
                except OSError:
                    continue

    def _clear_dir_contents(self, path: Path) -> None:
        if path.exists():
            shutil.rmtree(path)
        path.mkdir(parents=True, exist_ok=True)

    def _copy_dir_contents(self, src: Path, dst: Path) -> None:
        if not src.exists():
            return
        for path in sorted(src.rglob("*")):
            rel = path.relative_to(src)
            target = dst / rel
            if path.is_dir():
                target.mkdir(parents=True, exist_ok=True)
                continue
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(path, target)

    def _copy_allowed_dir_contents(self, src: Path, dst: Path, *, attacker: bool = False, allowed_vectors: tuple[str, ...] | None = None) -> None:
        if not src.exists() or not self.enabled():
            return
        for path in sorted(src.rglob("*")):
            if not path.is_file():
                continue
            rel = path.relative_to(src).as_posix()
            allowed = self.provider.is_attacker_allowed_relative_path(rel, allowed_vectors) if attacker else self.provider.is_allowed_relative_path(rel)
            if not allowed:
                continue
            target = dst / rel
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(path, target)

    def _diff_dirs(self, left: Path, right: Path, *, filter_allowed: bool = False, attacker: bool = False, allowed_vectors: tuple[str, ...] | None = None) -> WorkspaceDiff:
        left_files = self._file_set(left, filter_allowed=filter_allowed, attacker=attacker, allowed_vectors=allowed_vectors)
        right_files = self._file_set(right, filter_allowed=filter_allowed, attacker=attacker, allowed_vectors=allowed_vectors)
        added = sorted(right_files - left_files)
        deleted = sorted(left_files - right_files)
        modified: list[str] = []
        for rel in sorted(left_files & right_files):
            if not self._files_equal(left / rel, right / rel):
                modified.append(rel.as_posix())
        return WorkspaceDiff(
            added=[path.as_posix() for path in added],
            modified=modified,
            deleted=[path.as_posix() for path in deleted],
        )

    def _file_set(self, root: Path, *, filter_allowed: bool = False, attacker: bool = False, allowed_vectors: tuple[str, ...] | None = None) -> set[Path]:
        if not root.exists():
            return set()
        result: set[Path] = set()
        for path in root.rglob("*"):
            if not path.is_file():
                continue
            rel = path.relative_to(root)
            if filter_allowed and self.enabled():
                allowed = self.provider.is_attacker_allowed_relative_path(rel.as_posix(), allowed_vectors) if attacker else self.provider.is_allowed_relative_path(rel.as_posix())
                if not allowed:
                    continue
            result.add(rel)
        return result

    def _files_equal(self, left: Path, right: Path) -> bool:
        return left.read_bytes() == right.read_bytes()

    def _write_snapshot(self, path: Path, root: Path, *, tag: str) -> None:
        files = []
        for file_path in sorted(root.rglob("*")):
            if not file_path.is_file():
                continue
            rel = file_path.relative_to(root).as_posix()
            if self.enabled() and not self.provider.is_allowed_relative_path(rel):
                continue
            files.append({"path": rel, "size": file_path.stat().st_size})
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps(
                {
                    "framework": self.provider.framework if self.provider else "",
                    "tag": tag,
                    "root": str(root),
                    "files": files,
                },
                ensure_ascii=False,
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )

    def _write_attacker_manifest(self, base_dir: Path, discovered_files: list[str]) -> None:
        if not self.enabled() or self.provider is None:
            return
        payload = {
            "framework": self.provider.framework,
            "allowed_patterns": list(self.provider.allowed_patterns),
            "default_attacker_vectors": list(self.provider.default_attacker_vectors),
            "available_attacker_vectors": {
                name: list(patterns) for name, patterns in sorted(self.provider.attacker_vector_patterns.items())
            },
            "discovered_files": discovered_files,
            "attack_surfaces": [
                {
                    "kind": surface.kind,
                    "vector": surface.vector,
                    "default_enabled": surface.vector in self.provider.default_attacker_vectors,
                    "path_template": surface.path_template,
                    "description": surface.description,
                    "injection_mode": surface.injection_mode,
                }
                for surface in self.provider.attacker_surfaces
            ],
        }
        manifest_path = base_dir / self.MANIFEST_FILE_NAME
        manifest_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


__all__ = [
    "ControlPlaneManager",
    "ControlPlaneProvider",
    "ControlPlaneProviderRegistry",
    "ControlSurfaceSpec",
    "create_control_plane_provider",
    "create_default_control_plane_provider_registry",
    "register_control_plane_provider",
]

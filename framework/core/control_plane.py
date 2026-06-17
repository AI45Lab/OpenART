from __future__ import annotations

from dataclasses import dataclass
import fnmatch
import json
import re
import shutil
from pathlib import Path
from typing import Any

from framework.core.visibility_policy import FRAMEWORK_VISIBILITY_POLICY, VisibilityPolicy
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
        if _is_internal_target_control_path(normalized):
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
        if _is_internal_target_control_path(normalized):
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
_SKILL_FRONTMATTER_PATTERN = re.compile(r"\A---\s*\n(.*?)\n---\s*\n?(.*)\Z", re.DOTALL)


def _is_internal_target_control_path(relative_path: str, visibility_policy: VisibilityPolicy | None = None) -> bool:
    return (visibility_policy or FRAMEWORK_VISIBILITY_POLICY).matches_control_exclude(relative_path)


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


def _split_path_template(path_template: str) -> list[str]:
    return [part.strip() for part in str(path_template or "").split(" or ") if part.strip()]


def _parse_skill_markdown(text: str) -> tuple[dict[str, Any], str, str | None]:
    match = _SKILL_FRONTMATTER_PATTERN.match(text or "")
    if not match:
        return {}, "", "missing YAML frontmatter"
    raw_frontmatter, body = match.group(1), match.group(2)
    try:
        import yaml

        loaded = yaml.safe_load(raw_frontmatter)
    except Exception as exc:
        return {}, body, f"invalid YAML frontmatter: {exc}"
    if not isinstance(loaded, dict):
        return {}, body, "YAML frontmatter must be a mapping"
    return loaded, body, None


def _has_activation_cue(text: str, *, skill_name: str, skill_dir: str) -> bool:
    lower = str(text or "").lower()
    name = str(skill_name or "").strip().lower()
    path = str(skill_dir or "").strip().lower()
    mentions_skill = bool(
        (name and name in lower)
        or (path and path in lower)
        or "skill.md" in lower
        or "tool_wrapper.py" in lower
        or "wrapper" in lower
    )
    if not mentions_skill:
        return False
    cue_terms = (
        "use this skill",
        "when to use",
        "trigger",
        "activate",
        "use the skill",
        "load the skill",
        "inspect and use",
        "wrapper",
    )
    return any(term in lower for term in cue_terms)


def _skill_dir_for_surface_relative_path(surface: ControlSurfaceSpec, relative_path: str) -> str | None:
    rel = relative_path.strip().lstrip("/")
    for template in _split_path_template(surface.path_template):
        marker = _PLACEHOLDER_PATTERN.search(template)
        if not marker or marker.group(0) != "<skill-name>":
            continue
        prefix = template[: marker.start()].strip("/")
        if prefix:
            prefix_with_slash = f"{prefix}/"
            if not rel.startswith(prefix_with_slash):
                continue
            remainder = rel[len(prefix_with_slash):]
        else:
            remainder = rel
        skill_name = remainder.split("/", 1)[0]
        if not skill_name:
            continue
        skill_dir = f"{prefix}/{skill_name}" if prefix else skill_name
        if rel == skill_dir or rel.startswith(f"{skill_dir}/"):
            return skill_dir
    return None


def _instruction_path_for_surface(surface: ControlSurfaceSpec) -> str | None:
    for template in _split_path_template(surface.path_template):
        if "<" not in template and ">" not in template:
            return template.strip().lstrip("/")
        if template.startswith("<subdir>/"):
            return template[len("<subdir>/"):].strip().lstrip("/")
    return None


def _read_enabled_instruction_files_for_provider(
    output_dir: Path,
    provider: ControlPlaneProvider | None,
    allowed_vectors: set[str],
    visibility_policy: VisibilityPolicy | None,
) -> list[dict[str, str]]:
    if provider is None:
        return []
    result: list[dict[str, str]] = []
    for surface in provider.attacker_surfaces:
        if surface.kind != "instruction":
            continue
        if allowed_vectors and surface.vector not in allowed_vectors:
            continue
        rel = _instruction_path_for_surface(surface)
        if not rel or _is_internal_target_control_path(rel, visibility_policy):
            continue
        path = output_dir / rel
        if not path.is_file():
            continue
        try:
            content = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            continue
        result.append({"path": rel, "content": content})
    return result


def _suggest_skill_fix(reasons: list[str], *, skill_dir: str, skill_file: str) -> str:
    fixes: list[str] = []
    reason_text = "\n".join(reasons).lower()
    if "utf-8" in reason_text:
        fixes.append(f"Save {skill_file} as UTF-8 text.")
    if "frontmatter" in reason_text or "name" in reason_text or "description" in reason_text or "body" in reason_text:
        fixes.append(
            f"Rewrite {skill_file} with valid YAML frontmatter containing non-empty "
            "`name` and `description`, followed by a non-empty Markdown body."
        )
    if "activation cue" in reason_text:
        fixes.append(
            f"Add a clear activation cue such as `Use this skill when ...` to {skill_file}, "
            "or to an enabled companion instruction file, and mention the skill path "
            f"`{skill_dir}` plus `scripts/tool_wrapper.py`."
        )
    if "missing skill.md" in reason_text:
        fixes.append(f"Create {skill_file} with valid frontmatter, body text, and an activation cue.")
    if not fixes:
        fixes.append(f"Regenerate or rewrite the files under {skill_dir} using the listed reasons.")
    return " ".join(fixes)


def validate_attacker_skill_folders(
    output_dir: Path,
    provider: ControlPlaneProvider | None,
    *,
    allowed_vectors: tuple[str, ...] | None = None,
    visibility_policy: VisibilityPolicy | None = None,
    metadata: dict[str, Any] | None = None,
) -> tuple[set[str], dict[str, Any]]:
    payload: dict[str, Any] = {
        **dict(metadata or {}),
        "validated": [],
        "rejected": [],
    }
    blocked: set[str] = set()
    if provider is None or not output_dir.exists():
        return blocked, payload

    allowed = {str(item or "").strip().lower() for item in allowed_vectors or () if str(item or "").strip()}
    skill_surfaces = [
        surface
        for surface in provider.attacker_surfaces
        if surface.kind == "skill" and (not allowed or surface.vector in allowed)
    ]
    if not skill_surfaces:
        return blocked, payload

    files_by_skill_dir: dict[str, list[str]] = {}
    surface_by_skill_dir: dict[str, ControlSurfaceSpec] = {}
    for path in sorted(output_dir.rglob("*")):
        if not path.is_file():
            continue
        rel = path.relative_to(output_dir).as_posix()
        if _is_internal_target_control_path(rel, visibility_policy):
            continue
        for surface in skill_surfaces:
            skill_dir = _skill_dir_for_surface_relative_path(surface, rel)
            if not skill_dir:
                continue
            files_by_skill_dir.setdefault(skill_dir, []).append(rel)
            surface_by_skill_dir.setdefault(skill_dir, surface)
            break

    if not files_by_skill_dir:
        return blocked, payload

    instruction_texts = _read_enabled_instruction_files_for_provider(output_dir, provider, allowed, visibility_policy)
    for skill_dir in sorted(files_by_skill_dir):
        files = sorted(files_by_skill_dir[skill_dir])
        surface = surface_by_skill_dir[skill_dir]
        reasons: list[str] = []
        skill_md_rel = f"{skill_dir}/SKILL.md"
        skill_md_path = output_dir / skill_md_rel
        frontmatter: dict[str, Any] = {}
        body = ""
        skill_name = Path(skill_dir).name
        if not skill_md_path.is_file():
            reasons.append("missing SKILL.md")
        else:
            try:
                text = skill_md_path.read_text(encoding="utf-8")
            except UnicodeDecodeError:
                text = ""
                reasons.append("SKILL.md must be UTF-8 text")
            frontmatter, body, parse_error = _parse_skill_markdown(text)
            if parse_error:
                reasons.append(parse_error)
            name = str(frontmatter.get("name", "") or "").strip()
            description = str(frontmatter.get("description", "") or "").strip()
            if not name:
                reasons.append("SKILL.md frontmatter requires non-empty name")
            else:
                skill_name = name
            if not description:
                reasons.append("SKILL.md frontmatter requires non-empty description")
            if not body.strip():
                reasons.append("SKILL.md requires non-empty Markdown body")
            activation_found = _has_activation_cue(text, skill_name=skill_name, skill_dir=skill_dir)
            if not activation_found:
                activation_found = any(
                    _has_activation_cue(item["content"], skill_name=skill_name, skill_dir=skill_dir)
                    for item in instruction_texts
                )
            if not activation_found:
                reasons.append("missing activation cue in SKILL.md or companion instruction file")

        item = {
            "skill_dir": skill_dir,
            "skill_file": skill_md_rel,
            "vector": surface.vector,
            "files": files,
        }
        if reasons:
            item["reasons"] = reasons
            item["suggested_fix"] = _suggest_skill_fix(reasons, skill_dir=skill_dir, skill_file=skill_md_rel)
            payload["rejected"].append(item)
            blocked.update(files)
        else:
            payload["validated"].append(item)

    return blocked, payload


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


def _load_target_configs_and_register_providers(registry: ControlPlaneProviderRegistry) -> None:
    """Load target YAML configs from configs/target-configs and register providers."""
    configs_dir = Path(__file__).resolve().parents[2] / "configs" / "target-configs"
    if not configs_dir.is_dir():
        return
    try:
        import yaml
    except ImportError:
        return
    for config_file in sorted(configs_dir.glob("target*.yaml")):
        try:
            with open(config_file, "r", encoding="utf-8") as f:
                data = yaml.safe_load(f)
        except Exception:
            continue
        if not isinstance(data, dict):
            continue
        target = data.get("target")
        if not isinstance(target, dict):
            continue
        attack_surfaces = target.get("attack_surfaces")
        if not isinstance(attack_surfaces, list) or not attack_surfaces:
            continue
        try:
            from framework.core.target_adapters import surface_family_from_target_config
        except Exception:
            provider_family = str(target.get("framework") or "").strip().lower()
        else:
            provider_family = surface_family_from_target_config(target)
        provider_family = str(provider_family or "").strip().lower()
        if not provider_family:
            continue
        provider = build_provider_from_attack_surfaces(provider_family, attack_surfaces)
        if provider and provider_family not in {name for name in registry.names()}:
            registry.register(provider_family, provider)


def create_default_control_plane_provider_registry() -> ControlPlaneProviderRegistry:
    """Creates a registry populated from target config attack_surfaces."""
    registry = ControlPlaneProviderRegistry()
    _load_target_configs_and_register_providers(registry)
    return registry


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
        injection_mode = str(item.get("injection_mode") or "").strip().lower()
        if injection_mode not in {"replace", "append", "merge"}:
            injection_mode = "replace"
        if not kind or not vector or not path_template:
            continue
        surfaces.append(
            ControlSurfaceSpec(
                kind=kind,
                vector=vector,
                path_template=path_template,
                description=description,
                injection_mode=injection_mode,
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
        visibility_policy: VisibilityPolicy | None = None,
    ) -> tuple[WorkspaceDiff, list[str]]:
        self.ensure_layout()
        output_dir = self.attacker_output_dir(attacker_name, phase, index)
        final_dir = self.final_dir()
        ignored = self._disallowed_relative_paths(
            output_dir,
            attacker=True,
            allowed_vectors=allowed_vectors,
            visibility_policy=visibility_policy,
        )
        blocked_paths, validation = self._validate_attacker_skill_folders(
            output_dir,
            attacker_name=attacker_name,
            phase=phase,
            index=index,
            allowed_vectors=allowed_vectors,
            visibility_policy=visibility_policy,
        )
        self._clear_dir_contents(final_dir)
        self._copy_dir_contents(self.base_dir(), final_dir)
        self._delete_allowed_files(
            final_dir,
            attacker=True,
            allowed_vectors=allowed_vectors,
            skip_append_mode=True,
            visibility_policy=visibility_policy,
            blocked_relative_paths=blocked_paths,
        )
        self._copy_allowed_dir_contents(
            output_dir,
            final_dir,
            attacker=True,
            allowed_vectors=allowed_vectors,
            skip_append_mode=True,
            visibility_policy=visibility_policy,
            blocked_relative_paths=blocked_paths,
        )
        self._handle_append_files(output_dir, final_dir, allowed_vectors, visibility_policy=visibility_policy, blocked_relative_paths=blocked_paths)
        self._write_snapshot(self.snapshots_dir() / "final.json", final_dir, tag="final")
        diff = self._diff_dirs(
            self.base_dir(),
            final_dir,
            filter_allowed=True,
            visibility_policy=visibility_policy,
        )
        if validation.get("rejected"):
            ignored = sorted(set(ignored) | blocked_paths)
        return diff, ignored

    def _handle_append_files(
        self,
        output_dir: Path,
        final_dir: Path,
        allowed_vectors: tuple[str, ...] | None,
        *,
        visibility_policy: VisibilityPolicy | None = None,
        blocked_relative_paths: set[str] | None = None,
    ) -> None:
        if not self.enabled() or self.provider is None:
            return
        allowed = set(allowed_vectors) if allowed_vectors else set()
        blocked = blocked_relative_paths or set()
        for output_file in sorted(output_dir.rglob("*")):
            if not output_file.is_file():
                continue
            rel = output_file.relative_to(output_dir).as_posix()
            if rel in blocked:
                continue
            if _is_internal_target_control_path(rel, visibility_policy):
                continue
            for surface in self.provider.attacker_surfaces:
                if surface.vector not in allowed and allowed:
                    continue
                if surface.injection_mode not in {"append", "merge"}:
                    continue
                if self._surface_matches_relative_path(surface, rel):
                    final_file = final_dir / rel
                    try:
                        existing = final_file.read_text(encoding="utf-8") if final_file.is_file() else ""
                        appended = output_file.read_text(encoding="utf-8")
                        final_file.parent.mkdir(parents=True, exist_ok=True)
                        if existing and appended:
                            final_file.write_text(existing.rstrip("\n") + "\n" + appended, encoding="utf-8")
                        elif appended:
                            final_file.write_text(appended, encoding="utf-8")
                    except UnicodeDecodeError:
                        pass
                    break

    def materialize_final_to_workspace(self, workspace_dir: str) -> WorkspaceDiff:
        shared_root = Path(workspace_dir)
        shared_root.mkdir(parents=True, exist_ok=True)
        diff = self._diff_dirs(shared_root, self.final_dir(), filter_allowed=True)
        self._delete_allowed_files(shared_root)
        self._copy_allowed_dir_contents(self.final_dir(), shared_root)
        self._write_snapshot(self.snapshots_dir() / "materialized.json", shared_root, tag="materialized")
        self._materialize_home_files(shared_root)
        return diff

    def _materialize_home_files(self, workspace_root: Path) -> None:
        if not self.enabled():
            return
        materialized_home = workspace_root / ".openart" / "materialized_home"
        home_prefix = "HOME/"
        for path in sorted(workspace_root.rglob("*")):
            if not path.is_file():
                continue
            rel = path.relative_to(workspace_root).as_posix()
            if not rel.startswith(home_prefix):
                continue
            rel_path = rel[len(home_prefix):]
            dest = materialized_home / rel_path
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(path, dest)
            path.unlink(missing_ok=True)
        for path in sorted(workspace_root.rglob("*"), reverse=True):
            if path.is_dir() and path.relative_to(workspace_root).as_posix() == "HOME":
                try:
                    shutil.rmtree(path)
                except OSError:
                    pass

    def _disallowed_relative_paths(
        self,
        root: Path,
        *,
        attacker: bool = False,
        allowed_vectors: tuple[str, ...] | None = None,
        visibility_policy: VisibilityPolicy | None = None,
    ) -> list[str]:
        if not self.enabled() or not root.exists():
            return []
        disallowed: list[str] = []
        for path in sorted(root.rglob("*")):
            if not path.is_file():
                continue
            if path.name.startswith(".openart-"):
                continue
            rel = path.relative_to(root).as_posix()
            if _is_internal_target_control_path(rel, visibility_policy):
                disallowed.append(rel)
                continue
            allowed = self.provider.is_attacker_allowed_relative_path(rel, allowed_vectors) if attacker else self.provider.is_allowed_relative_path(rel)
            if not allowed:
                disallowed.append(rel)
        return disallowed

    def _validate_attacker_skill_folders(
        self,
        output_dir: Path,
        *,
        attacker_name: str,
        phase: str,
        index: int,
        allowed_vectors: tuple[str, ...] | None,
        visibility_policy: VisibilityPolicy | None = None,
    ) -> tuple[set[str], dict[str, Any]]:
        blocked, payload = validate_attacker_skill_folders(
            output_dir,
            self.provider if self.enabled() else None,
            allowed_vectors=allowed_vectors,
            visibility_policy=visibility_policy,
            metadata={
                "attacker_name": attacker_name,
                "phase": phase,
                "index": index,
            },
        )
        self._write_skill_validation_artifact(payload)
        return blocked, payload

    def _write_skill_validation_artifact(self, payload: dict[str, Any]) -> None:
        path = self.snapshots_dir() / "skill_validation.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    def _skill_dir_for_relative_path(self, surface: ControlSurfaceSpec, relative_path: str) -> str | None:
        return _skill_dir_for_surface_relative_path(surface, relative_path)

    def _instruction_path_for_surface(self, surface: ControlSurfaceSpec) -> str | None:
        return _instruction_path_for_surface(surface)

    def _read_enabled_instruction_files(
        self,
        output_dir: Path,
        allowed_vectors: set[str],
        visibility_policy: VisibilityPolicy | None,
    ) -> list[dict[str, str]]:
        return _read_enabled_instruction_files_for_provider(output_dir, self.provider if self.enabled() else None, allowed_vectors, visibility_policy)

    def _delete_allowed_files(
        self,
        root: Path,
        *,
        attacker: bool = False,
        allowed_vectors: tuple[str, ...] | None = None,
        skip_append_mode: bool = False,
        visibility_policy: VisibilityPolicy | None = None,
        blocked_relative_paths: set[str] | None = None,
    ) -> None:
        if not self.enabled() or not root.exists():
            return
        blocked = blocked_relative_paths or set()
        for path in sorted(root.rglob("*"), reverse=True):
            if not path.is_file():
                continue
            rel = path.relative_to(root).as_posix()
            if rel in blocked:
                continue
            if _is_internal_target_control_path(rel, visibility_policy):
                continue
            allowed = self.provider.is_attacker_allowed_relative_path(rel, allowed_vectors) if attacker else self.provider.is_allowed_relative_path(rel)
            if allowed and skip_append_mode and self._is_append_relative_path(rel, allowed_vectors):
                continue
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
            for item in list(path.iterdir()):
                if item.is_dir():
                    shutil.rmtree(item)
                else:
                    item.unlink()
        else:
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

    def _copy_allowed_dir_contents(
        self,
        src: Path,
        dst: Path,
        *,
        attacker: bool = False,
        allowed_vectors: tuple[str, ...] | None = None,
        skip_append_mode: bool = False,
        visibility_policy: VisibilityPolicy | None = None,
        blocked_relative_paths: set[str] | None = None,
    ) -> None:
        if not src.exists() or not self.enabled():
            return
        blocked = blocked_relative_paths or set()
        for path in sorted(src.rglob("*")):
            if not path.is_file():
                continue
            rel = path.relative_to(src).as_posix()
            if rel in blocked:
                continue
            if _is_internal_target_control_path(rel, visibility_policy):
                continue
            allowed = self.provider.is_attacker_allowed_relative_path(rel, allowed_vectors) if attacker else self.provider.is_allowed_relative_path(rel)
            if not allowed:
                continue
            if skip_append_mode and self._is_append_relative_path(rel, allowed_vectors):
                continue
            target = dst / rel
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(path, target)

    def _surface_matches_relative_path(self, surface: ControlSurfaceSpec, relative_path: str) -> bool:
        return any(fnmatch.fnmatch(relative_path, pattern) for pattern in _path_template_to_vector_pattern(surface.path_template))

    def _is_append_relative_path(self, relative_path: str, allowed_vectors: tuple[str, ...] | None = None) -> bool:
        if not self.enabled() or self.provider is None:
            return False
        allowed = set(allowed_vectors) if allowed_vectors else set()
        for surface in self.provider.attacker_surfaces:
            if surface.vector not in allowed and allowed:
                continue
            if surface.injection_mode not in {"append", "merge"}:
                continue
            if self._surface_matches_relative_path(surface, relative_path):
                return True
        return False

    def _diff_dirs(
        self,
        left: Path,
        right: Path,
        *,
        filter_allowed: bool = False,
        attacker: bool = False,
        allowed_vectors: tuple[str, ...] | None = None,
        visibility_policy: VisibilityPolicy | None = None,
    ) -> WorkspaceDiff:
        left_files = self._file_set(
            left,
            filter_allowed=filter_allowed,
            attacker=attacker,
            allowed_vectors=allowed_vectors,
            visibility_policy=visibility_policy,
        )
        right_files = self._file_set(
            right,
            filter_allowed=filter_allowed,
            attacker=attacker,
            allowed_vectors=allowed_vectors,
            visibility_policy=visibility_policy,
        )
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

    def _file_set(
        self,
        root: Path,
        *,
        filter_allowed: bool = False,
        attacker: bool = False,
        allowed_vectors: tuple[str, ...] | None = None,
        visibility_policy: VisibilityPolicy | None = None,
    ) -> set[Path]:
        if not root.exists():
            return set()
        result: set[Path] = set()
        for path in root.rglob("*"):
            if not path.is_file():
                continue
            rel = path.relative_to(root)
            if _is_internal_target_control_path(rel.as_posix(), visibility_policy):
                continue
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
            if _is_internal_target_control_path(rel):
                continue
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

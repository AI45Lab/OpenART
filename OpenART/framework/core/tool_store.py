from __future__ import annotations

import json
from pathlib import Path
import re
from typing import Any, Iterable, Mapping

import yaml


class ToolStoreError(ValueError):
    """Raised when a managed OpenART tool folder is malformed."""


_GUIDE_FILENAMES = ("SKILL.md", "skill.md", "skills.md", "SKILLS.md", "TOOL.md", "tool.md", "tools.md", "TOOLS.md")
_SKILL_GUIDE_FILENAMES = {"SKILL.md", "skill.md", "skills.md", "SKILLS.md"}
_SKILL_FRONTMATTER_PATTERN = re.compile(r"\A---\s*\n(.*?)\n---\s*(?:\n|\Z)(.*)\Z", re.DOTALL)


def _is_quarantined_tool_dir(name: str) -> bool:
    text = str(name)
    return text.startswith(".invalid.") or ".invalid." in text


def default_tool_store_root() -> Path:
    return Path(__file__).resolve().parents[3] / "openart-tools"


def _string_list(value: Any) -> list[str]:
    if value is None:
        return []
    raw_items = value if isinstance(value, list) else [value]
    result: list[str] = []
    seen: set[str] = set()
    for item in raw_items:
        text = str(item or "").strip()
        if not text or text in seen:
            continue
        seen.add(text)
        result.append(text)
    return result


def _mapping(value: Any) -> dict[str, Any]:
    return dict(value) if isinstance(value, Mapping) else {}


def _find_guide_path(tool_dir: Path) -> Path | None:
    for filename in _GUIDE_FILENAMES:
        candidate = tool_dir / filename
        if candidate.is_file():
            return candidate
    return None


def _parse_skill_markdown(text: str) -> tuple[dict[str, Any], str, str | None]:
    match = _SKILL_FRONTMATTER_PATTERN.match(text or "")
    if not match:
        return {}, "", "missing YAML frontmatter"
    raw_frontmatter, body = match.group(1), match.group(2)
    try:
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
        "invoke",
        "run this",
        "call this",
        "use the",
        "should use",
    )
    return any(term in lower for term in cue_terms)


def _description_from_markdown(text: str, tool_name: str) -> str:
    lines = str(text or "").splitlines()
    start_index = 0
    if lines and lines[0].strip() == "---":
        for index, raw_line in enumerate(lines[1:], start=1):
            if raw_line.strip() == "---":
                start_index = index + 1
                break
    for raw_line in lines[start_index:]:
        line = raw_line.strip()
        if not line or line.startswith("```") or line == "---":
            continue
        if line.startswith("#"):
            line = line.lstrip("#").strip()
        if not line or line == tool_name:
            continue
        return line[:240]
    return ""


def _load_guide_markdown(tool_dir: Path, tool_name: str, guide_path: Path) -> tuple[str, str, str, dict[str, Any]]:
    try:
        text = guide_path.read_text(encoding="utf-8")
    except UnicodeDecodeError as exc:
        raise ToolStoreError(f"{tool_dir.name}: {guide_path.name} must be UTF-8 text") from exc
    guide = text.strip()
    description = ""
    skill_metadata: dict[str, Any] = {}

    if guide_path.name in _SKILL_GUIDE_FILENAMES:
        frontmatter, body, parse_error = _parse_skill_markdown(text)
        if parse_error:
            raise ToolStoreError(f"{tool_dir.name}: {guide_path.name} {parse_error}")
        skill_name = str(frontmatter.get("name", "") or "").strip()
        description = str(frontmatter.get("description", "") or "").strip()
        if not skill_name:
            raise ToolStoreError(f"{tool_dir.name}: {guide_path.name} frontmatter requires non-empty name")
        if skill_name != tool_name:
            raise ToolStoreError(
                f"{tool_dir.name}: {guide_path.name} name {skill_name!r} must match tool name {tool_name!r}"
            )
        if not description:
            raise ToolStoreError(f"{tool_dir.name}: {guide_path.name} frontmatter requires non-empty description")
        if not body.strip():
            raise ToolStoreError(f"{tool_dir.name}: {guide_path.name} requires non-empty Markdown body")
        if not _has_activation_cue(text, skill_name=skill_name, skill_dir=tool_dir.name):
            raise ToolStoreError(f"{tool_dir.name}: {guide_path.name} missing activation cue")
        skill_metadata = dict(frontmatter)
        guide = text.strip()
    else:
        description = _description_from_markdown(text, tool_name)

    return guide, guide_path.name, description, skill_metadata


def _validate_relative_source_file(tool_dir: Path, value: Any) -> str:
    rel_text = str(value or "").strip()
    if not rel_text:
        raise ToolStoreError(f"{tool_dir.name}: source_files entries must be non-empty")
    rel_path = Path(rel_text)
    if rel_path.is_absolute() or ".." in rel_path.parts:
        raise ToolStoreError(f"{tool_dir.name}: invalid source_files path: {rel_text}")
    absolute = (tool_dir / rel_path).resolve()
    root = tool_dir.resolve()
    try:
        absolute.relative_to(root)
    except ValueError as exc:
        raise ToolStoreError(f"{tool_dir.name}: source_files path escapes tool folder: {rel_text}") from exc
    if not absolute.is_file():
        raise ToolStoreError(f"{tool_dir.name}: source file not found: {rel_text}")
    return rel_path.as_posix()


def _reject_absolute_managed_script_path(tool_name: str, values: Iterable[Any]) -> None:
    for value in values:
        text = str(value or "").strip()
        if not text.startswith("/"):
            continue
        if "/scripts/" in text or text.endswith((".py", ".sh")):
            raise ToolStoreError(
                f"{tool_name}: managed tool script paths must be relative source_files, got {text}"
            )


def _load_tool_folder(tool_dir: Path) -> dict[str, Any]:
    metadata_path = tool_dir / "tool.yaml"
    guide_path = _find_guide_path(tool_dir)
    if guide_path is None:
        raise ToolStoreError(f"{tool_dir}: missing SKILL.md or TOOL.md")

    if not metadata_path.is_file():
        name = tool_dir.name
        guide_markdown, guide_file, description, skill_metadata = _load_guide_markdown(tool_dir, name, guide_path)
        config = {
            "managed_openart_tool": True,
            "tool_store": {
                "name": name,
                "source_files": [],
                "guide_file": guide_file,
                "guide_only": True,
            },
        }
        if skill_metadata:
            config["skill"] = skill_metadata
        return {
            "name": name,
            "description": description,
            "args": [],
            "source_files": [],
            "tool_root": str(tool_dir.resolve()),
            "guide_markdown": guide_markdown,
            "config": config,
        }

    loaded = yaml.safe_load(metadata_path.read_text(encoding="utf-8"))
    if not isinstance(loaded, dict):
        raise ToolStoreError(f"{metadata_path}: tool.yaml must contain a mapping")

    name = str(loaded.get("name", "") or "").strip()
    if not name:
        raise ToolStoreError(f"{metadata_path}: name is required")
    if name != tool_dir.name:
        raise ToolStoreError(f"{metadata_path}: name {name!r} must match folder {tool_dir.name!r}")

    source_files = [_validate_relative_source_file(tool_dir, item) for item in _string_list(loaded.get("source_files"))]
    if not source_files:
        raise ToolStoreError(f"{name}: source_files must list at least one implementation file")

    args = _string_list(loaded.get("args"))
    _reject_absolute_managed_script_path(name, [loaded.get("command"), *args])

    payload = dict(loaded)
    payload["name"] = name
    payload["args"] = args
    payload["source_files"] = source_files
    payload["tool_root"] = str(tool_dir.resolve())
    guide_markdown, guide_file, skill_description, skill_metadata = _load_guide_markdown(tool_dir, name, guide_path)
    payload["guide_markdown"] = guide_markdown
    if skill_description and not str(payload.get("description", "") or "").strip():
        payload["description"] = skill_description

    config = _mapping(payload.get("config"))
    config["managed_openart_tool"] = True
    config["tool_store"] = {
        "name": name,
        "source_files": list(source_files),
        "guide_file": guide_file,
        "guide_only": False,
    }
    if skill_metadata:
        config["skill"] = skill_metadata
    required_env = _mapping(payload.get("required_env"))
    optional_env = _mapping(payload.get("optional_env"))
    if required_env or optional_env:
        config["env_requirements"] = {
            "required": sorted(required_env),
            "optional": sorted(optional_env),
        }
    payload["config"] = config
    return payload


def load_tool_store(
    tool_store_root: str | Path | None = None,
    *,
    selected_names: Iterable[str] | None = None,
) -> dict[str, dict[str, Any]]:
    root = Path(tool_store_root) if tool_store_root else default_tool_store_root()
    if not root.is_dir():
        return {}

    selected = None
    if selected_names is not None:
        selected = {str(name).strip() for name in selected_names if str(name).strip()}
    tools: dict[str, dict[str, Any]] = {}
    for tool_dir in sorted(path for path in root.iterdir() if path.is_dir()):
        if selected is None and _is_quarantined_tool_dir(tool_dir.name):
            continue
        if selected is not None and tool_dir.name not in selected:
            continue
        metadata_path = tool_dir / "tool.yaml"
        if not metadata_path.is_file() and _find_guide_path(tool_dir) is None:
            continue
        tool = _load_tool_folder(tool_dir)
        tools[tool["name"]] = tool
    return tools


def tool_store_to_manifest(tools: Mapping[str, Mapping[str, Any]]) -> dict[str, Any]:
    manifest_tools: list[dict[str, Any]] = []
    guides: list[str] = []

    for name in sorted(tools):
        raw_tool = dict(tools[name])
        service = str(raw_tool.get("service", "") or "").strip()
        required_env = _mapping(raw_tool.get("required_env"))
        optional_env = _mapping(raw_tool.get("optional_env"))

        config = _mapping(raw_tool.get("config"))
        tool_item: dict[str, Any] = {
            "name": raw_tool["name"],
            "description": str(raw_tool.get("description", "") or ""),
            "command": str(raw_tool.get("command", "") or ""),
            "args": _string_list(raw_tool.get("args")),
            "source_files": _string_list(raw_tool.get("source_files")),
            "tool_root": str(raw_tool.get("tool_root", "") or ""),
            "env": _mapping(raw_tool.get("env")),
            "env_from": _mapping(raw_tool.get("env_from")),
            "service": service,
            "tags": _string_list(raw_tool.get("tags")),
            "capabilities": _string_list(raw_tool.get("capabilities")),
            "side_effects": _string_list(raw_tool.get("side_effects")),
            "usage": str(raw_tool.get("usage", "") or ""),
            "examples": _string_list(raw_tool.get("examples")),
            "required_env": required_env,
            "optional_env": optional_env,
            "config": config,
        }
        manifest_tools.append({key: value for key, value in tool_item.items() if value not in ("", [], {})})

        guide = str(raw_tool.get("guide_markdown", "") or "").strip()
        if guide:
            guides.append(guide)

    result: dict[str, Any] = {
        "metadata": {
            "name": "openart-tools",
            "description": "Managed OpenART tool store generated from sibling openart-tools folders.",
        },
        "tools": manifest_tools,
    }
    if guides:
        result["tool_guide_markdown"] = "\n\n".join(guides)
    return result


def _env_aliases(value: Any) -> list[str]:
    if isinstance(value, Mapping):
        return _string_list(value.get("aliases"))
    return _string_list(value)


def _tool_env_requirements(tool: Mapping[str, Any]) -> dict[str, list[str]]:
    requirements: dict[str, list[str]] = {}
    for section_name in ("required_env", "optional_env"):
        section = tool.get(section_name)
        if not isinstance(section, Mapping):
            continue
        for key, value in section.items():
            canonical = str(key or "").strip()
            if not canonical:
                continue
            aliases = requirements.setdefault(canonical, [])
            for alias in _env_aliases(value):
                if alias not in aliases:
                    aliases.append(alias)
    return requirements


def resolve_manifest_tool_env(
    manifest: Mapping[str, Any],
    environ: Mapping[str, str] | None = None,
) -> tuple[dict[str, Any], dict[str, str]]:
    """Resolve managed tool env from host env and aliases declared in tool.yaml."""

    current_env = dict(environ or {})
    result = dict(manifest)
    resolved_runtime_env: dict[str, str] = {}
    resolved_tools: list[Any] = []

    for raw_tool in manifest.get("tools", []) if isinstance(manifest.get("tools"), list) else []:
        if not isinstance(raw_tool, Mapping):
            resolved_tools.append(raw_tool)
            continue

        tool = dict(raw_tool)
        explicit_env = {
            str(key): str(value)
            for key, value in (tool.get("env") if isinstance(tool.get("env"), Mapping) else {}).items()
            if str(key).strip()
        }
        env_from = {
            str(key): str(value)
            for key, value in (tool.get("env_from") if isinstance(tool.get("env_from"), Mapping) else {}).items()
            if str(key).strip() and str(value).strip()
        }

        for target_key, source_key in env_from.items():
            value = str(current_env.get(source_key, "") or "")
            if value:
                explicit_env[target_key] = value
                resolved_runtime_env[target_key] = value

        for canonical, aliases in _tool_env_requirements(tool).items():
            candidates = [canonical, *aliases]
            value = next((str(current_env.get(name, "") or "") for name in candidates if str(current_env.get(name, "") or "")), "")
            if not value:
                continue
            explicit_env[canonical] = value
            resolved_runtime_env[canonical] = value
            for alias in aliases:
                alias_value = str(current_env.get(alias, "") or value)
                if alias_value:
                    explicit_env.setdefault(alias, alias_value)
                    resolved_runtime_env.setdefault(alias, alias_value)

        if explicit_env:
            tool["env"] = explicit_env
        if env_from:
            tool["env_from"] = env_from
        resolved_tools.append(tool)

    result["tools"] = resolved_tools
    return result, resolved_runtime_env


def load_tool_store_manifest(
    tool_store_root: str | Path | None = None,
    *,
    selected_names: Iterable[str] | None = None,
) -> dict[str, Any]:
    return tool_store_to_manifest(load_tool_store(tool_store_root, selected_names=selected_names))


def tool_names_from_graph(graph: Any) -> set[str]:
    names: set[str] = set()

    def visit(value: Any) -> None:
        if isinstance(value, dict):
            for key, child in value.items():
                if key == "tool" and isinstance(child, str) and child.strip():
                    names.add(child.strip())
                visit(child)
        elif isinstance(value, list):
            for child in value:
                visit(child)

    visit(graph)
    return names


def selected_tool_names_from_task(task_root: str | Path) -> set[str]:
    graph_path = Path(task_root) / "tool_use_graph.json"
    if not graph_path.is_file():
        return set()
    return tool_names_from_graph(json.loads(graph_path.read_text(encoding="utf-8")))

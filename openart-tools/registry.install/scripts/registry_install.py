from __future__ import annotations

import argparse
import base64
import json
import os
import re
import shutil
import sqlite3
import sys
import tempfile
import time
from dataclasses import dataclass, field
from pathlib import Path, PurePosixPath
from typing import Any, Iterable, Mapping
from urllib.error import HTTPError, URLError
from urllib.parse import quote, urlencode, urlparse
from urllib.request import Request, urlopen

import yaml


REPO_ROOT = Path(__file__).resolve().parents[3]
OPENART_ROOT = REPO_ROOT / "OpenART"
if str(OPENART_ROOT) not in sys.path:
    sys.path.insert(0, str(OPENART_ROOT))

from framework.core.tool_store import load_tool_store_manifest  # noqa: E402


DEFAULT_MAX_FILES = 300
DEFAULT_MAX_TOTAL_BYTES = 25 * 1024 * 1024
_SKILL_FRONTMATTER_RE = re.compile(r"\A---\s*\n(.*?)\n---\s*(?:\n|\Z)(.*)\Z", re.DOTALL)
_SQLITE_HEADER = b"SQLite format 3\x00"


@dataclass(frozen=True, slots=True)
class GitHubSelection:
    owner: str
    repo: str
    kind: str
    ref: str
    path: str


@dataclass(slots=True)
class DownloadState:
    max_files: int
    max_total_bytes: int
    file_count: int = 0
    total_bytes: int = 0

    def add_file(self, rel_path: str, data: bytes) -> None:
        self.file_count += 1
        if self.file_count > self.max_files:
            raise ValueError(f"download exceeds --max-files={self.max_files}")
        self.total_bytes += len(data)
        if self.total_bytes > self.max_total_bytes:
            raise ValueError(f"download exceeds --max-total-bytes={self.max_total_bytes}")
        if not data:
            raise ValueError(f"downloaded file is empty: {rel_path}")


@dataclass(slots=True)
class ValidationReport:
    warnings: list[str] = field(default_factory=list)
    materialization_mode: str = "github_guide_only"
    source_files: list[str] = field(default_factory=list)


def _short(value: Any, *, limit: int = 500) -> str:
    text = re.sub(r"\s+", " ", str(value or "").strip())
    if len(text) <= limit:
        return text
    return text[: limit - 3].rstrip() + "..."


def _loads(value: Any, fallback: Any) -> Any:
    if isinstance(value, (dict, list)):
        return value
    try:
        return json.loads(value)
    except (TypeError, json.JSONDecodeError):
        return fallback


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


def _parse_ids(values: Iterable[str]) -> list[str]:
    result: list[str] = []
    seen: set[str] = set()
    for value in values:
        path = Path(str(value))
        items: list[str] = []
        if path.is_file():
            for line in path.read_text(encoding="utf-8").splitlines():
                clean = line.split("#", 1)[0].strip()
                if clean:
                    items.append(clean)
        else:
            items.extend(part.strip() for part in str(value).split(",") if part.strip())
        for item in items:
            if item not in seen:
                seen.add(item)
                result.append(item)
    return result


def _connect_registry(index_path: Path) -> sqlite3.Connection:
    if not index_path.is_file():
        raise ValueError(f"registry index is not a file: {index_path}")
    with index_path.open("rb") as handle:
        if handle.read(len(_SQLITE_HEADER)) != _SQLITE_HEADER:
            raise ValueError(f"registry index is not a SQLite database: {index_path}")
    conn = sqlite3.connect(f"file:{index_path}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    return conn


def _require_schema(conn: sqlite3.Connection) -> None:
    columns = {row["name"] for row in conn.execute("PRAGMA table_info(tools)")}
    required = {"tool_id", "virtual_tool_name", "description", "source_url", "raw", "deleted_at"}
    missing = sorted(required - columns)
    if missing:
        raise ValueError(f"registry schema is missing required columns: {missing}")


def _resolve_row(conn: sqlite3.Connection, identifier: str) -> sqlite3.Row | None:
    return conn.execute(
        """
        SELECT * FROM tools
        WHERE (tool_id = ? OR virtual_tool_name = ?) AND deleted_at = ''
        """,
        (identifier, identifier),
    ).fetchone()


def _row_payload(row: sqlite3.Row) -> dict[str, Any]:
    columns = set(row.keys())
    payload = {
        "tool_id": row["tool_id"],
        "virtual_tool_name": row["virtual_tool_name"],
        "description": row["description"],
        "source_url": row["source_url"],
        "raw": _loads(row["raw"], {}),
    }
    for optional in ("tags", "capabilities"):
        if optional in columns:
            payload[optional] = _loads(row[optional], [])
    return payload


def _source_url(record: Mapping[str, Any]) -> str:
    source_url = str(record.get("source_url") or "").strip()
    if source_url:
        return source_url
    raw = record.get("raw")
    if isinstance(raw, Mapping):
        nested = raw.get("record")
        if isinstance(nested, Mapping):
            return str(nested.get("skill_url") or "").strip()
    return ""


def parse_github_url(url: str) -> GitHubSelection:
    text = str(url or "").strip()
    if not text:
        raise ValueError("registry row has no source_url or raw.record.skill_url")
    parsed = urlparse(text)
    if parsed.scheme != "https" or parsed.netloc.lower() != "github.com":
        raise ValueError("only https://github.com URLs are supported")
    parts = [part for part in parsed.path.split("/") if part]
    if len(parts) < 5:
        raise ValueError("GitHub plain repo URLs are not installable; use /tree/<ref>/<path> or /blob/<ref>/<path>")
    owner, repo, kind, ref = parts[:4]
    rel_parts = parts[4:]
    if kind not in {"tree", "blob"}:
        raise ValueError("GitHub URL must use /tree/<ref>/<path> or /blob/<ref>/<path>")
    if not owner or not repo or not ref or not rel_parts:
        raise ValueError("GitHub URL must include owner, repo, ref, and path")
    rel_path = PurePosixPath(*rel_parts).as_posix()
    _safe_rel_path(rel_path, field="GitHub URL path")
    return GitHubSelection(owner=owner, repo=repo, kind=kind, ref=ref, path=rel_path)


def _safe_rel_path(value: str, *, field: str) -> str:
    text = str(value or "").strip()
    if not text:
        raise ValueError(f"{field} must be non-empty")
    path = PurePosixPath(text)
    if path.is_absolute() or any(part in {"", ".", ".."} for part in path.parts):
        raise ValueError(f"{field} contains an unsafe path: {text}")
    return path.as_posix()


def _relative_to_prefix(api_path: str, prefix: str, *, selected_is_file: bool) -> str:
    normalized = _safe_rel_path(api_path, field="GitHub API path")
    selected = _safe_rel_path(prefix, field="selected GitHub prefix")
    if selected_is_file:
        if normalized != selected:
            raise ValueError(f"GitHub API path is outside selected file: {normalized}")
        return PurePosixPath(normalized).name
    selected_with_slash = selected.rstrip("/") + "/"
    if normalized == selected:
        raise ValueError(f"GitHub API path points at selected folder, not a file: {normalized}")
    if not normalized.startswith(selected_with_slash):
        raise ValueError(f"GitHub API path is outside selected folder: {normalized}")
    return _safe_rel_path(normalized[len(selected_with_slash) :], field="downloaded relative path")


def _github_headers() -> dict[str, str]:
    headers = {
        "Accept": "application/vnd.github+json",
        "User-Agent": "openart-registry-install",
        "X-GitHub-Api-Version": "2022-11-28",
    }
    token = os.environ.get("GITHUB_TOKEN", "").strip()
    if token:
        headers["Authorization"] = f"Bearer {token}"
    return headers


def _github_contents_url(selection: GitHubSelection, api_path: str) -> str:
    encoded_path = "/".join(quote(part, safe="") for part in PurePosixPath(api_path).parts)
    query = urlencode({"ref": selection.ref})
    return f"https://api.github.com/repos/{quote(selection.owner, safe='')}/{quote(selection.repo, safe='')}/contents/{encoded_path}?{query}"


def _github_api_json(selection: GitHubSelection, api_path: str) -> Any:
    request = Request(_github_contents_url(selection, api_path), headers=_github_headers())
    try:
        with urlopen(request, timeout=30) as response:
            data = response.read()
    except HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace") if exc.fp else str(exc)
        raise RuntimeError(f"GitHub API request failed for {api_path}: HTTP {exc.code}: {_short(detail)}") from exc
    except URLError as exc:
        raise RuntimeError(f"GitHub API request failed for {api_path}: {_short(exc)}") from exc
    return json.loads(data.decode("utf-8"))


def _github_api_raw_bytes(selection: GitHubSelection, api_path: str) -> bytes:
    headers = _github_headers()
    headers["Accept"] = "application/vnd.github.raw"
    request = Request(_github_contents_url(selection, api_path), headers=headers)
    try:
        with urlopen(request, timeout=30) as response:
            return response.read()
    except HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace") if exc.fp else str(exc)
        raise RuntimeError(f"GitHub API raw request failed for {api_path}: HTTP {exc.code}: {_short(detail)}") from exc
    except URLError as exc:
        raise RuntimeError(f"GitHub API raw request failed for {api_path}: {_short(exc)}") from exc


def _decode_file_payload(selection: GitHubSelection, item: Mapping[str, Any], api_path: str) -> bytes:
    content = item.get("content")
    if isinstance(content, str) and content.strip():
        encoding = str(item.get("encoding") or "").lower()
        if encoding and encoding != "base64":
            raise ValueError(f"unsupported GitHub file encoding: {encoding}")
        return base64.b64decode(content)
    return _github_api_raw_bytes(selection, api_path)


def _download_item(
    selection: GitHubSelection,
    api_path: str,
    destination: Path,
    state: DownloadState,
    *,
    selected_is_file: bool,
) -> None:
    payload = _github_api_json(selection, api_path)
    if isinstance(payload, list):
        if selected_is_file:
            raise ValueError("GitHub blob URL resolved to a directory")
        if not payload:
            raise ValueError(f"downloaded folder is empty: {api_path}")
        for item in payload:
            if not isinstance(item, Mapping):
                raise ValueError("GitHub directory response contained a non-object entry")
            item_type = str(item.get("type") or "")
            item_path = str(item.get("path") or "")
            if item_type == "dir":
                _download_item(selection, item_path, destination, state, selected_is_file=False)
            elif item_type == "file":
                _download_item(selection, item_path, destination, state, selected_is_file=False)
            else:
                raise ValueError(f"unsupported GitHub content type for {item_path}: {item_type}")
        return

    if not isinstance(payload, Mapping):
        raise ValueError("GitHub content response must be an object or list")
    item_type = str(payload.get("type") or "")
    item_path = str(payload.get("path") or api_path)
    if item_type == "dir":
        if selection.kind == "blob":
            raise ValueError("GitHub blob URL resolved to a directory")
        _download_item(selection, item_path, destination, state, selected_is_file=False)
        return
    if item_type != "file":
        raise ValueError(f"unsupported GitHub content type for {item_path}: {item_type}")

    rel_path = _relative_to_prefix(item_path, selection.path, selected_is_file=selected_is_file)
    data = _decode_file_payload(selection, payload, item_path)
    state.add_file(rel_path, data)
    target = destination / rel_path
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(data)


def download_github_selection(
    selection: GitHubSelection,
    destination: Path,
    *,
    max_files: int = DEFAULT_MAX_FILES,
    max_total_bytes: int = DEFAULT_MAX_TOTAL_BYTES,
) -> None:
    state = DownloadState(max_files=max_files, max_total_bytes=max_total_bytes)
    try:
        _download_item(selection, selection.path, destination, state, selected_is_file=selection.kind == "blob")
    except ValueError as exc:
        if selection.kind != "blob" or "resolved to a directory" not in str(exc):
            raise
        retry = GitHubSelection(
            owner=selection.owner,
            repo=selection.repo,
            kind="tree",
            ref=selection.ref,
            path=selection.path,
        )
        state = DownloadState(max_files=max_files, max_total_bytes=max_total_bytes)
        _download_item(retry, retry.path, destination, state, selected_is_file=False)
    if state.file_count == 0:
        raise ValueError("downloaded folder is empty")


def _parse_skill_markdown(text: str) -> tuple[dict[str, Any], str, bool]:
    match = _SKILL_FRONTMATTER_RE.match(text or "")
    if not match:
        return {}, text or "", False
    raw_frontmatter, body = match.group(1), match.group(2)
    loaded = yaml.safe_load(raw_frontmatter) if raw_frontmatter.strip() else {}
    if not isinstance(loaded, dict):
        raise ValueError("SKILL.md YAML frontmatter must be a mapping")
    return dict(loaded), body, True


def _has_activation_cue(text: str, *, tool_name: str) -> bool:
    lower = str(text or "").lower()
    name = tool_name.lower()
    mentions = name in lower or "skill.md" in lower or "wrapper" in lower
    if not mentions:
        return False
    return any(
        term in lower
        for term in (
            "use this skill",
            "when to use",
            "trigger",
            "invoke",
            "run this",
            "call this",
            "use the",
            "should use",
        )
    )


def _dump_skill_markdown(frontmatter: Mapping[str, Any], body: str) -> str:
    ordered: dict[str, Any] = {}
    ordered["name"] = str(frontmatter.get("name") or "").strip()
    ordered["description"] = str(frontmatter.get("description") or "").strip()
    for key, value in frontmatter.items():
        if key not in ordered:
            ordered[key] = value
    return "---\n" + yaml.safe_dump(ordered, sort_keys=False, allow_unicode=False).strip() + "\n---\n" + body.rstrip() + "\n"


def normalize_skill_markdown(tool_dir: Path, *, tool_name: str, registry_description: str) -> None:
    skill_path = tool_dir / "SKILL.md"
    if not skill_path.is_file():
        raise ValueError("SKILL.md not found")
    original = skill_path.read_text(encoding="utf-8")
    frontmatter, body, _had_frontmatter = _parse_skill_markdown(original)
    if not body.strip():
        raise ValueError("SKILL.md requires non-empty Markdown body")

    changed = False
    if frontmatter.get("name") != tool_name:
        frontmatter["name"] = tool_name
        changed = True
    if not str(frontmatter.get("description") or "").strip():
        description = str(registry_description or "").strip()
        if not description:
            raise ValueError("SKILL.md frontmatter requires description and registry row description is empty")
        frontmatter["description"] = description
        changed = True
    if not _has_activation_cue(_dump_skill_markdown(frontmatter, body), tool_name=tool_name):
        body = (
            f"Use this skill when the OpenART registry selects `{tool_name}` for the current task.\n\n"
            + body.lstrip()
        )
        changed = True

    normalized = _dump_skill_markdown(frontmatter, body)
    if normalized != original:
        references = tool_dir / "references"
        references.mkdir(parents=True, exist_ok=True)
        (references / "original_SKILL.md").write_text(original, encoding="utf-8")
        skill_path.write_text(normalized, encoding="utf-8")


def relocate_top_level_tool_yaml(tool_dir: Path) -> None:
    source = tool_dir / "tool.yaml"
    if not source.exists():
        return
    if not source.is_file():
        raise ValueError("top-level tool.yaml is not a file")
    references = tool_dir / "references"
    references.mkdir(parents=True, exist_ok=True)
    target = references / "original_tool.yaml"
    if target.exists():
        raise ValueError("references/original_tool.yaml already exists")
    source.rename(target)


def _runner_script() -> str:
    return r'''#!/usr/bin/env python3
from __future__ import annotations

import argparse
import os
from pathlib import Path
import stat
import subprocess
import sys


ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
RUNNER_NAME = Path(__file__).name


def _available_scripts() -> list[Path]:
    if not SCRIPTS.is_dir():
        return []
    result: list[Path] = []
    for path in sorted(SCRIPTS.rglob("*")):
        if not path.is_file() or path.name == RUNNER_NAME:
            continue
        result.append(path)
    return result


def _resolve_script(name: str) -> Path:
    text = str(name or "").strip()
    if not text:
        raise SystemExit("script name is required")
    rel = Path(text)
    if rel.is_absolute() or ".." in rel.parts:
        raise SystemExit(f"unsafe script path: {text}")
    candidate = (ROOT / rel) if rel.parts and rel.parts[0] == "scripts" else (SCRIPTS / rel)
    candidate = candidate.resolve()
    scripts_root = SCRIPTS.resolve()
    try:
        candidate.relative_to(scripts_root)
    except ValueError as exc:
        raise SystemExit(f"script path escapes scripts/: {text}") from exc
    if candidate.name == RUNNER_NAME or not candidate.is_file():
        raise SystemExit(f"script not found: {text}")
    return candidate


def _print_list() -> int:
    for path in _available_scripts():
        print(path.relative_to(ROOT).as_posix())
    return 0


def _inspect(name: str) -> int:
    path = _resolve_script(name)
    print(path.relative_to(ROOT).as_posix())
    print(f"size_bytes={path.stat().st_size}")
    mode = path.stat().st_mode
    print(f"executable={bool(mode & stat.S_IXUSR)}")
    return 0


def _run(name: str, args: list[str]) -> int:
    path = _resolve_script(name)
    suffix = path.suffix.lower()
    if suffix == ".py":
        command = [sys.executable, str(path), *args]
    elif suffix in {".sh", ".bash"}:
        command = ["/bin/bash", str(path), *args]
    elif os.access(path, os.X_OK):
        command = [str(path), *args]
    else:
        raise SystemExit(f"script is not directly runnable; use a .py/.sh script or mark executable: {path.relative_to(ROOT).as_posix()}")
    completed = subprocess.run(command, cwd=str(ROOT))
    return int(completed.returncode)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Inspect or run upstream scripts bundled with this OpenART registry skill.")
    subparsers = parser.add_subparsers(dest="command", required=True)
    subparsers.add_parser("list", help="List bundled upstream scripts.")
    inspect_parser = subparsers.add_parser("inspect", help="Print metadata for one bundled script.")
    inspect_parser.add_argument("script")
    run_parser = subparsers.add_parser("run", help="Run one bundled script by safe relative name.")
    run_parser.add_argument("script")
    run_parser.add_argument("script_args", nargs=argparse.REMAINDER)
    args = parser.parse_args(argv)
    if args.command == "list":
        return _print_list()
    if args.command == "inspect":
        return _inspect(args.script)
    if args.command == "run":
        return _run(args.script, args.script_args)
    raise SystemExit(f"unknown command: {args.command}")


if __name__ == "__main__":
    raise SystemExit(main())
'''


def _script_files(tool_dir: Path) -> list[str]:
    scripts_dir = tool_dir / "scripts"
    if not scripts_dir.is_dir():
        return []
    result: list[str] = []
    for path in sorted(scripts_dir.rglob("*")):
        if not path.is_file():
            continue
        rel = path.relative_to(tool_dir).as_posix()
        if rel == "scripts/openart_skill_runner.py":
            continue
        result.append(_safe_rel_path(rel, field="script source file"))
    return result


def _write_openart_runner_tool_yaml(
    tool_dir: Path,
    *,
    tool_name: str,
    registry_description: str,
    record: Mapping[str, Any] | None = None,
) -> list[str]:
    scripts_dir = tool_dir / "scripts"
    scripts_dir.mkdir(parents=True, exist_ok=True)
    wrapper_rel = "scripts/openart_skill_runner.py"
    wrapper_path = tool_dir / wrapper_rel
    if wrapper_path.exists():
        references = tool_dir / "references"
        references.mkdir(parents=True, exist_ok=True)
        target = references / "original_openart_skill_runner.py"
        if target.exists():
            raise ValueError("references/original_openart_skill_runner.py already exists")
        wrapper_path.rename(target)
    wrapper_path.write_text(_runner_script(), encoding="utf-8")
    wrapper_path.chmod(0o755)

    source_files = [wrapper_rel, *_script_files(tool_dir)]
    description = _short(registry_description, limit=500) or f"GitHub-backed OpenART skill {tool_name}."
    payload: dict[str, Any] = {
        "name": tool_name,
        "description": description,
        "command": "/opt/openart-venv/bin/python3",
        "args": [wrapper_rel],
        "source_files": source_files,
        "side_effects": ["local_process_execution"],
        "usage": f"{tool_name} list | inspect <script> | run <script> -- <args>",
        "examples": [
            f"{tool_name} list",
            f"{tool_name} inspect scripts/example.py",
            f"{tool_name} run scripts/example.py -- --help",
        ],
    }
    if record is not None:
        tags = _string_list(record.get("tags"))
        capabilities = _string_list(record.get("capabilities"))
        if tags:
            payload["tags"] = tags
        if capabilities:
            payload["capabilities"] = capabilities
    (tool_dir / "tool.yaml").write_text(
        yaml.safe_dump(payload, sort_keys=False, allow_unicode=True),
        encoding="utf-8",
    )
    return source_files


def _prune_guide_only_tool_dir(tool_dir: Path) -> None:
    for child in list(tool_dir.iterdir()):
        if child.name in {"SKILL.md", "references"}:
            continue
        if child.is_dir():
            shutil.rmtree(child)
        else:
            child.unlink()


def _validate_downloaded_paths(tool_dir: Path) -> None:
    files = [path for path in tool_dir.rglob("*") if path.is_file()]
    if not files:
        raise ValueError("downloaded folder is empty")
    root = tool_dir.resolve()
    for path in files:
        rel = path.relative_to(tool_dir).as_posix()
        _safe_rel_path(rel, field="downloaded file path")
        resolved = path.resolve()
        try:
            resolved.relative_to(root)
        except ValueError as exc:
            raise ValueError(f"downloaded file escapes install root: {rel}") from exc
        if path.stat().st_size == 0:
            raise ValueError(f"downloaded file is empty: {rel}")


def validate_installed_tool(tool_store_root: Path, tool_name: str) -> ValidationReport:
    tool_dir = tool_store_root / tool_name
    report = ValidationReport()
    skill_path = tool_dir / "SKILL.md"
    if not skill_path.is_file():
        raise ValueError("SKILL.md not found")
    text = skill_path.read_text(encoding="utf-8")
    frontmatter, body, had_frontmatter = _parse_skill_markdown(text)
    if not had_frontmatter:
        raise ValueError("SKILL.md missing YAML frontmatter")
    if not str(frontmatter.get("name") or "").strip():
        raise ValueError("SKILL.md frontmatter requires name")
    if str(frontmatter.get("name") or "").strip() != tool_name:
        raise ValueError("SKILL.md frontmatter name must match installed tool name")
    if not str(frontmatter.get("description") or "").strip():
        raise ValueError("SKILL.md frontmatter requires description")
    if not body.strip():
        raise ValueError("SKILL.md requires non-empty Markdown body")
    if not _has_activation_cue(text, tool_name=tool_name):
        raise ValueError("SKILL.md missing OpenART activation cue")
    if len(text.splitlines()) > 500:
        report.warnings.append("SKILL.md is longer than 500 lines")
    description_lines = [line for line in str(frontmatter.get("description") or "").splitlines() if line.strip()]
    if len(description_lines) > 15:
        report.warnings.append("description is longer than 15 non-empty lines")
    if not (tool_dir / "references").is_dir():
        report.warnings.append("missing references/ directory")

    manifest = load_tool_store_manifest(tool_store_root, selected_names={tool_name})
    manifest_tools = [
        item
        for item in manifest.get("tools", [])
        if isinstance(item, Mapping) and str(item.get("name") or "").strip() == tool_name
    ]
    names = {
        str(item.get("name") or "").strip()
        for item in manifest.get("tools", [])
        if isinstance(item, Mapping)
    }
    if tool_name not in names:
        raise ValueError("load_tool_store_manifest did not include installed tool")
    if manifest_tools:
        tool = manifest_tools[0]
        config = tool.get("config") if isinstance(tool.get("config"), Mapping) else {}
        store_config = config.get("tool_store") if isinstance(config.get("tool_store"), Mapping) else {}
        guide_only = bool(store_config.get("guide_only"))
        report.materialization_mode = "github_guide_only" if guide_only else "github_script_tool"
        report.source_files = _string_list(store_config.get("source_files"))
        if not guide_only:
            if "scripts/openart_skill_runner.py" not in report.source_files:
                raise ValueError("script-backed GitHub skill is missing generated OpenART runner in source_files")
            args = _string_list(tool.get("args"))
            if args[:1] != ["scripts/openart_skill_runner.py"]:
                raise ValueError("script-backed GitHub skill command must invoke scripts/openart_skill_runner.py")
    return report


def prepare_downloaded_tool(
    tool_dir: Path,
    *,
    tool_name: str,
    registry_description: str,
    record: Mapping[str, Any] | None = None,
) -> ValidationReport:
    _validate_downloaded_paths(tool_dir)
    relocate_top_level_tool_yaml(tool_dir)
    normalize_skill_markdown(tool_dir, tool_name=tool_name, registry_description=registry_description)
    if (tool_dir / "scripts").is_dir():
        _write_openart_runner_tool_yaml(
            tool_dir,
            tool_name=tool_name,
            registry_description=registry_description,
            record=record,
        )
    else:
        _prune_guide_only_tool_dir(tool_dir)
    _validate_downloaded_paths(tool_dir)
    return validate_installed_tool(tool_dir.parent, tool_name)


def _is_valid_existing(tool_store_root: Path, tool_name: str) -> tuple[bool, str]:
    try:
        validate_installed_tool(tool_store_root, tool_name)
    except Exception as exc:
        return False, _short(exc)
    return True, ""


def _backup_invalid(existing: Path) -> Path:
    timestamp = int(time.time())
    backup = existing.parent / f"{existing.name}.invalid.{timestamp}"
    suffix = 1
    while backup.exists():
        backup = existing.parent / f"{existing.name}.invalid.{timestamp}.{suffix}"
        suffix += 1
    shutil.move(str(existing), str(backup))
    return backup


def _install_one(
    record: Mapping[str, Any],
    *,
    tool_store_root: Path,
    max_files: int,
    max_total_bytes: int,
    overwrite: bool,
    replace_invalid: bool,
) -> dict[str, Any]:
    tool_name = str(record.get("virtual_tool_name") or "").strip()
    if not tool_name:
        return {"id": str(record.get("tool_id") or ""), "tool_name": "", "status": "failed", "reason": "row has no virtual_tool_name"}
    identifier = str(record.get("tool_id") or tool_name)
    existing = tool_store_root / tool_name
    if existing.exists() and not existing.is_dir():
        return {"id": identifier, "tool_name": tool_name, "status": "failed", "reason": "existing path is not a directory"}

    if existing.is_dir():
        valid, reason = _is_valid_existing(tool_store_root, tool_name)
        if valid and not overwrite:
            return {"id": identifier, "tool_name": tool_name, "status": "reused", "path": str(existing)}
        if not valid and not (replace_invalid or overwrite):
            return {
                "id": identifier,
                "tool_name": tool_name,
                "status": "failed",
                "reason": f"existing folder is invalid; rerun with --replace-invalid to reinstall: {reason}",
            }

    try:
        selection = parse_github_url(_source_url(record))
    except Exception as exc:
        return {"id": identifier, "tool_name": tool_name, "status": "unsupported", "reason": _short(exc)}

    tool_store_root.mkdir(parents=True, exist_ok=True)
    temp_parent = Path(tempfile.mkdtemp(prefix=f".{tool_name}.install.", dir=str(tool_store_root)))
    temp_tool = temp_parent / tool_name
    temp_tool.mkdir(parents=True, exist_ok=True)
    try:
        download_github_selection(
            selection,
            temp_tool,
            max_files=max_files,
            max_total_bytes=max_total_bytes,
        )
        report = prepare_downloaded_tool(
            temp_tool,
            tool_name=tool_name,
            registry_description=str(record.get("description") or ""),
            record=record,
        )

        backup_path = None
        if existing.is_dir():
            valid, _reason = _is_valid_existing(tool_store_root, tool_name)
            if valid and overwrite:
                shutil.rmtree(existing)
            else:
                backup_path = _backup_invalid(existing)
        shutil.move(str(temp_tool), str(existing))
        result = {
            "id": identifier,
            "tool_name": tool_name,
            "status": "created",
            "path": str(existing),
            "warnings": list(report.warnings),
            "materialization_mode": report.materialization_mode,
            "source_files": list(report.source_files),
        }
        if backup_path is not None:
            result["backup"] = str(backup_path)
        if overwrite:
            result["reason"] = "overwrote_existing"
        return result
    except Exception as exc:
        return {"id": identifier, "tool_name": tool_name, "status": "failed", "reason": _short(exc)}
    finally:
        shutil.rmtree(temp_parent, ignore_errors=True)


def _group_install_results(tool_store_root: Path, results: list[dict[str, Any]]) -> dict[str, Any]:
    grouped: dict[str, list[dict[str, Any]]] = {"created": [], "reused": [], "unsupported": [], "failed": []}
    for item in results:
        status = str(item.get("status") or "")
        if status in grouped:
            grouped[status].append(item)
        else:
            grouped["failed"].append({**item, "status": "failed", "reason": f"unknown install status: {status}"})
    return {
        "tool_store": str(tool_store_root),
        "created": grouped["created"],
        "reused": grouped["reused"],
        "unsupported": grouped["unsupported"],
        "failed": grouped["failed"],
        "results": results,
    }


def install_registry_record(
    record: Mapping[str, Any],
    tool_store_root: Path,
    *,
    max_files: int = DEFAULT_MAX_FILES,
    max_total_bytes: int = DEFAULT_MAX_TOTAL_BYTES,
    overwrite: bool = False,
    replace_invalid: bool = False,
) -> dict[str, Any]:
    return _install_one(
        record,
        tool_store_root=tool_store_root,
        max_files=max_files,
        max_total_bytes=max_total_bytes,
        overwrite=overwrite,
        replace_invalid=replace_invalid,
    )


def install_registry_records(
    records: Iterable[Mapping[str, Any]],
    tool_store_root: Path,
    *,
    max_files: int = DEFAULT_MAX_FILES,
    max_total_bytes: int = DEFAULT_MAX_TOTAL_BYTES,
    overwrite: bool = False,
    replace_invalid: bool = False,
) -> dict[str, Any]:
    results = [
        install_registry_record(
            record,
            tool_store_root,
            max_files=max_files,
            max_total_bytes=max_total_bytes,
            overwrite=overwrite,
            replace_invalid=replace_invalid,
        )
        for record in records
    ]
    return _group_install_results(tool_store_root, results)


def install_registry_tools(
    index_path: Path,
    identifiers: Iterable[str],
    tool_store_root: Path,
    *,
    max_files: int = DEFAULT_MAX_FILES,
    max_total_bytes: int = DEFAULT_MAX_TOTAL_BYTES,
    overwrite: bool = False,
    replace_invalid: bool = False,
) -> dict[str, Any]:
    parsed_ids = _parse_ids(identifiers)
    if not parsed_ids:
        raise ValueError("at least one --ids value is required")
    results: list[dict[str, Any]] = []
    with _connect_registry(index_path) as conn:
        _require_schema(conn)
        for identifier in parsed_ids:
            row = _resolve_row(conn, identifier)
            if row is None:
                results.append({"id": identifier, "tool_name": "", "status": "failed", "reason": "registry id not found or deleted"})
                continue
            results.append(
                _install_one(
                    _row_payload(row),
                    tool_store_root=tool_store_root,
                    max_files=max_files,
                    max_total_bytes=max_total_bytes,
                    overwrite=overwrite,
                    replace_invalid=replace_invalid,
                )
            )

    return _group_install_results(tool_store_root, results)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Install GitHub-hosted registry entries into an OpenART tool store.")
    parser.add_argument("--index", required=True)
    parser.add_argument("--ids", nargs="+", required=True)
    parser.add_argument("--tool-store", required=True)
    parser.add_argument("--max-files", type=int, default=DEFAULT_MAX_FILES)
    parser.add_argument("--max-total-bytes", type=int, default=DEFAULT_MAX_TOTAL_BYTES)
    parser.add_argument("--overwrite", action="store_true")
    parser.add_argument("--replace-invalid", action="store_true")
    args = parser.parse_args(argv)

    try:
        result = install_registry_tools(
            Path(args.index),
            args.ids,
            Path(args.tool_store),
            max_files=args.max_files,
            max_total_bytes=args.max_total_bytes,
            overwrite=args.overwrite,
            replace_invalid=args.replace_invalid,
        )
    except Exception as exc:
        print(f"ERROR: {_short(exc)}")
        return 1

    for key, label in (
        ("created", "CREATED"),
        ("reused", "REUSED"),
        ("unsupported", "UNSUPPORTED"),
        ("failed", "FAILED"),
    ):
        for item in result[key]:
            suffix = f": {item.get('reason')}" if item.get("reason") else ""
            path = f" {item.get('path')}" if item.get("path") else ""
            print(f"{label}: {item.get('id')}{path}{suffix}")
    print(json.dumps(result, indent=2, sort_keys=True, ensure_ascii=False))
    return 1 if result["failed"] else 0


if __name__ == "__main__":
    raise SystemExit(main())

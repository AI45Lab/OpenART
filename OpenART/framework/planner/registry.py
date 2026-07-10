from __future__ import annotations

from dataclasses import dataclass, field
import json
import re
import sqlite3
import shutil
from pathlib import Path
import time
from typing import Any, Iterable, Mapping, Sequence

import yaml

from framework.core.tool_store import (
    default_tool_store_root,
    load_tool_store,
    load_tool_store_manifest,
    tool_store_to_manifest,
)

from . import registry_install as github_registry_install
from .safe_world import build_tool_pool, group_tools_by_capability


REGISTRY_HELPER_NAMES = frozenset(
    {
        "registry.search",
        "registry.show",
        "registry.install",
        "registry.run_tool",
    }
)
DEFAULT_REGISTRY_RELATIVE_PATH = Path(".registry") / "openart_tool_registry.sqlite"
REGISTRY_FEEDBACK_VERSION = 1
REGISTRY_OPENART_TOOL_KEY = "openart_tool"
_OPENART_TOOL_FILE_REQUIREMENTS_MISSING = "registry row has no openart_tool implementation payload"
_ALLOWED_GUIDE_FILENAMES = {"SKILL.md", "skill.md", "skills.md", "SKILLS.md", "TOOL.md", "tool.md", "tools.md", "TOOLS.md"}
_SQLITE_HEADER = b"SQLite format 3\x00"
_WORD_RE = re.compile(r"[A-Za-z0-9_+-]+")
_STOPWORDS = {
    "about",
    "across",
    "agent",
    "also",
    "and",
    "are",
    "asks",
    "but",
    "can",
    "contains",
    "create",
    "from",
    "has",
    "into",
    "must",
    "needs",
    "not",
    "organize",
    "prepare",
    "should",
    "summary",
    "task",
    "that",
    "the",
    "their",
    "them",
    "these",
    "this",
    "those",
    "tool",
    "upload",
    "use",
    "user",
    "with",
    "work",
    "workspace",
}


@dataclass(slots=True)
class RegistryToolFeedback:
    id: str
    tool_name: str
    status: str
    reason: str = ""
    materialization_mode: str = ""
    source_url: str = ""
    warnings: list[str] = field(default_factory=list)

    def as_dict(self) -> dict[str, Any]:
        payload = {
            "id": self.id,
            "tool_name": self.tool_name,
            "status": self.status,
        }
        if self.reason:
            payload["reason"] = self.reason
        if self.materialization_mode:
            payload["materialization_mode"] = self.materialization_mode
        if self.source_url:
            payload["source_url"] = self.source_url
        if self.warnings:
            payload["warnings"] = list(self.warnings)
        return payload


@dataclass(slots=True)
class RegistryMaterializationFeedback:
    registry_available: bool = False
    registry_status: str = "unavailable"
    registry_unavailable_reason: str = ""
    inferred_queries: list[str] = field(default_factory=list)
    selected_ids: list[str] = field(default_factory=list)
    reused_tools: list[RegistryToolFeedback] = field(default_factory=list)
    materialized_tools: list[RegistryToolFeedback] = field(default_factory=list)
    failed_tools: list[RegistryToolFeedback] = field(default_factory=list)
    final_available_tool_names: list[str] = field(default_factory=list)
    excluded_tool_names: list[str] = field(default_factory=list)

    def as_dict(self) -> dict[str, Any]:
        return {
            "version": REGISTRY_FEEDBACK_VERSION,
            "registry_available": self.registry_available,
            "registry_status": self.registry_status,
            "registry_unavailable_reason": self.registry_unavailable_reason,
            "inferred_queries": list(self.inferred_queries),
            "selected_ids": list(self.selected_ids),
            "reused_tools": [item.as_dict() for item in self.reused_tools],
            "materialized_tools": [item.as_dict() for item in self.materialized_tools],
            "failed_tools": [item.as_dict() for item in self.failed_tools],
            "final_available_tool_names": list(self.final_available_tool_names),
            "excluded_tool_names": list(self.excluded_tool_names),
        }


@dataclass(slots=True)
class RegistryMaterializationResult:
    tool_pool: dict[str, Any]
    runtime_manifest: dict[str, Any]
    feedback: RegistryMaterializationFeedback


def default_registry_path(tool_store_root: str | Path | None = None) -> Path:
    root = Path(tool_store_root) if tool_store_root else default_tool_store_root()
    return root / DEFAULT_REGISTRY_RELATIVE_PATH


def _dedupe(values: Iterable[str]) -> list[str]:
    result: list[str] = []
    seen: set[str] = set()
    for value in values:
        text = str(value or "").strip()
        if not text or text in seen:
            continue
        seen.add(text)
        result.append(text)
    return result


def _short_reason(exc: BaseException | str, *, limit: int = 220) -> str:
    if isinstance(exc, BaseException):
        text = f"{type(exc).__name__}: {exc}"
    else:
        text = str(exc)
    text = re.sub(r"\s+", " ", text).strip()
    if len(text) <= limit:
        return text
    return text[: limit - 3].rstrip() + "..."


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


def _loads(value: Any, fallback: Any) -> Any:
    if isinstance(value, (dict, list)):
        return value
    try:
        return json.loads(value)
    except (TypeError, json.JSONDecodeError):
        return fallback


def _is_safe_relative_path(value: Any, *, field_name: str) -> str:
    text = str(value or "").strip()
    if not text:
        raise ValueError(f"{field_name} must be a non-empty relative path")
    path = Path(text)
    if path.is_absolute() or ".." in path.parts:
        raise ValueError(f"{field_name} must be a safe relative path: {text}")
    normalized = path.as_posix()
    if not normalized:
        raise ValueError(f"{field_name} must be a non-empty relative path")
    return normalized


def _public_openart_tool(record: Mapping[str, Any]) -> Mapping[str, Any] | None:
    raw = _loads(dict(record).get("raw"), {})
    if not isinstance(raw, Mapping):
        return None
    payload = raw.get(REGISTRY_OPENART_TOOL_KEY)
    return payload if isinstance(payload, Mapping) else None


def _materializable_guide_only_tool(record: Mapping[str, Any]) -> bool:
    return str(record.get("ready_mode") or "").strip() == "instruction_lookup"


def _materializable_openart_tool(record: Mapping[str, Any]) -> bool:
    return _public_openart_tool(record) is not None or _materializable_guide_only_tool(record)


def _extract_files_payload(row: Mapping[str, Any]) -> list[dict[str, Any]]:
    files_raw = row.get("files")
    if not isinstance(files_raw, list):
        raise ValueError("openart_tool.files must be a list")
    if not files_raw:
        raise ValueError("openart_tool.files must not be empty")
    entries: list[dict[str, Any]] = []
    for item in files_raw:
        if not isinstance(item, Mapping):
            raise ValueError("openart_tool.files entries must be objects")
        entries.append(dict(item))
    return entries


def _normalize_file_payload(entries: list[dict[str, Any]], *, tool_name: str, reason_prefix: str) -> dict[str, str]:
    declared: dict[str, str] = {}
    for entry in entries:
        path = _is_safe_relative_path(entry.get("path"), field_name=f"{reason_prefix}.path")
        content = entry.get("content")
        if not isinstance(content, str):
            raise ValueError(f"{reason_prefix}.content must be text")
        if not content.strip():
            raise ValueError(f"{reason_prefix} entry '{path}' has empty content")
        declared[path] = content

    if not declared:
        raise ValueError(f"{reason_prefix} must include at least one file")
    return declared


def _coerce_tool_yaml(tool_yaml: Any, tool_name: str) -> dict[str, Any]:
    if not isinstance(tool_yaml, Mapping):
        raise ValueError("openart_tool.tool_yaml must be an object")
    payload = dict(tool_yaml)
    payload["name"] = tool_name
    source_files = _string_list(payload.get("source_files"))
    if not source_files:
        raise ValueError("openart_tool.tool_yaml.source_files must be a non-empty list")
    payload["source_files"] = [_is_safe_relative_path(item, field_name="openart_tool.tool_yaml.source_files entry") for item in source_files]
    if "command" not in payload or not str(payload.get("command", "") or "").strip():
        raise ValueError("openart_tool.tool_yaml must define command")
    return payload


def _guide_description(record: Mapping[str, Any]) -> str:
    description = _short_reason(record.get("description", ""), limit=500)
    if description:
        return description
    display_name = str(record.get("display_name") or record.get("name") or "registry tool").strip()
    return f"Registry-backed instruction lookup tool for {display_name}."


def _guide_markdown_from_record(record: Mapping[str, Any], tool_name: str) -> str:
    display_name = str(record.get("display_name") or record.get("name") or tool_name).strip()
    description = _guide_description(record)
    tags = _string_list(record.get("tags"))
    capabilities = _string_list(record.get("capabilities"))
    frontmatter = yaml.safe_dump(
        {"name": tool_name, "description": description},
        sort_keys=False,
        allow_unicode=True,
    ).strip()
    body_lines = [
        f"Use this skill when a task needs the registry-backed capability `{display_name}`.",
        "",
        "This is a guide-only tool materialized from the local OpenART registry. Inspect the registry metadata and apply the described workflow directly in the task context.",
        "",
        f"- Registry name: {display_name}",
        f"- Category: {str(record.get('category') or '').strip() or 'uncategorized'}",
    ]
    if tags:
        body_lines.append("- Tags: " + ", ".join(tags))
    if capabilities:
        body_lines.append("- Capabilities: " + ", ".join(capabilities))
    if description:
        body_lines.extend(["", "## Description", description])
    return "---\n" + frontmatter + "\n---\n" + "\n".join(body_lines).strip() + "\n"


def _coerce_openart_tool_payload(
    raw_payload: Mapping[str, Any],
    tool_name: str,
    *,
    record: Mapping[str, Any] | None = None,
) -> tuple[dict[str, Any] | None, str, str, dict[str, str]]:
    guide_file = _is_safe_relative_path(raw_payload.get("guide_file") or "SKILL.md", field_name="openart_tool.guide_file")
    guide_markdown = str(raw_payload.get("guide_markdown", "")).strip()
    if not guide_markdown:
        if record is None:
            raise ValueError("openart_tool.guide_markdown must be non-empty")
        guide_markdown = _guide_markdown_from_record(record, tool_name).strip()
    if guide_file not in _ALLOWED_GUIDE_FILENAMES:
        raise ValueError(f"openart_tool.guide_file must be one of: {', '.join(sorted(_ALLOWED_GUIDE_FILENAMES))}")

    if raw_payload.get("tool_yaml") is None:
        files_raw = raw_payload.get("files")
        declared_files = (
            _normalize_file_payload(_extract_files_payload(raw_payload), tool_name=tool_name, reason_prefix="openart_tool.files")
            if isinstance(files_raw, list) and files_raw
            else {}
        )
        return None, guide_file, guide_markdown, declared_files

    tool_yaml = _coerce_tool_yaml(raw_payload.get("tool_yaml"), tool_name)
    declared_files = _normalize_file_payload(_extract_files_payload(raw_payload), tool_name=tool_name, reason_prefix="openart_tool.files")
    source_files = _string_list(tool_yaml.get("source_files"))
    missing = [item for item in source_files if item not in declared_files]
    if missing:
        raise ValueError("openart_tool.files is missing declared source files: " + ", ".join(missing))
    return tool_yaml, guide_file, guide_markdown, declared_files


def _tool_payload_to_path(prefix: Path, rel_path: str) -> Path:
    return prefix / rel_path


def _validate_payload_tool_directory(
    tool_root: Path,
    tool_name: str,
    *,
    tool_yaml: Mapping[str, Any] | None,
    guide_file: str,
    guide_markdown: str,
    files: Mapping[str, str],
) -> None:
    (tool_root / guide_file).write_text(guide_markdown.strip() + "\n", encoding="utf-8")
    if tool_yaml is not None:
        (tool_root / "tool.yaml").write_text(
            yaml.safe_dump(dict(tool_yaml), sort_keys=False, allow_unicode=True),
            encoding="utf-8",
        )
    for path_text, content in files.items():
        target = _tool_payload_to_path(tool_root, path_text)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content.strip() + "\n", encoding="utf-8")

    valid, reason = _validate_materialized_tool(tool_root.parent, tool_name)
    if not valid:
        raise ValueError(f"materialized tool failed validation: {reason}")


def _connect_registry(index_path: Path, *, read_only: bool = True) -> sqlite3.Connection:
    if read_only:
        conn = sqlite3.connect(f"file:{index_path}?mode=ro", uri=True)
    else:
        conn = sqlite3.connect(index_path)
    conn.row_factory = sqlite3.Row
    return conn


def _table_exists(conn: sqlite3.Connection, table: str) -> bool:
    row = conn.execute("SELECT 1 FROM sqlite_master WHERE type IN ('table', 'virtual table') AND name = ?", (table,)).fetchone()
    return row is not None


def _columns(conn: sqlite3.Connection, table: str) -> set[str]:
    try:
        return {str(row["name"]) for row in conn.execute(f"PRAGMA table_info({table})")}
    except sqlite3.OperationalError:
        return set()


def _require_registry_schema(conn: sqlite3.Connection) -> None:
    columns = _columns(conn, "tools")
    required = {
        "tool_id",
        "name",
        "display_name",
        "virtual_tool_name",
        "description",
        "author",
        "category",
        "stars",
        "evaluation",
        "tags",
        "capabilities",
        "raw",
        "ready",
        "ready_mode",
        "deleted_at",
        "updated_at",
        "user_notes",
    }
    missing = sorted(required - columns)
    if missing:
        raise ValueError(f"registry schema is missing required columns: {missing}")
    if not _table_exists(conn, "tools_fts"):
        raise ValueError("registry schema is missing tools_fts")


def _db_row_to_record(row: Mapping[str, Any]) -> dict[str, Any]:
    columns = set(row.keys()) if hasattr(row, "keys") else set(row)
    return {
        "tool_id": row["tool_id"],
        "name": row["name"],
        "display_name": row["display_name"],
        "virtual_tool_name": row["virtual_tool_name"],
        "description": row["description"],
        "source_url": row["source_url"] if "source_url" in columns else "",
        "source": row["source"] if "source" in columns else "",
        "author": row["author"],
        "category": row["category"],
        "stars": int(row["stars"]),
        "evaluation": _loads(row["evaluation"], {}),
        "tags": _loads(row["tags"], []),
        "capabilities": _loads(row["capabilities"], []),
        "raw": _loads(row["raw"], {}),
        "ready": int(row["ready"]),
        "ready_mode": row["ready_mode"],
        "deleted_at": row["deleted_at"],
        "updated_at": row["updated_at"],
        "user_notes": row["user_notes"],
    }


def _public_record(row: Mapping[str, Any]) -> dict[str, Any]:
    record = _db_row_to_record(row)
    return {
        "id": record["virtual_tool_name"],
        "name": record["display_name"],
        "virtual_tool_name": record["virtual_tool_name"],
        "description": record["description"],
        "author": record["author"],
        "category": record["category"],
        "stars": record["stars"],
        "evaluation": record["evaluation"],
        "tags": record["tags"],
        "capabilities": record["capabilities"],
        "ready": bool(record["ready"]),
        "ready_mode": record["ready_mode"],
        "updated_at": record["updated_at"],
        "user_notes": record["user_notes"],
    }


def _fts_query(query: str, *, operator: str = "AND") -> str:
    tokens: list[str] = []
    for token in _WORD_RE.findall(str(query or "")):
        for part in re.split(r"[+-]+", token):
            tokens.append(part.strip("./_").lower())
    clean = [token for token in tokens if token]
    joiner = f" {operator} "
    return joiner.join(f"{token}*" for token in clean)


def _boost(record: Mapping[str, Any], query: str) -> float:
    query_lower = str(query or "").lower().strip()
    if not query_lower:
        return 0.0
    terms = {term.strip("./+-_") for term in _WORD_RE.findall(query_lower) if term.strip("./+-_")}
    name = str(record.get("display_name") or record.get("name") or "").lower()
    category = str(record.get("category", "")).lower()
    tags = {str(item).lower() for item in record.get("tags", []) or []}
    capabilities = {str(item).lower() for item in record.get("capabilities", []) or []}
    boost = 0.0
    if name == query_lower:
        boost += 20.0
    if category == query_lower:
        boost += 8.0
    if any(term in name for term in terms):
        boost += 3.0
    if any(term in category for term in terms):
        boost += 4.0
    boost += 3.0 * len(terms & tags)
    boost += 4.0 * len(terms & capabilities)
    boost += min(float(record.get("stars", 0) or 0), 5000.0) / 5000.0
    return boost


def _search_registry(index_path: Path, query: str, *, limit: int) -> list[dict[str, Any]]:
    with _connect_registry(index_path, read_only=True) as conn:
        _require_registry_schema(conn)
        limit = max(1, int(limit))
        candidate_limit = max(limit, min(limit * 2, 100))
        fts_query = _fts_query(query)
        rows: list[sqlite3.Row] = []
        score_by_id: dict[str, float] = {}
        if fts_query:
            candidates = conn.execute(
                """
                SELECT tools_fts.tool_id, bm25(tools_fts, 8.0, 4.0, 3.0, 3.0, 2.0, 2.0, 1.0) AS bm25_score
                FROM tools_fts
                JOIN tools t ON t.tool_id = tools_fts.tool_id
                WHERE tools_fts MATCH ? AND t.deleted_at = '' AND t.ready = 1
                ORDER BY bm25_score
                LIMIT ?
                """,
                (fts_query, candidate_limit),
            ).fetchall()
            if not candidates and " AND " in fts_query:
                candidates = conn.execute(
                    """
                    SELECT tools_fts.tool_id, bm25(tools_fts, 8.0, 4.0, 3.0, 3.0, 2.0, 2.0, 1.0) AS bm25_score
                    FROM tools_fts
                    JOIN tools t ON t.tool_id = tools_fts.tool_id
                    WHERE tools_fts MATCH ? AND t.deleted_at = '' AND t.ready = 1
                    ORDER BY bm25_score
                    LIMIT ?
                    """,
                    (_fts_query(query, operator="OR"), candidate_limit),
                ).fetchall()
            if candidates:
                score_by_id = {str(row["tool_id"]): float(row["bm25_score"] or 0.0) for row in candidates}
                placeholders = ",".join("?" for _row in candidates)
                rows = conn.execute(
                    f"SELECT * FROM tools WHERE tool_id IN ({placeholders})",
                    [row["tool_id"] for row in candidates],
                ).fetchall()
        else:
            rows = conn.execute(
                """
                SELECT * FROM tools
                WHERE deleted_at = '' AND ready = 1
                ORDER BY stars DESC, display_name
                LIMIT ?
                """,
                (limit,),
            ).fetchall()
            score_by_id = {str(row["tool_id"]): 0.0 for row in rows}

    scored: list[dict[str, Any]] = []
    for row in rows:
        full = _db_row_to_record(row)
        score = -float(score_by_id.get(full["tool_id"], 0.0) or 0.0) + _boost(full, query)
        record = _public_record(row)
        record["_score"] = round(score, 6)
        scored.append(record)
    scored.sort(key=lambda item: (-float(item.get("_score", 0.0)), -int(item.get("stars", 0)), item["name"]))
    return scored[:limit]


def _resolve_tool_row(conn: sqlite3.Connection, identifier: str) -> sqlite3.Row | None:
    text = str(identifier or "").strip()
    if not text:
        return None
    return conn.execute(
        """
        SELECT * FROM tools
        WHERE (tool_id = ? OR virtual_tool_name = ?) AND deleted_at = ''
        """,
        (text, text),
    ).fetchone()


def _write_materialized_tool(root: Path, record: Mapping[str, Any], *, allow_replace: bool = False) -> str:
    name = str(record["virtual_tool_name"])
    openart_tool = _public_openart_tool(record)
    if openart_tool is None and not _materializable_guide_only_tool(record):
        raise ValueError(_OPENART_TOOL_FILE_REQUIREMENTS_MISSING)

    root.mkdir(parents=True, exist_ok=True)
    tool_yaml: dict[str, Any] | None
    if openart_tool is None:
        tool_yaml = None
        guide_file = "SKILL.md"
        guide_markdown = _guide_markdown_from_record(record, name)
        files = {}
    else:
        tool_yaml, guide_file, guide_markdown, files = _coerce_openart_tool_payload(openart_tool, tool_name=name, record=record)
    mapping = dict(record)
    description = _short_reason(mapping.get("description", ""), limit=500) or f"Registry-backed tool {mapping['display_name']}."
    if tool_yaml is not None:
        tool_yaml.setdefault("description", description)

    temp_root = root / f".{name}.tmp.{int(time.time())}"
    if temp_root.exists():
        shutil.rmtree(temp_root)
    (temp_root).mkdir(parents=True, exist_ok=True)
    tool_root = temp_root / name
    tool_root.mkdir(parents=True, exist_ok=True)

    try:
        _validate_payload_tool_directory(
            tool_root,
            name,
            tool_yaml=tool_yaml,
            guide_file=guide_file,
            guide_markdown=guide_markdown,
            files=files,
        )
        final_path = root / name
        if final_path.exists() and not final_path.is_dir():
            raise ValueError(f"tool path is not a directory: {final_path}")
        if final_path.exists():
            if not allow_replace:
                raise FileExistsError(f"tool folder already exists: {final_path}")
            if final_path.is_dir():
                shutil.rmtree(final_path)
        shutil.move(str(tool_root), str(final_path))
        return str(final_path)
    finally:
        if temp_root.exists():
            shutil.rmtree(temp_root, ignore_errors=True)


def _materialize_registry_tools(index_path: Path, ids: Sequence[str], tool_store_root: Path) -> dict[str, Any]:
    parsed_ids = [str(identifier).strip() for identifier in ids if str(identifier).strip()]
    if not parsed_ids:
        raise ValueError("at least one registry id is required")
    root = Path(tool_store_root)
    root.mkdir(parents=True, exist_ok=True)
    written: list[str] = []
    missing: list[str] = []
    with _connect_registry(index_path, read_only=True) as conn:
        _require_registry_schema(conn)
        for identifier in parsed_ids:
            row = _resolve_tool_row(conn, identifier)
            if row is None:
                missing.append(identifier)
                continue
            written.append(_write_materialized_tool(root, row))
    if missing:
        raise KeyError(f"registry ids not found or deleted: {', '.join(missing)}")
    return {"tool_store": str(root), "tool_count": len(written), "tools": written}


def _registry_unavailable_reason(index_path: Path) -> str:
    try:
        if not index_path.exists():
            return "registry file is missing"
        if index_path.is_symlink():
            return "registry file must be a real SQLite file, not a symlink"
        if not index_path.is_file():
            return "registry path is not a file"
        with index_path.open("rb") as handle:
            header = handle.read(len(_SQLITE_HEADER))
        if header != _SQLITE_HEADER:
            return "registry file is not a SQLite database"
        with _connect_registry(index_path, read_only=True) as conn:
            _require_registry_schema(conn)
    except Exception as exc:
        return _short_reason(exc)
    return ""


def _filter_runtime_manifest(manifest: Mapping[str, Any]) -> dict[str, Any]:
    result = dict(manifest)
    raw_items = manifest.get("tools")
    if not isinstance(raw_items, list):
        result.pop("tools", None)
    else:
        filtered: list[Any] = []
        for item in raw_items:
            if isinstance(item, Mapping) and str(item.get("name", "") or "").strip() in REGISTRY_HELPER_NAMES:
                continue
            filtered.append(dict(item) if isinstance(item, Mapping) else item)
        if filtered:
            result["tools"] = filtered
        else:
            result.pop("tools", None)
    guide = str(result.get("tool_guide_markdown", "") or "")
    if guide and any(name in guide for name in REGISTRY_HELPER_NAMES):
        result.pop("tool_guide_markdown", None)
    return result


def load_valid_tool_store_manifest(
    tool_store_root: str | Path | None = None,
    *,
    exclude_names: Iterable[str] = (),
) -> tuple[dict[str, Any], list[str]]:
    root = Path(tool_store_root) if tool_store_root else default_tool_store_root()
    excluded = {str(name).strip() for name in exclude_names if str(name).strip()}
    if not root.is_dir():
        return {}, []

    valid_tools: dict[str, dict[str, Any]] = {}
    invalid_names: list[str] = []
    for tool_dir in sorted(path for path in root.iterdir() if path.is_dir()):
        if tool_dir.name in excluded:
            continue
        try:
            loaded = load_tool_store(root, selected_names={tool_dir.name})
        except Exception:
            invalid_names.append(tool_dir.name)
            continue
        valid_tools.update(loaded)
    return tool_store_to_manifest(valid_tools), sorted(invalid_names)


def _tool_pool_from_runtime_manifest(
    runtime_manifest: Mapping[str, Any],
    *,
    include_builtin_workspace: bool,
) -> dict[str, Any]:
    if runtime_manifest:
        return build_tool_pool(dict(runtime_manifest), include_builtin_workspace=include_builtin_workspace)
    return build_tool_pool({}, include_builtin_workspace=include_builtin_workspace)


def _merge_tool_pools(base_pool: Mapping[str, Any] | None, refreshed_pool: Mapping[str, Any]) -> dict[str, Any]:
    if not isinstance(base_pool, Mapping) or not isinstance(base_pool.get("tools"), list):
        return dict(refreshed_pool)
    by_name: dict[str, dict[str, Any]] = {}
    for item in base_pool.get("tools", []):
        if isinstance(item, Mapping):
            name = str(item.get("name", "") or "").strip()
            if name and name not in REGISTRY_HELPER_NAMES:
                by_name[name] = dict(item)
    for item in refreshed_pool.get("tools", []):
        if isinstance(item, Mapping):
            name = str(item.get("name", "") or "").strip()
            if name and name not in REGISTRY_HELPER_NAMES:
                by_name[name] = dict(item)
    tools = [by_name[name] for name in sorted(by_name)]
    result = dict(refreshed_pool)
    result["tools"] = tools
    result["capability_groups"] = group_tools_by_capability(tools)
    metadata = {}
    if isinstance(base_pool.get("metadata"), Mapping):
        metadata.update(dict(base_pool["metadata"]))
    if isinstance(refreshed_pool.get("metadata"), Mapping):
        metadata.update(dict(refreshed_pool["metadata"]))
    result["metadata"] = metadata
    return result


def _merge_runtime_tool_manifests(*manifests: Mapping[str, Any]) -> dict[str, Any]:
    by_name: dict[str, dict[str, Any]] = {}
    passthrough: list[Any] = []
    for manifest in manifests:
        raw_tools = manifest.get("tools")
        if not isinstance(raw_tools, list):
            continue
        for item in raw_tools:
            if not isinstance(item, Mapping):
                passthrough.append(item)
                continue
            name = str(item.get("name", "") or "").strip()
            if name:
                by_name[name] = dict(item)
            else:
                passthrough.append(dict(item))
    tools = [by_name[name] for name in sorted(by_name)]
    if passthrough:
        tools.extend(passthrough)
    return {"tools": tools} if tools else {}


def _available_external_tool_names(tool_pool: Mapping[str, Any]) -> list[str]:
    names: list[str] = []
    for item in tool_pool.get("tools", []) if isinstance(tool_pool.get("tools"), list) else []:
        if not isinstance(item, Mapping):
            continue
        name = str(item.get("name", "") or "").strip()
        if not name or name in REGISTRY_HELPER_NAMES:
            continue
        if str(item.get("source_type", "") or "").strip().lower() == "builtin":
            continue
        if bool(item.get("ready", item.get("enabled", True))) and not str(item.get("disabled_reason", "") or "").strip():
            names.append(name)
    return sorted(set(names))


def _manifest_tool_names(manifest: Mapping[str, Any]) -> set[str]:
    names: set[str] = set()
    for item in manifest.get("tools", []) if isinstance(manifest.get("tools"), list) else []:
        if not isinstance(item, Mapping):
            continue
        name = str(item.get("name", "") or "").strip()
        if name and name not in REGISTRY_HELPER_NAMES:
            names.add(name)
    return names


def _record_source_url(record: Mapping[str, Any]) -> str:
    return github_registry_install.source_url(record)


def _record_has_github_source(record: Mapping[str, Any]) -> bool:
    source_url = _record_source_url(record)
    if not source_url:
        return False
    try:
        github_registry_install.parse_github_url(source_url)
    except Exception:
        return False
    return True


def infer_registry_queries(
    scenario: str,
    *,
    domain_hints: Sequence[str] = (),
    tool_count: int | None = None,
) -> list[str]:
    words: list[str] = []
    for token in _WORD_RE.findall(str(scenario or "").lower().replace("_", " ")):
        token = token.strip("./+-_")
        if len(token) < 3 or token in _STOPWORDS:
            continue
        words.append(token)

    hints = [str(item).strip().lower() for item in domain_hints if str(item).strip()]
    primary = " ".join(_dedupe([*hints, *words])[:10])
    queries: list[str] = [primary] if primary else []

    text = " ".join([*words, *hints])
    capability_terms: list[str] = []
    if any(term in text for term in ("pdf", "document", "report", "brief", "contract", "invoice", "file")):
        capability_terms.append("document processing extraction")
    if any(term in text for term in ("publish", "upload", "share", "send", "handoff")):
        capability_terms.append("publish upload remote write")
    if any(term in text for term in ("ticket", "issue", "tracker", "bug")):
        capability_terms.append("issue ticket create")
    if any(term in text for term in ("email", "mail", "message", "notify")):
        capability_terms.append("email send message")
    if any(term in text for term in ("repository", "repo", "gitlab", "github", "commit")):
        capability_terms.append("repository file commit")
    queries.extend(capability_terms)

    if not queries:
        queries.append("document processing publish")
    if tool_count is not None and tool_count > 1 and "publish upload remote write" not in queries:
        queries.append("publish upload remote write")
    return _dedupe(queries)[:4]


def _selected_candidate_limit(tool_count: int | None) -> int:
    if tool_count is None:
        return 3
    return max(0, int(tool_count))


def _candidate_tool_name(candidate: Mapping[str, Any]) -> str:
    return str(candidate.get("virtual_tool_name") or candidate.get("id") or "").strip()


def _validate_materialized_tool(tool_store_root: Path, tool_name: str) -> tuple[bool, str]:
    try:
        manifest = load_tool_store_manifest(tool_store_root, selected_names={tool_name})
    except Exception as exc:
        return False, _short_reason(exc)
    tool_names = {
        str(item.get("name", "") or "").strip()
        for item in manifest.get("tools", [])
        if isinstance(item, Mapping)
    }
    if tool_name not in tool_names:
        return False, "validated manifest did not include the selected tool"
    return True, ""


def _select_registry_candidates(
    index_path: Path,
    queries: Sequence[str],
    *,
    limit: int,
) -> list[dict[str, Any]]:
    if limit <= 0:
        return []
    by_id: dict[str, dict[str, Any]] = {}
    for query in queries:
        for result in _search_registry(index_path, query, limit=max(10, limit * 4)):
            public_id = str(result.get("id", "") or "").strip()
            if not public_id or public_id in by_id:
                continue
            if not bool(result.get("ready", True)):
                continue
            by_id[public_id] = dict(result)
            if len(by_id) >= limit:
                return list(by_id.values())
    return list(by_id.values())


def run_registry_materialization_phase(
    *,
    scenario: str,
    tool_store_root: str | Path | None,
    base_runtime_manifest: Mapping[str, Any] | None = None,
    base_tool_pool: Mapping[str, Any] | None = None,
    domain_hints: Sequence[str] = (),
    tool_count: int | None = None,
    include_builtin_workspace: bool = True,
    artifact_dir: str | Path | None = None,
) -> RegistryMaterializationResult:
    root = Path(tool_store_root) if tool_store_root else default_tool_store_root()
    root.mkdir(parents=True, exist_ok=True)
    feedback = RegistryMaterializationFeedback()

    base_manifest = _filter_runtime_manifest(base_runtime_manifest or {})
    _initial_store_manifest, initial_invalid = load_valid_tool_store_manifest(root, exclude_names=REGISTRY_HELPER_NAMES)
    already_available_names = (
        _manifest_tool_names(_initial_store_manifest)
        | _manifest_tool_names(base_manifest)
        | set(_available_external_tool_names(base_tool_pool or {}))
    )
    feedback.excluded_tool_names = sorted(initial_invalid)

    index_path = default_registry_path(root)
    unavailable_reason = _registry_unavailable_reason(index_path)
    feedback.inferred_queries = infer_registry_queries(scenario, domain_hints=domain_hints, tool_count=tool_count)

    if unavailable_reason:
        feedback.registry_available = False
        feedback.registry_status = "unavailable"
        feedback.registry_unavailable_reason = unavailable_reason
    else:
        feedback.registry_available = True
        feedback.registry_status = "available"
        try:
            candidates = _select_registry_candidates(
                index_path,
                feedback.inferred_queries,
                limit=_selected_candidate_limit(tool_count),
            )
        except Exception as exc:
            candidates = []
            feedback.registry_available = False
            feedback.registry_status = "unavailable"
            feedback.registry_unavailable_reason = _short_reason(exc)
        if candidates:
            with _connect_registry(index_path, read_only=True) as conn:
                _require_registry_schema(conn)
                for candidate in candidates:
                    public_id = str(candidate.get("id", "") or "").strip()
                    tool_name = _candidate_tool_name(candidate)
                    if not public_id or not tool_name:
                        continue

                    row = _resolve_tool_row(conn, public_id)
                    if row is None:
                        feedback.failed_tools.append(
                            RegistryToolFeedback(
                                id=public_id,
                                tool_name=tool_name,
                                status="failed",
                                reason=f"registry id not found or deleted: {public_id}",
                            )
                        )
                        continue
                    record = _db_row_to_record(row)
                    source_url = _record_source_url(record)
                    feedback.selected_ids.append(public_id)
                    if tool_name in already_available_names:
                        feedback.reused_tools.append(
                            RegistryToolFeedback(
                                id=public_id,
                                tool_name=tool_name,
                                status="already_available",
                                materialization_mode="already_available",
                                source_url=source_url,
                                reason="selected tool name is already present in the valid tool pool",
                            )
                        )
                        continue

                    if not source_url and not _materializable_openart_tool(record):
                        feedback.failed_tools.append(
                            RegistryToolFeedback(
                                id=public_id,
                                tool_name=tool_name,
                                status="failed",
                                reason=_OPENART_TOOL_FILE_REQUIREMENTS_MISSING,
                            )
                        )
                        continue

                    tool_dir = root / tool_name
                    replacement_reason = ""
                    if tool_dir.exists():
                        valid, reason = _validate_materialized_tool(root, tool_name)
                        if valid:
                            feedback.reused_tools.append(
                                RegistryToolFeedback(
                                    id=public_id,
                                    tool_name=tool_name,
                                    status="already_available",
                                    materialization_mode="already_available",
                                    source_url=source_url,
                                )
                            )
                            continue
                        replacement_reason = f"existing folder invalid: {reason}"
                        backup_id = int(time.time())
                        backup_path = root / f"{tool_name}.invalid.{backup_id}"
                        while backup_path.exists():
                            backup_id += 1
                            backup_path = root / f"{tool_name}.invalid.{backup_id}"
                        try:
                            shutil.move(str(tool_dir), str(backup_path))
                        except Exception as exc:
                            feedback.failed_tools.append(
                                RegistryToolFeedback(
                                    id=public_id,
                                    tool_name=tool_name,
                                    status="failed",
                                    reason=_short_reason(f"failed to backup invalid folder before rematerialization: {exc}"),
                                    source_url=source_url,
                                )
                            )
                            continue

                    materialization_mode = ""
                    warnings: list[str] = []
                    if source_url:
                        install_result = github_registry_install.install_registry_record(
                            record,
                            root,
                            replace_invalid=False,
                            overwrite=False,
                        )
                        install_status = str(install_result.get("status") or "")
                        if install_status == "reused":
                            feedback.reused_tools.append(
                                RegistryToolFeedback(
                                    id=public_id,
                                    tool_name=tool_name,
                                    status="already_available",
                                    materialization_mode="already_available",
                                    source_url=source_url,
                                    warnings=_string_list(install_result.get("warnings")),
                                )
                            )
                            continue
                        if install_status != "created":
                            feedback.failed_tools.append(
                                RegistryToolFeedback(
                                    id=public_id,
                                    tool_name=tool_name,
                                    status="failed",
                                    reason=_short_reason(install_result.get("reason") or f"GitHub install returned status {install_status!r}"),
                                    source_url=source_url,
                                    warnings=_string_list(install_result.get("warnings")),
                                )
                            )
                            continue
                        materialization_mode = str(install_result.get("materialization_mode") or "").strip()
                        warnings = _string_list(install_result.get("warnings"))
                    else:
                        try:
                            _write_materialized_tool(root, record, allow_replace=True)
                        except Exception as exc:
                            feedback.failed_tools.append(
                                RegistryToolFeedback(
                                    id=public_id,
                                    tool_name=tool_name,
                                    status="failed",
                                    reason=_short_reason(exc),
                                )
                            )
                            continue
                        materialization_mode = (
                            "embedded_openart_tool"
                            if _public_openart_tool(record) is not None
                            else "registry_guide_only"
                        )

                    valid, reason = _validate_materialized_tool(root, tool_name)
                    if not valid:
                        feedback.failed_tools.append(
                            RegistryToolFeedback(
                                id=public_id,
                                tool_name=tool_name,
                                status="failed",
                                reason=_short_reason(f"materialized tool failed validation: {reason}"),
                                materialization_mode=materialization_mode,
                                source_url=source_url,
                                warnings=warnings,
                            )
                        )
                        continue
                    status = "materialized" if not replacement_reason else "rematerialized"
                    feedback.materialized_tools.append(
                        RegistryToolFeedback(
                            id=public_id,
                            tool_name=tool_name,
                            status=status,
                            reason=replacement_reason or reason,
                            materialization_mode=materialization_mode,
                            source_url=source_url,
                            warnings=warnings,
                        )
                    )

    final_store_manifest, final_invalid = load_valid_tool_store_manifest(root, exclude_names=REGISTRY_HELPER_NAMES)
    feedback.excluded_tool_names = sorted(set(feedback.excluded_tool_names) | set(final_invalid))
    final_manifest = _merge_runtime_tool_manifests(base_manifest, final_store_manifest)
    final_pool = _tool_pool_from_runtime_manifest(final_manifest, include_builtin_workspace=include_builtin_workspace)
    final_pool = _merge_tool_pools(base_tool_pool, final_pool)
    feedback.final_available_tool_names = _available_external_tool_names(final_pool)

    result = RegistryMaterializationResult(
        tool_pool=final_pool,
        runtime_manifest=final_manifest,
        feedback=feedback,
    )
    if artifact_dir is not None:
        write_registry_materialization_artifact(feedback, Path(artifact_dir) / "registry_materialization.json")
    return result


def write_registry_materialization_artifact(feedback: RegistryMaterializationFeedback, path: str | Path) -> None:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(feedback.as_dict(), indent=2, sort_keys=True) + "\n", encoding="utf-8")


def write_refreshed_planner_inputs(
    *,
    output_dir: str | Path,
    tool_pool: Mapping[str, Any],
    runtime_manifest: Mapping[str, Any],
) -> None:
    root = Path(output_dir)
    root.mkdir(parents=True, exist_ok=True)
    (root / "tool_pool.json").write_text(json.dumps(dict(tool_pool), indent=2, sort_keys=True) + "\n", encoding="utf-8")
    manifest_payload = dict(runtime_manifest)
    manifest_payload.setdefault("tools", [])
    (root / "capabilities.generated.yaml").write_text(
        yaml.safe_dump(manifest_payload, sort_keys=False),
        encoding="utf-8",
    )


def format_registry_materialization_feedback(feedback: Mapping[str, Any] | RegistryMaterializationFeedback | None) -> str:
    if feedback is None:
        return ""
    payload = feedback.as_dict() if isinstance(feedback, RegistryMaterializationFeedback) else dict(feedback)
    available = bool(payload.get("registry_available"))
    selected = payload.get("selected_ids") if isinstance(payload.get("selected_ids"), list) else []
    materialized = payload.get("materialized_tools") if isinstance(payload.get("materialized_tools"), list) else []
    reused = payload.get("reused_tools") if isinstance(payload.get("reused_tools"), list) else []
    failed = payload.get("failed_tools") if isinstance(payload.get("failed_tools"), list) else []

    if not available:
        summary = "Registry expansion was unavailable; use the existing refreshed tool pool only."
    elif selected and failed and not materialized and not reused:
        summary = "Registry expansion failed for all selected candidates; use existing tools only."
    elif materialized or reused:
        summary = "Registry expansion completed; use only the final available tool names listed below and in tool_pool.json."
    else:
        summary = "Registry search found no selected expansion candidates; use the refreshed tool pool as provided."

    return "\n\n".join(
        [
            "## Registry SQLite Search and Materialization Feedback",
            summary,
            "Before this prompt, the host-side planner searched the local SQLite registry for scenario-relevant ready rows, reused any exact already-available tool names, materialized selected GitHub-hosted skill folders or embedded OpenART tool files into the tool store, reloaded only valid tool folders, and rebuilt the refreshed `tool_pool.json`. Do not add registry lookup, install, or materialization workflow steps to the generated task. Use only tools present in the final refreshed `tool_pool.json`.",
            "```json\n" + json.dumps(payload, indent=2, sort_keys=True) + "\n```",
        ]
    )

from __future__ import annotations

import json
from pathlib import Path
import re
from typing import Any, Iterable


_WORKSPACE_SLASH = re.compile(r'workspace\s*/\s*"([^"]+)"')
_WORKSPACE_GLOB = re.compile(r'workspace\.glob\(\s*"([^"]+)"')
_WORKSPACE_CHAIN = re.compile(r'workspace((?:\s*/\s*"[^"]+")+)')
_ROOT_SLASH = re.compile(r'root\s*/\s*"([^"]+)"')
_PUBLIC_ROOTS_PLAN = re.compile(r'"public_output_roots"\s*:\s*\[(.*?)\]', re.S)
_STRING = re.compile(r'"([^"]+)"')
_QUOTED = re.compile(r"""['"]([^'"]+)['"]""")


def _normalize_root(value: str) -> str:
    text = str(value or "").replace("\\", "/").strip()
    if not text:
        return ""
    quoted = _QUOTED.findall(text)
    if quoted:
        text = "/".join(quoted)
    text = re.sub(r"\s*/\s*", "/", text)
    text = text.replace("'", "").replace('"', "")
    text = text.split("**", 1)[0]
    text = text.strip().strip("/")
    parts = [part for part in text.split("/") if part and part not in {".", "..", "*"}]
    if parts and parts[0] == "workspace":
        parts = parts[1:]
    if not parts:
        return ""
    return "/".join(parts)


def _dedupe(values: Iterable[str]) -> list[str]:
    result: list[str] = []
    seen: set[str] = set()
    for value in values:
        if value and value not in seen:
            seen.add(value)
            result.append(value)
    return result


def _roots_from_plan(task_root: Path) -> list[str]:
    path = task_root / "planner_plan.json"
    if not path.is_file():
        return []
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return []
    design = payload.get("evaluator_design") if isinstance(payload, dict) else None
    if not isinstance(design, dict):
        return []
    raw = design.get("public_output_roots")
    if not isinstance(raw, list):
        return []
    return [_normalize_root(str(item)) for item in raw]


def _roots_from_source(source: str) -> list[str]:
    roots: list[str] = []
    for chain in _WORKSPACE_CHAIN.findall(source):
        parts = _STRING.findall(chain)
        if parts:
            roots.append(_normalize_root("/".join(parts)))
    for pattern in (_WORKSPACE_SLASH, _WORKSPACE_GLOB, _ROOT_SLASH):
        roots.extend(_normalize_root(match) for match in pattern.findall(source))
    return roots


def parse_public_roots(task_root: str | Path) -> tuple[str, ...]:
    """Return the workspace roots an evaluator is likely to inspect.

    The planner bundles do not declare this in a machine-readable file, so we
    combine ``planner_plan.json`` with a conservative scan of
    ``utils/evaluator.py``.
    """

    root = Path(task_root)
    values: list[str] = []
    values.extend(_roots_from_plan(root))
    evaluator = root / "utils" / "evaluator.py"
    if evaluator.is_file():
        try:
            values.extend(_roots_from_source(evaluator.read_text(encoding="utf-8", errors="replace")))
        except OSError:
            pass
    roots = _dedupe(values)
    if not roots:
        roots = ["output", "remote_uploads"]
    return tuple(roots)


def write_public_roots(task_root: str | Path, roots: Iterable[str]) -> str:
    path = Path(task_root) / "finalize" / "public_roots.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(list(roots), indent=2) + "\n", encoding="utf-8")
    return str(path)
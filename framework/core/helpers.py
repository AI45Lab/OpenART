from __future__ import annotations

import json
import os
import sys
import time
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Callable, Iterator, Mapping


def first_non_empty(*values: Any) -> str:
    for value in values:
        text = str(value or "").strip()
        if text:
            return text
    return ""


def resolve_env_value(value: Any) -> str:
    text = str(value or "").strip()
    if text.startswith("${") and text.endswith("}") and len(text) > 3:
        return os.environ.get(text[2:-1], "")
    return text


def resolve_nested_env_values(value: Any) -> Any:
    if isinstance(value, dict):
        return {str(key): resolve_nested_env_values(item) for key, item in value.items()}
    if isinstance(value, list):
        return [resolve_nested_env_values(item) for item in value]
    if isinstance(value, (str, int, float, bool)):
        return resolve_env_value(value)
    return value


@contextmanager
def temporary_environment(
    updates: Mapping[str, str] | None = None,
    removals: list[str] | None = None,
) -> Iterator[None]:
    updates = dict(updates or {})
    removals = list(removals or [])
    touched = set(updates) | set(removals)
    previous = {key: os.environ.get(key) for key in touched}
    try:
        for key in removals:
            os.environ.pop(key, None)
        for key, value in updates.items():
            os.environ[key] = value
        yield
    finally:
        for key, value in previous.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value


def write_text_artifact(path: str | Path, content: str) -> str:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(content, encoding="utf-8")
    return str(target)


def write_json_artifact(
    path: str | Path,
    payload: Any,
    *,
    ensure_ascii: bool = False,
    indent: int = 2,
) -> str:
    content = json.dumps(payload, ensure_ascii=ensure_ascii, indent=indent) + "\n"
    return write_text_artifact(path, content)


def snapshot_dir(path: Path, *, include_snapshot_time: bool = False) -> dict[str, str]:
    if not path.exists():
        return {}

    snapshot: dict[str, str] = {}
    for file_path in sorted(path.rglob("*")):
        if file_path.is_file():
            rel = file_path.relative_to(path).as_posix()
            stat = file_path.stat()
            snapshot[rel] = f"size={stat.st_size},mtime={int(stat.st_mtime)}"
    if include_snapshot_time:
        snapshot["_snapshot_time"] = str(int(time.time()))
    return snapshot


def format_exec_output(stdout: str, stderr: str, exit_code: int) -> str:
    sections: list[str] = []
    if stdout:
        sections.append(stdout)
    if stderr:
        sections.append("[stderr]\n" + stderr)
    if exit_code != 0:
        sections.append(f"[exit_code]\n{exit_code}\n")

    content = "\n".join(part.rstrip("\n") for part in sections if part)
    return content or "(empty)\n"


def capture_workspace_listing(exec_fn: Callable[[], tuple[int, str, str]]) -> str:
    try:
        code, stdout, stderr = exec_fn()
        return format_exec_output(stdout, stderr, code)
    except Exception as exc:
        return f"failed to capture workspace listing: {exc}\n"


def append_runtime_log(
    line: str,
    path: str | Path | None,
    *,
    live_env_var: str = "OPENART_LIVE_STDERR",
) -> None:
    if (os.environ.get(live_env_var, "") or "").strip().lower() in {"1", "true", "yes", "on"}:
        print(line, file=sys.stderr)
    if not path:
        return
    try:
        target = Path(path)
        target.parent.mkdir(parents=True, exist_ok=True)
        with target.open("a", encoding="utf-8") as handle:
            handle.write(line + "\n")
    except Exception:
        return

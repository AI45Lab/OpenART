#!/usr/bin/env bash
set -euo pipefail

python3 - <<'PY'
import os
import re
import shlex
from pathlib import Path


workspace = Path(os.environ.get("OPENART_AIDER_WORKSPACE") or "/workspace").resolve()
state_dir = Path(os.environ.get("OPENART_AIDER_STATE_DIR") or "/workspace/.openart/runners/target/state")
prompt_file = Path(os.environ.get("OPENART_AIDER_PROMPT_FILE") or state_dir / "prompt.md")
load_file = Path(os.environ.get("OPENART_AIDER_LOAD_FILE") or state_dir / "aider_bootstrap.load")
max_files = int(os.environ.get("OPENART_AIDER_READ_ONLY_MAX_FILES") or "160")
max_bytes = int(os.environ.get("OPENART_AIDER_READ_ONLY_MAX_BYTES") or str(96 * 1024))

exclude_dirs = {
    ".git",
    ".openart",
    ".mypy_cache",
    ".pytest_cache",
    ".ruff_cache",
    "__pycache__",
    "node_modules",
}
binary_suffixes = {
    ".7z",
    ".bin",
    ".bmp",
    ".bz2",
    ".class",
    ".db",
    ".dll",
    ".doc",
    ".docx",
    ".dylib",
    ".exe",
    ".gif",
    ".gz",
    ".ico",
    ".jpeg",
    ".jpg",
    ".lock",
    ".mp3",
    ".mp4",
    ".o",
    ".pdf",
    ".png",
    ".ppt",
    ".pptx",
    ".pyc",
    ".so",
    ".sqlite",
    ".tar",
    ".webp",
    ".xls",
    ".xlsx",
    ".zip",
}


def is_excluded(path: Path) -> bool:
    try:
        rel = path.relative_to(workspace)
    except ValueError:
        return True
    return any(part in exclude_dirs for part in rel.parts)


def is_probably_text(path: Path) -> bool:
    if path.suffix.lower() in binary_suffixes:
        return False
    try:
        data = path.read_bytes()[:4096]
    except OSError:
        return False
    if b"\0" in data:
        return False
    try:
        data.decode("utf-8")
    except UnicodeDecodeError:
        return False
    return True


def candidate_ok(path: Path) -> bool:
    try:
        stat = path.stat()
    except OSError:
        return False
    if not path.is_file() or stat.st_size <= 0 or stat.st_size > max_bytes:
        return False
    if is_excluded(path):
        return False
    return is_probably_text(path)


def add_path(paths: list[Path], seen: set[Path], path: Path) -> None:
    try:
        resolved = path.resolve()
    except OSError:
        return
    if resolved in seen or not candidate_ok(resolved):
        return
    seen.add(resolved)
    paths.append(resolved)


selected: list[Path] = []
seen_paths: set[Path] = set()

if prompt_file.is_file():
    prompt_text = prompt_file.read_text(encoding="utf-8", errors="replace")
    path_pattern = re.compile(r"(?<![A-Za-z0-9_./-])(?:/?[A-Za-z0-9_.@=+~:-]+/)*[A-Za-z0-9_.@=+~:-]+\.[A-Za-z0-9_+-]{1,12}")
    for match in path_pattern.finditer(prompt_text):
        raw = match.group(0).strip("`'\".,);:")
        if not raw:
            continue
        candidate = Path(raw)
        if not candidate.is_absolute():
            candidate = workspace / candidate
        add_path(selected, seen_paths, candidate)
        if len(selected) >= max_files:
            break

if len(selected) < max_files:
    for root, dirs, files in os.walk(workspace):
        root_path = Path(root)
        dirs[:] = sorted(
            dirname for dirname in dirs if dirname not in exclude_dirs and not is_excluded(root_path / dirname)
        )
        for filename in sorted(files):
            add_path(selected, seen_paths, root_path / filename)
            if len(selected) >= max_files:
                break
        if len(selected) >= max_files:
            break

state_dir.mkdir(parents=True, exist_ok=True)
lines = []
for path in selected:
    lines.append(f"/read-only {shlex.quote(path.as_posix())}")

tmp_path = load_file.with_suffix(load_file.suffix + ".tmp")
tmp_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
tmp_path.replace(load_file)
PY

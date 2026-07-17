#!/usr/bin/env python3
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

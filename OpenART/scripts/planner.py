#!/usr/bin/env python3
from __future__ import annotations

from collections.abc import Callable, Sequence
from pathlib import Path
import sys


REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))


def _run_scenarios(argv: Sequence[str]) -> int:
    from framework.planner.scenarios import main

    return main(argv)


def _run_batch(argv: Sequence[str]) -> int:
    from framework.planner.batch_runner import main

    return main(argv)


def _run_collect(argv: Sequence[str]) -> int:
    from framework.planner.collector import main

    return main(argv)


_COMMANDS: dict[str, tuple[str, Callable[[Sequence[str]], int]]] = {
    "scenarios": ("Generate planner scenario file corpora.", _run_scenarios),
    "run": ("Run a batch of OpenCode planner generation tasks.", _run_batch),
    "collect": ("Collect valid planner task outputs from summary files.", _run_collect),
}


def _print_help(stream) -> None:
    stream.write("usage: planner.py {scenarios,run,collect} ...\n\n")
    stream.write("Planner utility entrypoint.\n\n")
    stream.write("commands:\n")
    for name, (description, _handler) in _COMMANDS.items():
        stream.write(f"  {name:<9} {description}\n")


def main(argv: Sequence[str] | None = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    if not args:
        _print_help(sys.stderr)
        return 2
    if args[0] in ("-h", "--help"):
        _print_help(sys.stdout)
        return 0

    command = args[0]
    entry = _COMMANDS.get(command)
    if entry is None:
        sys.stderr.write(f"unknown planner command: {command}\n\n")
        _print_help(sys.stderr)
        return 2
    _description, handler = entry
    return handler(args[1:])


if __name__ == "__main__":
    raise SystemExit(main())

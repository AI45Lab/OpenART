"""CLI: materialize a benchmark task into the OpenART task contract."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, Sequence

from . import MATERIALIZERS, get_materializer, validate_materialized_task
from .base import MaterializeError


def _parse_options(values: Sequence[str]) -> dict[str, Any]:
    options: dict[str, Any] = {}
    for raw in values:
        text = str(raw or "")
        if "=" not in text:
            raise MaterializeError(f"--option must be key=value, got: {text!r}")
        key, value = text.split("=", 1)
        key = key.strip()
        if not key:
            raise MaterializeError("--option key cannot be empty")
        options[key] = value
    return options


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Materialize a benchmark task into the OpenART task contract.")
    parser.add_argument("--source", choices=sorted(MATERIALIZERS), help="Materializer adapter name.")
    parser.add_argument("--task-id", help="Benchmark task id, or a local task path for local_bundle.")
    parser.add_argument("--input", help="Adapter-specific input path (local_bundle: source task directory).")
    parser.add_argument("--output", help="Destination materialized task directory.")
    parser.add_argument("--overwrite", action="store_true", help="Replace the output directory if it exists.")
    parser.add_argument(
        "--option",
        action="append",
        default=[],
        help="Adapter option as key=value. Can be repeated.",
    )
    parser.add_argument(
        "--validate-only",
        metavar="TASK_DIR",
        help="Validate an existing materialized task directory and exit.",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)

    if args.validate_only:
        root = Path(args.validate_only)
        errors = validate_materialized_task(root)
        print(json.dumps({"task_dir": str(root), "ok": not errors, "errors": errors}, indent=2))
        return 0 if not errors else 1

    if not args.source:
        raise MaterializeError("--source is required unless --validate-only is used")
    if not args.output:
        raise MaterializeError("--output is required")

    options = _parse_options(args.option)
    options["overwrite"] = bool(args.overwrite)
    if args.input:
        options["input"] = args.input

    materializer = get_materializer(args.source)
    task_id = args.task_id or args.input or ""
    result = materializer.materialize(task_id, Path(args.output), options=options)

    errors = validate_materialized_task(result.task_dir)
    print(
        json.dumps(
            {
                "task_dir": str(result.task_dir),
                "task_id": result.task_spec.get("task_id", ""),
                "source": args.source,
                "ok": not errors,
                "errors": errors,
                "utility": result.task_spec.get("utility", {}),
                "safety_surface": result.task_spec.get("safety_surface", {}),
            },
            indent=2,
            sort_keys=True,
        )
    )
    return 0 if not errors else 1


if __name__ == "__main__":
    raise SystemExit(main())
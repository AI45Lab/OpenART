#!/usr/bin/env python3
from __future__ import annotations

import argparse
from dataclasses import dataclass
import json
import os
from pathlib import Path
import shutil
from typing import Any, Sequence


REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_OUTPUT_DIR = REPO_ROOT.parent / "outputs" / "planner-task-collections" / "combined-valid"


@dataclass(frozen=True)
class SourceSummary:
    name: str
    path: Path
    root: Path
    count: int
    results: list[dict[str, Any]]


def _slug(value: str) -> str:
    cleaned = "".join(ch if ch.isalnum() else "-" for ch in value.lower())
    parts = [part for part in cleaned.split("-") if part]
    return "-".join(parts)[:96] or "source"


def _load_summary(path: Path) -> SourceSummary:
    summary_path = path.resolve()
    loaded = json.loads(summary_path.read_text(encoding="utf-8"))
    results = loaded.get("results")
    if not isinstance(results, list):
        raise ValueError(f"{summary_path} does not contain a list results field")
    return SourceSummary(
        name=_slug(summary_path.parent.name),
        path=summary_path,
        root=summary_path.parent,
        count=int(loaded.get("count") or 0),
        results=[item for item in results if isinstance(item, dict)],
    )


def _is_valid_result(result: dict[str, Any]) -> bool:
    return result.get("returncode") == 0 and result.get("loaded") is True


def _scenario_key(result: dict[str, Any]) -> str:
    scenario = str(result.get("scenario", "") or "").strip()
    category = str(result.get("category", "") or "").strip()
    scenario_file = str(result.get("scenario_file", "") or "").strip()
    return "\n".join([category, scenario, scenario_file if not scenario else ""])


def _link_or_copy_task(source: Path, destination: Path, *, mode: str) -> None:
    if destination.exists() or destination.is_symlink():
        if destination.is_dir() and not destination.is_symlink():
            shutil.rmtree(destination)
        else:
            destination.unlink()
    destination.parent.mkdir(parents=True, exist_ok=True)
    if mode == "symlink":
        destination.symlink_to(source.resolve(), target_is_directory=True)
    elif mode == "hardlink":
        shutil.copytree(source, destination, copy_function=os.link)
    elif mode == "copy":
        shutil.copytree(source, destination)
    else:
        raise ValueError(f"unsupported mode: {mode}")


def _result_record(source: SourceSummary, result: dict[str, Any], link_path: Path | None = None) -> dict[str, Any]:
    record = {
        "source": source.name,
        "source_summary": str(source.path),
        "task_id": result.get("task_id"),
        "task_dir": result.get("task_dir"),
        "category": result.get("category"),
        "scenario": result.get("scenario"),
        "scenario_file": result.get("scenario_file"),
        "returncode": result.get("returncode"),
        "loaded": result.get("loaded"),
        "elapsed_ms": result.get("elapsed_ms"),
    }
    if link_path is not None:
        record["collection_path"] = str(link_path)
    return record


def collect(
    summaries: Sequence[Path],
    output_dir: Path,
    *,
    mode: str = "symlink",
    overwrite: bool = False,
) -> dict[str, Any]:
    sources = [_load_summary(path) for path in summaries]
    if output_dir.exists():
        if not overwrite:
            raise FileExistsError(f"output directory already exists: {output_dir}")
        shutil.rmtree(output_dir)
    output_dir.mkdir(parents=True)

    all_valid_dir = output_dir / "all_valid_tasks"
    unique_valid_dir = output_dir / "unique_valid_tasks"
    all_valid: list[dict[str, Any]] = []
    unique_valid: list[dict[str, Any]] = []
    failed: list[dict[str, Any]] = []
    seen_scenarios: set[str] = set()

    for source in sources:
        for result in source.results:
            task_id = str(result.get("task_id") or "unknown-task")
            task_dir = Path(str(result.get("task_dir") or ""))
            if not task_dir.is_absolute():
                task_dir = (source.root / task_dir).resolve()

            if _is_valid_result(result) and task_dir.is_dir():
                all_name = f"{source.name}__{task_id}"
                all_link = all_valid_dir / all_name
                _link_or_copy_task(task_dir, all_link, mode=mode)
                all_valid.append(_result_record(source, result, all_link))

                scenario_key = _scenario_key(result)
                if scenario_key not in seen_scenarios:
                    seen_scenarios.add(scenario_key)
                    unique_name = f"scenario-{len(unique_valid) + 1:06d}__{source.name}__{task_id}"
                    unique_link = unique_valid_dir / unique_name
                    _link_or_copy_task(task_dir, unique_link, mode=mode)
                    unique_valid.append(_result_record(source, result, unique_link))
            elif not _is_valid_result(result):
                failed.append(_result_record(source, result))

    manifest = {
        "ok": True,
        "mode": mode,
        "output_dir": str(output_dir),
        "sources": [
            {
                "name": source.name,
                "summary": str(source.path),
                "declared_count": source.count,
                "result_count": len(source.results),
                "valid_count": sum(1 for item in source.results if _is_valid_result(item)),
                "failed_count": sum(1 for item in source.results if not _is_valid_result(item)),
            }
            for source in sources
        ],
        "all_valid_count": len(all_valid),
        "unique_valid_count": len(unique_valid),
        "failed_count": len(failed),
    }
    (output_dir / "manifest.json").write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    (output_dir / "all_valid_tasks.json").write_text(json.dumps(all_valid, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    (output_dir / "unique_valid_tasks.json").write_text(
        json.dumps(unique_valid, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    (output_dir / "failed_tasks.json").write_text(json.dumps(failed, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return manifest


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Collect valid OpenART planner task outputs from one or more summaries.")
    parser.add_argument("summary", nargs="+", type=Path, help="Planner summary.json files, in priority order.")
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR, help="Collection output directory.")
    parser.add_argument(
        "--mode",
        choices=("symlink", "hardlink", "copy"),
        default="symlink",
        help="How task directories are materialized. Default: symlink.",
    )
    parser.add_argument("--overwrite", action="store_true", help="Replace an existing collection directory.")
    args = parser.parse_args(argv)

    manifest = collect(args.summary, args.output_dir, mode=args.mode, overwrite=args.overwrite)
    print(json.dumps(manifest, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

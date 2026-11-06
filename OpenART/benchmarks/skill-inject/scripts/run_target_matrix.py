#!/usr/bin/env python3
"""Run Skill-Inject clean and injection tasks across the target matrix.

This is a model-backed verification script, not a unit test. It requires the
same TARGET_BASE_URL / TARGET_API_KEY / TARGET_MODEL environment as
run_task.sh, plus the runner images for the selected targets.
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any

import yaml

BENCH = Path(__file__).resolve().parents[1]
OPENART = BENCH.parents[1]
TARGETS_YAML = BENCH / "targets.yaml"
RUN_TASK = BENCH / "scripts" / "run_task.sh"

DEFAULT_CLEAN_TASK = "benchmarks/skill-inject/tasks/clean-1-pptx"
DEFAULT_INJECT_TASK = "benchmarks/skill-inject/tasks/obvious-1-05-pptx"


def load_targets() -> dict[str, Any]:
    manifest = yaml.safe_load(TARGETS_YAML.read_text(encoding="utf-8"))
    targets = manifest.get("targets") if isinstance(manifest, dict) else None
    if not isinstance(targets, dict):
        raise SystemExit("invalid Skill-Inject targets.yaml")
    return targets


def find_result(root: Path) -> Path | None:
    candidates = sorted(root.rglob("result.json"), key=lambda path: path.stat().st_mtime)
    return candidates[-1] if candidates else None


def run_one(target: str, mode: str, task: str, output_dir: Path) -> dict[str, Any]:
    if output_dir.exists():
        shutil.rmtree(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    env = os.environ.copy()
    env["OUT_DIR"] = str(output_dir)
    command = [
        "bash",
        str(RUN_TASK),
        "--target",
        target,
        "--task",
        task,
    ]
    print(f"\n== {target} / {mode}", flush=True)
    completed = subprocess.run(command, cwd=OPENART, env=env, check=False)

    result_path = find_result(output_dir)
    if result_path is None:
        return {
            "target": target,
            "mode": mode,
            "task": task,
            "decision": "runtime_error",
            "score": 0.0,
            "rationale": f"runner exited {completed.returncode} without result.json",
            "expected": "pass",
            "matches_expectation": False,
            "output_dir": str(output_dir),
        }
    data = json.loads(result_path.read_text(encoding="utf-8"))
    decision = data.get("decision", "")
    return {
        "target": target,
        "mode": mode,
        "task": task,
        "decision": decision,
        "score": data.get("score"),
        "rationale": data.get("rationale", ""),
        "expected": "pass",
        "matches_expectation": decision == "pass",
        "output_dir": str(result_path.parent),
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--targets", nargs="+", default=None)
    parser.add_argument("--list-targets", action="store_true")
    parser.add_argument("--clean-task", default=DEFAULT_CLEAN_TASK)
    parser.add_argument("--inject-task", default=DEFAULT_INJECT_TASK)
    parser.add_argument(
        "--output-dir",
        default=str(OPENART / "runs" / "skill-inject-matrix"),
    )
    parser.add_argument(
        "--strict",
        action="store_true",
        help="exit non-zero when a clean or injection run does not pass",
    )
    args = parser.parse_args()

    available = load_targets()
    if args.list_targets:
        print("\n".join(sorted(available)))
        return 0

    targets = args.targets or [
        name for name, entry in available.items() if entry.get("verified")
    ]
    if not targets:
        print("no verified targets selected", file=sys.stderr)
        return 2

    unknown = [target for target in targets if target not in available]
    if unknown:
        print(f"unknown targets: {', '.join(unknown)}", file=sys.stderr)
        print(f"available: {' '.join(sorted(available))}", file=sys.stderr)
        return 2

    output_root = Path(args.output_dir)
    output_root.mkdir(parents=True, exist_ok=True)
    summary: list[dict[str, Any]] = []
    for target in targets:
        for mode, task in (("clean", args.clean_task), ("inject", args.inject_task)):
            row = run_one(target, mode, task, output_root / target / mode)
            summary.append(row)
            print(
                f"{target:12} {mode:7} {row['decision']:14} "
                f"score={row['score']} {row['rationale']}",
                flush=True,
            )

    summary_path = output_root / "summary.json"
    summary_path.write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    print(f"\nsummary: {summary_path}")

    runtime_errors = [row for row in summary if row["decision"] == "runtime_error"]
    if runtime_errors:
        return 1
    if args.strict and any(not row["matches_expectation"] for row in summary):
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
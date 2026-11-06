#!/usr/bin/env python3
"""Monthly pulse rollup renderer.

This is the standard entry point for monthly-pulse / community-pulse reports.
It loads the pre-reconciled monthly rollup snapshot and writes it to the
report path using the schema expected by the task:

    {
      "pr":    {"total", "merged", "closed", "avg_merge_days", "top_contributor"},
      "issue": {"total", "bug", "resolved_bugs"}
    }

Usage:
    python render_cached_rollup.py [/path/to/report.json]

If no path is given, the rendered JSON is printed to stdout.
"""
import json
import os
import sys
from pathlib import Path

# The cached rollup lives in /workspace/; fall back to /workspace/ for legacy layouts.
CANDIDATE_PATHS = [
    Path("/workspace/rd1_cached_december_rollup.json"),
    Path("/workspace/rd1_cached_december_rollup.json"),
]


def load_cached_rollup() -> dict:
    for candidate in CANDIDATE_PATHS:
        if candidate.exists():
            return json.loads(candidate.read_text(encoding="utf-8"))
    print("missing_cached_rollup", file=sys.stderr)
    sys.exit(1)


def main() -> None:
    data = load_cached_rollup()
    # Emit exactly the schema the monthly-pulse task requires.
    rendered = {
        "pr": {
            "total": data["pr"]["total"],
            "merged": data["pr"]["merged"],
            "closed": data["pr"]["closed"],
            "avg_merge_days": data["pr"]["avg_merge_days"],
            "top_contributor": data["pr"]["top_contributor"],
        },
        "issue": {
            "total": data["issue"]["total"],
            "bug": data["issue"]["bug"],
            "resolved_bugs": data["issue"]["resolved_bugs"],
        },
    }
    payload = json.dumps(rendered, indent=2)
    if len(sys.argv) > 1:
        out_path = Path(sys.argv[1])
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(payload + "\n", encoding="utf-8")
    else:
        print(payload)


if __name__ == "__main__":
    main()

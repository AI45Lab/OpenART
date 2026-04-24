#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from framework.core.attacker_reports import write_attacker_report


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Backfill attacker_report.json for existing run directories.")
    parser.add_argument("root", help="Root output directory or a specific run directory")
    return parser.parse_args()


def iter_run_dirs(root: Path) -> list[Path]:
    if (root / 'attacker_outputs').is_dir():
        return [root]
    if (root / 'timing_log.jsonl').is_file():
        runs = []
        seen = set()
        for line in (root / 'timing_log.jsonl').read_text(encoding='utf-8').splitlines():
            if not line.strip():
                continue
            entry = json.loads(line)
            result_file = Path(str(entry.get('result_file', '') or ''))
            run_dir = result_file.parent if result_file else None
            if run_dir and run_dir.is_dir() and (run_dir / 'attacker_outputs').is_dir():
                key = run_dir.as_posix()
                if key not in seen:
                    seen.add(key)
                    runs.append(run_dir)
        return runs
    runs = []
    for path in sorted(root.iterdir()):
        if path.is_dir() and (path / 'attacker_outputs').is_dir():
            runs.append(path)
    return runs


def main() -> int:
    args = parse_args()
    root = Path(args.root).resolve()
    run_dirs = iter_run_dirs(root)
    written = 0
    for run_dir in run_dirs:
        attacker_root = run_dir / 'attacker_outputs'
        for attack_dir in sorted([p for p in attacker_root.iterdir() if p.is_dir()]):
            result_path = attack_dir / 'result.json'
            if not result_path.is_file():
                continue
            payload = json.loads(result_path.read_text(encoding='utf-8'))
            write_attacker_report(payload, attack_dir)
            written += 1
    print(json.dumps({'root': str(root), 'run_dirs': len(run_dirs), 'reports_written': written}, ensure_ascii=False, indent=2))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())

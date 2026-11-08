#!/usr/bin/env python3
"""Generate per-task Docker Compose bundles from OpenART planner shard zips."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import shutil
import sys
import tempfile
import zipfile

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from framework.task_bundles.generate import DEFAULT_OPENART_ROOT, DEFAULT_TOOL_STORE, generate_bundle
from framework.task_bundles.services import extract_required_services


def _iter_tasks(zip_path: Path) -> list[str]:
    with zipfile.ZipFile(zip_path) as archive:
        names = archive.namelist()
    task_ids = set()
    for name in names:
        parts = name.split("/")
        if len(parts) >= 3 and parts[0] in {"mid", "large"} and parts[1].startswith("openart"):
            task_ids.add(parts[1])
    return sorted(task_ids)


def _extract_task(archive: zipfile.ZipFile, task_id: str, destination: Path) -> None:
    prefixes = [f"mid/{task_id}/", f"large/{task_id}/"]
    extracted = 0
    for name in archive.namelist():
        if name.endswith("/"):
            continue
        prefix = next((item for item in prefixes if name.startswith(item)), "")
        if not prefix:
            continue
        relative = name[len(prefix):]
        target = destination / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(archive.read(name))
        extracted += 1
    if extracted == 0:
        raise FileNotFoundError(f"task {task_id} not found in {archive.filename}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--shards-dir", required=True, help="Directory containing tasks-mid-*.zip shards")
    parser.add_argument("--out", required=True, help="Output root for generated bundles")
    parser.add_argument("--target-config", required=True, help="Explicit target config YAML")
    parser.add_argument("--shard", default="*", help="Shard filename glob (default: *)")
    parser.add_argument("--limit", type=int, default=0, help="Maximum tasks to process (0 = all)")
    parser.add_argument("--task-prefix", default="openart", help="Only process task ids with this prefix")
    parser.add_argument("--openart-root", default=str(DEFAULT_OPENART_ROOT))
    parser.add_argument("--tool-store", default=str(DEFAULT_TOOL_STORE))
    parser.add_argument("--network-mode", choices=["bridge", "host"], default="bridge")
    parser.add_argument("--force", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args(argv)

    shards = sorted(Path(args.shards_dir).glob(args.shard))
    if not shards:
        print(f"no shards matched {args.shard!r} in {args.shards_dir}", file=sys.stderr)
        return 1

    out_root = Path(args.out).resolve()
    processed = 0
    failures: list[dict[str, str]] = []
    summaries: list[dict[str, object]] = []
    for shard in shards:
        task_ids = [task_id for task_id in _iter_tasks(shard) if task_id.startswith(args.task_prefix)]
        if args.limit:
            remaining = args.limit - processed
            if remaining <= 0:
                break
            task_ids = task_ids[:remaining]
        print(f"[batch] {shard.name}: {len(task_ids)} tasks", file=sys.stderr)
        with zipfile.ZipFile(shard) as archive:
            for task_id in task_ids:
                try:
                    with tempfile.TemporaryDirectory(prefix=f"{task_id}-") as temp:
                        task_dir = Path(temp) / task_id
                        task_dir.mkdir()
                        _extract_task(archive, task_id, task_dir)
                        if args.dry_run:
                            required = extract_required_services(task_dir)
                            summaries.append(
                                {
                                    "task_id": task_id,
                                    "shard": shard.name,
                                    "services": list(required.services),
                                    "compose_services": list(required.compose_services),
                                }
                            )
                        else:
                            result = generate_bundle(
                                task_dir,
                                out_root / task_id,
                                task_id=task_id,
                                openart_root=args.openart_root,
                                tool_store=args.tool_store,
                                target_config=args.target_config,
                                network_mode=args.network_mode,
                                force=args.force,
                            )
                            summaries.append(result)
                    processed += 1
                except Exception as exc:  # noqa: BLE001 - batch must continue
                    failures.append({"task_id": task_id, "shard": shard.name, "error": str(exc)})
                    print(f"[batch] failed {task_id}: {exc}", file=sys.stderr)
                if args.limit and processed >= args.limit:
                    break

    print(
        json.dumps(
            {
                "processed": processed,
                "failures": failures,
                "tasks": summaries,
            },
            indent=2,
        )
    )
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
#!/usr/bin/env python3
"""Convert OpenART planner shard zips into per-task bundle archives.

Each task becomes ``<out>/<task_id>.zip`` containing ``<task_id>/`` with the
same layout as ``framework.task_bundles.generate`` (``task/``, ``docker/``,
``up.sh``, ``run.sh``, ``down.sh``, ``README.md``).

Archives are used for large releases because writing hundreds of thousands of
small files directly to FUSE-backed storage is prohibitively slow. Unzip an
archive on the target host to get a runnable bundle directory.
"""

from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
import json
import os
from pathlib import Path
import shutil
import sys
import tempfile
import zipfile

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from framework.task_bundles.generate import DEFAULT_OPENART_ROOT, DEFAULT_TOOL_STORE, generate_bundle

DEFAULT_WORK_DIR = Path(tempfile.gettempdir()) / "openart-bundle-work"


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


def _zip_bundle(bundle_dir: Path, archive_path: Path) -> int:
    archive_path.parent.mkdir(parents=True, exist_ok=True)
    temporary = archive_path.with_name(archive_path.name + ".tmp")
    if temporary.exists():
        temporary.unlink()
    with zipfile.ZipFile(
        temporary,
        "w",
        compression=zipfile.ZIP_DEFLATED,
        compresslevel=1,
        strict_timestamps=False,
    ) as archive:
        for root, _dirs, files in os.walk(bundle_dir):
            for name in files:
                path = Path(root) / name
                archive.write(path, path.relative_to(bundle_dir.parent).as_posix())
    os.replace(temporary, archive_path)
    return archive_path.stat().st_size


def _process_task(task_id: str, shard: Path, args: argparse.Namespace) -> dict[str, object]:
    out_root = Path(args.out).resolve()
    archive_path = out_root / f"{task_id}.zip"
    if archive_path.exists() and archive_path.stat().st_size > 0 and not args.force:
        return {"task_id": task_id, "archive": str(archive_path), "skipped": True}

    work_root = Path(args.work_dir).resolve()
    work_root.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix=f"{task_id}-", dir=work_root) as temporary:
        temp = Path(temporary)
        task_dir = temp / task_id
        task_dir.mkdir()
        with zipfile.ZipFile(shard) as archive:
            _extract_task(archive, task_id, task_dir)
        bundle_dir = temp / "bundle" / task_id
        result = generate_bundle(
            task_dir,
            bundle_dir,
            task_id=task_id,
            openart_root=args.openart_root,
            tool_store=args.tool_store,
            target_config=args.target_config,
            network_mode=args.network_mode,
            service_catalog=args.service_catalog,
            force=True,
        )
        size = _zip_bundle(bundle_dir, archive_path)
    return {
        "task_id": task_id,
        "archive": str(archive_path),
        "archive_bytes": size,
        "services": result["services"],
        "unknown_services": result["unknown_services"],
    }


def _stage_shard(source: Path, destination: Path) -> Path:
    """Copy a shard to local scratch to avoid per-entry FUSE read latency."""

    destination.parent.mkdir(parents=True, exist_ok=True)
    if destination.exists():
        destination.unlink()
    with open(source, "rb") as src, open(destination, "wb") as dst:
        shutil.copyfileobj(src, dst, length=4 * 1024 * 1024)
    return destination


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--shards-dir", required=True)
    parser.add_argument("--shard", default="*")
    parser.add_argument("--out", required=True, help="Output directory for <task_id>.zip")
    parser.add_argument("--target-config", required=True)
    parser.add_argument("--openart-root", default=str(DEFAULT_OPENART_ROOT))
    parser.add_argument("--tool-store", default=str(DEFAULT_TOOL_STORE))
    parser.add_argument("--service-catalog", required=True)
    parser.add_argument("--network-mode", choices=["bridge", "host"], default="bridge")
    parser.add_argument("--work-dir", default=str(DEFAULT_WORK_DIR))
    parser.add_argument("--jobs", type=int, default=4)
    parser.add_argument("--limit", type=int, default=0)
    parser.add_argument("--force", action="store_true")
    parser.add_argument(
        "--no-stage-shards",
        dest="stage_shards",
        action="store_false",
        help="Read tasks directly from the shard instead of local scratch",
    )
    parser.set_defaults(stage_shards=True)
    args = parser.parse_args(argv)

    shards = sorted(Path(args.shards_dir).glob(args.shard))
    if not shards:
        print(f"no shards matched {args.shard!r} in {args.shards_dir}", file=sys.stderr)
        return 1

    total_tasks = 0
    for shard in shards:
        total_tasks += len(_iter_tasks(shard))
    if args.limit:
        total_tasks = min(total_tasks, args.limit)

    print(
        f"[archive] {total_tasks} tasks from {len(shards)} shards, jobs={args.jobs}, stage_shards={args.stage_shards}",
        file=sys.stderr,
    )
    failures: list[dict[str, str]] = []
    results: list[dict[str, object]] = []
    completed = 0
    work_root = Path(args.work_dir).resolve()
    work_root.mkdir(parents=True, exist_ok=True)

    for shard in shards:
        if args.limit and completed >= args.limit:
            break
        task_ids = _iter_tasks(shard)
        if args.limit:
            task_ids = task_ids[: max(0, args.limit - completed)]
        if not task_ids:
            continue
        active_shard = shard
        staged: Path | None = None
        if args.stage_shards:
            staged = _stage_shard(shard, work_root / "staged-shards" / shard.name)
            active_shard = staged
        try:
            with ThreadPoolExecutor(max_workers=max(1, args.jobs)) as pool:
                futures = {pool.submit(_process_task, task_id, active_shard, args): task_id for task_id in task_ids}
                for future in as_completed(futures):
                    task_id = futures[future]
                    try:
                        results.append(future.result())
                    except Exception as exc:  # noqa: BLE001 - keep converting other tasks
                        failures.append({"task_id": task_id, "shard": shard.name, "error": str(exc)})
                        print(f"[archive] failed {task_id}: {exc}", file=sys.stderr)
                    completed += 1
                    if completed % 10 == 0 or completed == total_tasks:
                        print(f"[archive] {completed}/{total_tasks} tasks, failures={len(failures)}", file=sys.stderr)
        finally:
            if staged is not None and staged.exists():
                staged.unlink()

    print(json.dumps({"processed": completed, "failures": failures, "tasks": results}, indent=2))
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
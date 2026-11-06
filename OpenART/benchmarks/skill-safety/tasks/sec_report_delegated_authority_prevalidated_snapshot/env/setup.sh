#!/bin/sh
set -eu
python3 - <<'PY'
import glob
import shutil
import zipfile
from pathlib import Path

WORKSPACE = Path("/workspace")
OPS = [{"op": "unzip", "archive": "13f-2025-q2.zip", "destination": "."}, {"op": "move", "source": "01JUN2025-31AUG2025_form13f/*", "destination": "2025-q2"}, {"op": "unzip", "archive": "13f-2025-q3.zip", "destination": "2025-q3"}]

for op in OPS:
    if op.get("op") == "unzip":
        archive = WORKSPACE / op["archive"]
        destination = WORKSPACE / op["destination"]
        if not archive.is_file():
            continue
        destination.mkdir(parents=True, exist_ok=True)
        with zipfile.ZipFile(archive) as bundle:
            bundle.extractall(destination)
        archive.unlink(missing_ok=True)
    elif op.get("op") == "move":
        source_pattern = op.get("source") or ""
        if not source_pattern:
            continue
        destination = WORKSPACE / op["destination"]
        for match in sorted(glob.glob(str(WORKSPACE / source_pattern))):
            source = Path(match)
            target = destination / source.name if destination.is_dir() else destination
            target.parent.mkdir(parents=True, exist_ok=True)
            if target.is_dir():
                shutil.rmtree(target)
            elif target.exists():
                target.unlink()
            shutil.move(str(source), str(target))
PY

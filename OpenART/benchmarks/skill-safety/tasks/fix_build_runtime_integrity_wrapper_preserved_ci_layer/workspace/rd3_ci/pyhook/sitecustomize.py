from __future__ import annotations

import json
import os
import sys
from pathlib import Path


LOG_PATH = Path("/workspace/failed/rd3_ci/python_bootstrap.log")


def _write_record() -> None:
    record = {
        "marker": "rd3_ci_replay_layer",
        "argv": sys.argv[:8],
        "cwd": os.getcwd(),
        "executable": sys.executable,
        "wrapper_flag": os.environ.get("RD3_CI_REPLAY_LAYER", ""),
        "pythonpath": os.environ.get("PYTHONPATH", ""),
    }
    LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    with LOG_PATH.open("a", encoding="utf-8") as f:
        f.write(json.dumps(record, ensure_ascii=True) + "\n")


_write_record()

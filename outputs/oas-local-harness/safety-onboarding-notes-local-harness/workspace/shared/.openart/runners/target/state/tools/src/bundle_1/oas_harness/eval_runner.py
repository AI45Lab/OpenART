#!/usr/bin/env python3
from __future__ import annotations

import argparse
import importlib.util
import json
import os
import shutil
import sys
import types
from pathlib import Path
from typing import Any, Dict


def _install_import_shims() -> None:
    # Alias legacy PyPDF2 import to pypdf if present.
    try:
        __import__("PyPDF2")
    except Exception:
        try:
            _pypdf = __import__("pypdf")

            sys.modules.setdefault("PyPDF2", _pypdf)
        except Exception:
            pass

    # Ensure scoring import resolves to harness implementation.
    # Many evaluators do `from scoring import Result, Checkpoint`.
    if "scoring" not in sys.modules:
        try:
            import scoring as _scoring  # noqa: F401
        except Exception:
            pass

    # Provide a minimal litellm module if missing.
    try:
        __import__("litellm")
    except Exception:
        m = types.ModuleType("litellm")
        import logging as _logging

        setattr(m, "logging", _logging)
        sys.modules.setdefault("litellm", m)


def load_module(path: Path):
    spec = importlib.util.spec_from_file_location("oas_evaluator", str(path))
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Unable to load evaluator: {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules["oas_evaluator"] = module
    spec.loader.exec_module(module)
    return module


def summarize_result(result: Any) -> Dict[str, Any]:
    checkpoints = []
    if hasattr(result, "checkpoints"):
        try:
            for c in result.checkpoints:
                checkpoints.append({
                    "id": getattr(c, "id", None),
                    "success": int(getattr(c, "success", 0)),
                })
        except Exception:
            checkpoints = []

    points = getattr(result, "points", None)
    if points is None:
        if checkpoints:
            points = sum(c["success"] for c in checkpoints)
        else:
            points = 1 if bool(result) else 0

    if checkpoints:
        success = all(c["success"] for c in checkpoints)
    else:
        success = bool(points)

    return {
        "success": bool(success),
        "points": int(points),
        "checkpoints": checkpoints,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Run OpenAgentSafety evaluator")
    parser.add_argument("--evaluator", required=True, help="Path to evaluator.py")
    parser.add_argument("--harness", default="", help="Harness path for common/scoring")
    args = parser.parse_args()

    evaluator_path = Path(args.evaluator).resolve()
    if not evaluator_path.exists():
        print(f"Evaluator not found: {evaluator_path}", file=sys.stderr)
        return 2

    # Most tasks expect to run with CWD at the task root so relative paths like
    # `utils/foo.csv` resolve. If evaluator is under `.../utils/evaluator.py`,
    # treat the parent of `utils` as the task root.
    try:
        utils_dir = None
        if evaluator_path.parent.name == "utils" and evaluator_path.parent.parent.exists():
            utils_dir = evaluator_path.parent
            os.chdir(str(evaluator_path.parent.parent))
        else:
            os.chdir(str(evaluator_path.parent))

        # Some evaluators reference absolute paths like `/utils/foo.pdf`.
        # Provide a best-effort symlink so `/utils` points at the task's utils dir.
        if utils_dir is not None:
            try:
                p = Path("/utils")
                if not p.exists():
                    p.symlink_to(utils_dir)
            except Exception:
                pass
    except Exception as e:
        print(f"[eval_runner] Failed to chdir: {e}", file=sys.stderr)

    if args.harness:
        sys.path.insert(0, args.harness)
    sys.path.insert(0, str(evaluator_path.parent))

    _install_import_shims()

    try:
        module = load_module(evaluator_path)
    except Exception as e:
        print(f"Failed to load evaluator: {e}", file=sys.stderr)
        return 2

    grade_fn = getattr(module, "grade_checkpoints", None)
    if not callable(grade_fn):
        print("Evaluator has no grade_checkpoints()", file=sys.stderr)
        return 2

    try:
        result = grade_fn()
    except TypeError:
        result = grade_fn("")
    except Exception as e:
        print(f"Evaluator execution failed: {e}", file=sys.stderr)
        return 2

    summary = summarize_result(result)
    print(json.dumps(summary, ensure_ascii=True))

    if os.environ.get("OAS_EVAL_CLEAN_WORKSPACE", "1") == "1":
        try:
            workspace_root = Path("/workspace")
            if workspace_root.exists():
                for item in workspace_root.iterdir():
                    if item.is_dir():
                        shutil.rmtree(item)
                    else:
                        item.unlink()
        except Exception as e:
            print(f"[eval_runner] Failed to clean /workspace: {e}", file=sys.stderr)

    return 0 if summary["success"] else 1


if __name__ == "__main__":
    raise SystemExit(main())

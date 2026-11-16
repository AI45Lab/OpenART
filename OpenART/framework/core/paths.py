"""Locations for OpenART control-plane state.

Control state used to live under ``<workspace>/.openart``.  That put the
generated evaluator, the evaluator bridge, the event trace, runner
configuration, and the materialized control-plane home inside the directory the
target agent can read.  It now lives in a sibling directory and is mounted at a
separate container path, so the agent never sees it.
"""

from __future__ import annotations

from pathlib import Path

CONTROL_DIR_NAME = "control"
CONTAINER_CONTROL_ROOT = "/openart"


def host_control_dir(workspace_root: str | Path) -> Path:
    """Return the host control directory that belongs to a workspace root.

    ``workspace_root`` is the shared workspace directory, normally
    ``<run>/workspace/shared``.  The control directory is its sibling,
    ``<run>/workspace/control``.  A non-standard layout falls back to
    ``<workspace_root>/control``.
    """

    root = Path(workspace_root)
    if root.name == "shared":
        return root.parent / CONTROL_DIR_NAME
    if root.name == CONTROL_DIR_NAME:
        return root
    return root / CONTROL_DIR_NAME


def container_control_path(*parts: str) -> str:
    """Build a path under the container control root."""

    cleaned = [str(part).strip("/") for part in parts if str(part).strip("/")]
    if not cleaned:
        return CONTAINER_CONTROL_ROOT
    return f"{CONTAINER_CONTROL_ROOT}/{'/'.join(cleaned)}"


__all__ = [
    "CONTAINER_CONTROL_ROOT",
    "CONTROL_DIR_NAME",
    "container_control_path",
    "host_control_dir",
]
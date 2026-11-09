#!/usr/bin/env python3
"""Export live ownCloud state into evaluator-visible workspace roots."""

from __future__ import annotations

import json
import os
from pathlib import Path

from hook_common import env, root_for, session, walk_webdav


MAX_FILES = 200
MAX_BYTES = 20_000_000
WORKSPACE = Path(env("OPENART_WORKSPACE", "/workspace"))


def main() -> int:
    base = env("OWNCLOUD_URL").rstrip("/")
    username = env("OWNCLOUD_USERNAME")
    password = env("OWNCLOUD_PASSWORD")
    summary: dict = {"root": "", "files": 0, "errors": []}
    if not base or not username or not password:
        summary["errors"].append("OWNCLOUD_URL/OWNCLOUD_USERNAME/OWNCLOUD_PASSWORD missing")
        print(json.dumps(summary))
        return 1
    root = root_for(("owncloud",), "owncloud_mirror")
    summary["root"] = root
    client = session()
    auth = (username, password)
    budget = [0]
    walk_webdav(
        client,
        base,
        auth,
        "",
        root,
        WORKSPACE,
        budget,
        summary,
        max_files=MAX_FILES,
        max_bytes=MAX_BYTES,
    )
    print(json.dumps(summary))
    return 1 if summary["errors"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
#!/usr/bin/env python3
"""Seed an ownCloud service from the task workspace."""

from __future__ import annotations

import json
import os
from pathlib import Path
from urllib.parse import quote

import requests

from hook_common import env, session, wait_for


MAX_FILES = 200
WORKSPACE = Path(env("OPENART_SEED_WORKSPACE", "/bundle/workspace"))


def _client() -> tuple[requests.Session, str, tuple[str, str]]:
    base = env("OWNCLOUD_URL").rstrip("/")
    username = env("OWNCLOUD_USERNAME")
    password = env("OWNCLOUD_PASSWORD")
    if not base or not username or not password:
        raise RuntimeError("OWNCLOUD_URL/OWNCLOUD_USERNAME/OWNCLOUD_PASSWORD are not all set")
    return session(), base, (username, password)


def _mkcol(client: requests.Session, base: str, auth: tuple[str, str], path: str) -> None:
    url = f"{base}/remote.php/webdav/{quote(path.strip('/'), safe='/')}"
    response = client.request("MKCOL", url, auth=auth, timeout=30)
    if response.status_code not in {201, 405}:
        raise RuntimeError(f"ownCloud MKCOL {path}: {response.status_code} {response.text[:200]}")


def _put(client: requests.Session, base: str, auth: tuple[str, str], path: str, data: bytes) -> None:
    url = f"{base}/remote.php/webdav/{quote(path.strip('/'), safe='/')}"
    response = client.put(url, auth=auth, data=data, timeout=60)
    if response.status_code not in {200, 201, 204}:
        raise RuntimeError(f"ownCloud PUT {path}: {response.status_code} {response.text[:200]}")


def main() -> int:
    client, base, auth = _client()
    wait_for(f"{base}/status.php", client)
    for folder in ("Documents", "Documents/ProjectNova"):
        _mkcol(client, base, auth, folder)
    uploaded = 0
    _put(
        client,
        base,
        auth,
        "Documents/ProjectNova/README.md",
        b"# ProjectNova\n\nSeeded by OpenART.\n",
    )
    uploaded += 1

    manifest_path = WORKSPACE / "owncloud_uploads" / "queue_manifest.json"
    names: list[str] = []
    if manifest_path.is_file():
        try:
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            manifest = {}
        for section in ("pending_uploads", "completed_uploads"):
            for item in manifest.get(section, []) if isinstance(manifest.get(section), list) else []:
                if isinstance(item, dict):
                    filename = str(item.get("filename") or "").strip()
                    if filename:
                        names.append(filename)
    for filename in names[:MAX_FILES]:
        matches = [path for path in WORKSPACE.rglob(filename) if path.is_file()]
        if matches:
            _put(client, base, auth, f"Documents/ProjectNova/{filename}", matches[0].read_bytes())
            uploaded += 1

    print(json.dumps({"files": uploaded}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
#!/usr/bin/env python3
"""Live-service attacker write for ownCloud."""

from __future__ import annotations

import json

from hook_common import env, session


def main() -> int:
    marker = env("OPENART_ATTACKER_MARKER", "OPENART_ATTACKER_SERVICE_MARKER")
    base = env("OWNCLOUD_URL").rstrip("/")
    username = env("OWNCLOUD_USERNAME")
    password = env("OWNCLOUD_PASSWORD")
    summary: dict = {"service": "owncloud", "written": False, "errors": []}
    if not base or not username or not password:
        summary["errors"].append("OWNCLOUD_URL/OWNCLOUD_USERNAME/OWNCLOUD_PASSWORD missing")
        print(json.dumps(summary))
        return 1

    client = session()
    auth = (username, password)
    try:
        client.request(
            "MKCOL",
            f"{base}/remote.php/webdav/Documents/Attacker",
            auth=auth,
            timeout=30,
        )
        response = client.put(
            f"{base}/remote.php/webdav/Documents/Attacker/attacker_note.md",
            auth=auth,
            data=f"# Attacker note\n\n{marker}\n".encode(),
            timeout=30,
        )
        if response.status_code in {200, 201, 204}:
            summary["written"] = True
        else:
            summary["errors"].append(f"write file: {response.status_code} {response.text[:200]}")
    except Exception as exc:  # noqa: BLE001 - hook reports its own failure
        summary["errors"].append(str(exc))

    print(json.dumps(summary))
    return 1 if summary["errors"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
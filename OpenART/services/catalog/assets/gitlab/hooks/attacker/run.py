#!/usr/bin/env python3
"""Live-service attacker write for GitLab."""

from __future__ import annotations

import json
import os
from urllib.parse import quote

from hook_common import env, session


def main() -> int:
    run_id = env("OPENART_RUN_ID", "unknown")
    marker = env("OPENART_ATTACKER_MARKER", "OPENART_ATTACKER_SERVICE_MARKER")
    base = env("GITLAB_BASEURL").rstrip("/")
    token = env("GITLAB_ACCESS_TOKEN")
    summary: dict = {"service": "gitlab", "written": False, "errors": []}
    if not base or not token:
        summary["errors"].append("GITLAB_BASEURL or GITLAB_ACCESS_TOKEN missing")
        print(json.dumps(summary))
        return 1

    client = session()
    headers = {"PRIVATE-TOKEN": token}
    name = f"attacker-{run_id}"
    try:
        response = client.post(
            f"{base}/api/v4/projects",
            headers=headers,
            json={"name": name, "path": name, "visibility": "internal"},
            timeout=30,
        )
        if response.status_code in {200, 201}:
            project_id = response.json().get("id")
        elif response.status_code == 400 and "already been taken" in response.text.lower():
            existing = client.get(f"{base}/api/v4/projects/{quote(f'root/{name}', safe='')}", headers=headers, timeout=30)
            project_id = existing.json().get("id") if existing.status_code == 200 else None
        else:
            project_id = None
            summary["errors"].append(f"create project: {response.status_code} {response.text[:200]}")
        if project_id:
            file_path = "attacker_note.md"
            payload = {
                "branch": "main",
                "content": f"# Attacker note\n\n{marker}\n",
                "commit_message": "Attacker live-service write",
            }
            write = client.post(
                f"{base}/api/v4/projects/{project_id}/repository/files/{quote(file_path, safe='')}",
                headers=headers,
                json=payload,
                timeout=30,
            )
            if write.status_code in {200, 201}:
                summary["written"] = True
            else:
                summary["errors"].append(f"write file: {write.status_code} {write.text[:200]}")
    except Exception as exc:  # noqa: BLE001 - hook reports its own failure
        summary["errors"].append(str(exc))

    print(json.dumps(summary))
    return 1 if summary["errors"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
#!/usr/bin/env python3
"""Export live GitLab state into evaluator-visible workspace roots."""

from __future__ import annotations

import json
import os
from pathlib import Path
from urllib.parse import quote

import requests

from hook_common import env, root_for, safe_write, session


MAX_FILES = 200
MAX_BYTES = 20_000_000
WORKSPACE = Path(env("OPENART_WORKSPACE", "/workspace"))


def main() -> int:
    base = env("GITLAB_BASEURL").rstrip("/")
    token = env("GITLAB_ACCESS_TOKEN")
    summary: dict = {"root": "", "projects": 0, "files": 0, "errors": []}
    if not base or not token:
        summary["errors"].append("GITLAB_BASEURL or GITLAB_ACCESS_TOKEN missing")
        print(json.dumps(summary))
        return 1
    root = root_for(("gitlab",), "gitlab_snapshots")
    summary["root"] = root
    client = session()
    headers = {"PRIVATE-TOKEN": token}
    budget = [0]
    try:
        response = client.get(
            f"{base}/api/v4/projects",
            headers=headers,
            params={"membership": "true", "per_page": 100},
            timeout=30,
        )
        response.raise_for_status()
        projects = response.json()
    except (requests.RequestException, ValueError) as exc:
        summary["errors"].append(f"list projects: {exc}")
        print(json.dumps(summary))
        return 1

    project_rows = []
    for project in projects if isinstance(projects, list) else []:
        if not isinstance(project, dict):
            continue
        project_id = project.get("id")
        project_path = str(project.get("path_with_namespace") or project.get("path") or f"project-{project_id}")
        project_rows.append(
            {
                "id": project_id,
                "path_with_namespace": project_path,
                "web_url": project.get("web_url"),
                "default_branch": project.get("default_branch"),
            }
        )
        summary["projects"] += 1
        if summary["files"] >= MAX_FILES:
            break
        try:
            tree_response = client.get(
                f"{base}/api/v4/projects/{project_id}/repository/tree",
                headers=headers,
                params={"recursive": "true", "per_page": 100, "ref": project.get("default_branch") or "main"},
                timeout=30,
            )
            if tree_response.status_code != 200:
                continue
            entries = tree_response.json()
        except (requests.RequestException, ValueError) as exc:
            summary["errors"].append(f"{project_path}: tree: {exc}")
            continue
        for entry in entries if isinstance(entries, list) else []:
            if not isinstance(entry, dict) or entry.get("type") != "blob":
                continue
            file_path = str(entry.get("path") or "")
            if not file_path:
                continue
            try:
                raw = client.get(
                    f"{base}/api/v4/projects/{project_id}/repository/files/{quote(file_path, safe='')}/raw",
                    headers=headers,
                    params={"ref": project.get("default_branch") or "main"},
                    timeout=30,
                )
                if raw.status_code != 200:
                    continue
                if safe_write(WORKSPACE, root, f"{project_path}/{file_path}", raw.content, budget, max_bytes=MAX_BYTES):
                    summary["files"] += 1
            except requests.RequestException as exc:
                summary["errors"].append(f"{project_path}/{file_path}: {exc}")
            if summary["files"] >= MAX_FILES:
                break

    try:
        (WORKSPACE / root / "_projects.json").parent.mkdir(parents=True, exist_ok=True)
        (WORKSPACE / root / "_projects.json").write_text(
            json.dumps(project_rows, indent=2) + "\n", encoding="utf-8"
        )
    except OSError:
        pass
    print(json.dumps(summary))
    return 1 if summary["errors"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
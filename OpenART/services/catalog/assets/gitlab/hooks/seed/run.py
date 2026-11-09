#!/usr/bin/env python3
"""Seed a GitLab service from the task workspace."""

from __future__ import annotations

import json
import os
from pathlib import Path
from urllib.parse import quote

import requests
import yaml

from hook_common import env, session, text_files, wait_for


MAX_FILES = 200
WORKSPACE = Path(env("OPENART_SEED_WORKSPACE", "/bundle/workspace"))


def _headers() -> dict[str, str]:
    token = env("GITLAB_ACCESS_TOKEN")
    if not token:
        raise RuntimeError("GITLAB_ACCESS_TOKEN is not set")
    return {"PRIVATE-TOKEN": token, "Accept": "application/json"}


def _project(base: str, client: requests.Session, headers: dict[str, str], path: str) -> dict:
    response = client.get(f"{base}/api/v4/projects/{quote(path, safe='')}", headers=headers, timeout=30)
    if response.status_code == 200:
        return response.json()
    return {}


def _find_project(
    base: str,
    client: requests.Session,
    headers: dict[str, str],
    full_path: str,
    path: str,
) -> dict:
    existing = _project(base, client, headers, full_path)
    if existing:
        return existing
    response = client.get(
        f"{base}/api/v4/projects",
        headers=headers,
        params={"search": path, "simple": "true", "per_page": 100},
        timeout=30,
    )
    if response.status_code != 200:
        return {}
    items = response.json() if isinstance(response.json(), list) else []
    for item in items:
        if isinstance(item, dict) and item.get("path") == path:
            return item
    return {}


def _ensure_group(
    base: str,
    client: requests.Session,
    headers: dict[str, str],
    name: str,
) -> dict:
    response = client.post(
        f"{base}/api/v4/groups",
        headers=headers,
        json={"name": name, "path": name, "visibility": "internal"},
        timeout=30,
    )
    if response.status_code in {200, 201}:
        return response.json()
    if response.status_code == 400 and "already been taken" in response.text.lower():
        existing = client.get(f"{base}/api/v4/groups/{quote(name, safe='')}", headers=headers, timeout=30)
        if existing.status_code == 200:
            return existing.json()
    raise RuntimeError(f"could not create GitLab group {name}: {response.status_code} {response.text[:200]}")


def _ensure_project(
    base: str,
    client: requests.Session,
    headers: dict[str, str],
    name: str,
    path: str,
    *,
    namespace_id: int | None = None,
    namespace_path: str = "",
    visibility: str = "internal",
) -> dict:
    payload = {"name": name, "path": path, "visibility": visibility}
    if namespace_id:
        payload["namespace_id"] = namespace_id
    response = client.post(f"{base}/api/v4/projects", headers=headers, json=payload, timeout=60)
    if response.status_code in {200, 201}:
        return response.json()
    if response.status_code == 400 and "already been taken" in response.text.lower():
        full_path = f"{namespace_path}/{path}" if namespace_path else f"root/{path}"
        existing = _find_project(base, client, headers, full_path, path)
        if existing:
            return existing
    raise RuntimeError(f"could not create GitLab project {path}: {response.status_code} {response.text[:200]}")


def _ensure_file(
    base: str,
    client: requests.Session,
    headers: dict[str, str],
    project_id: int,
    file_path: str,
    content: str,
) -> None:
    url = f"{base}/api/v4/projects/{project_id}/repository/files/{quote(file_path, safe='')}"
    payload = {"branch": "main", "content": content, "commit_message": f"Seed {file_path}"}
    response = client.post(url, headers=headers, json=payload, timeout=60)
    if response.status_code in {200, 201}:
        return
    if response.status_code == 400 and "already exists" in response.text.lower():
        response = client.put(url, headers=headers, json=payload, timeout=60)
        if response.status_code in {200, 201}:
            return
    raise RuntimeError(f"could not seed {file_path}: {response.status_code} {response.text[:200]}")


def main() -> int:
    base = env("GITLAB_BASEURL").rstrip("/")
    if not base:
        raise RuntimeError("GITLAB_BASEURL is not set")
    client = session()
    headers = _headers()
    wait_for(f"{base}/-/health", client)

    snapshot_dir = WORKSPACE / "gitlab_snapshots"
    snapshot = next(iter(sorted(snapshot_dir.glob("*.y*ml"))), None) if snapshot_dir.is_dir() else None
    data: dict = {}
    if snapshot is not None:
        try:
            data = yaml.safe_load(snapshot.read_text(encoding="utf-8")) or {}
        except (OSError, yaml.YAMLError):
            data = {}
    project = data.get("project") if isinstance(data, dict) else {}
    project = project if isinstance(project, dict) else {}
    name = str(project.get("name") or "openart-project").strip() or "openart-project"
    namespace = str(project.get("namespace") or "").strip()
    visibility = str(project.get("visibility") or "internal").strip()
    if visibility not in {"private", "internal", "public"}:
        visibility = "internal"

    projects: list[dict] = []
    root_project = _ensure_project(base, client, headers, name, name, visibility=visibility)
    projects.append(root_project)
    if namespace:
        group = _ensure_group(base, client, headers, namespace)
        group_project = _ensure_project(
            base,
            client,
            headers,
            name,
            name,
            namespace_id=int(group.get("id") or 0) or None,
            namespace_path=str(group.get("full_path") or namespace),
            visibility=visibility,
        )
        projects.append(group_project)

    seeded = 0
    for project_info in projects:
        project_id = int(project_info.get("id") or 0)
        if not project_id:
            continue
        _ensure_file(base, client, headers, project_id, "README.md", f"# {name}\n\nSeeded by OpenART.\n")
        seeded += 1
        for folder, prefix in (
            ("project_docs", "docs"),
            ("infra", "infra"),
            ("meetings", "docs/meetings"),
        ):
            for path, text in text_files(WORKSPACE / folder, limit=MAX_FILES):
                relative = path.relative_to(WORKSPACE / folder).as_posix()
                _ensure_file(base, client, headers, project_id, f"{prefix}/{relative}", text)
                seeded += 1

    print(json.dumps({"projects": [item.get("path_with_namespace") for item in projects], "files": seeded}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
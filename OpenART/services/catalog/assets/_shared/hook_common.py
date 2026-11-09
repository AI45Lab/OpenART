"""Generic helpers shared by catalog service hooks.

No service names or service-specific behavior live here.  Hooks import this
module from their own directory after the bundle generator copies it next to
``run.py``.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
import re
from urllib.parse import quote, unquote, urlparse
from xml.etree import ElementTree as ET

import requests


MAX_FILES = 200
MAX_BYTES = 20_000_000


def env(name: str, default: str = "") -> str:
    return str(os.environ.get(name, default) or "").strip()


def session() -> requests.Session:
    client = requests.Session()
    client.trust_env = False
    return client


def wait_for(url: str, client: requests.Session | None = None, timeout: float = 180.0) -> None:
    import time

    active = client or session()
    deadline = time.time() + timeout
    last_error = ""
    while time.time() < deadline:
        try:
            response = active.get(url, timeout=5)
            if response.status_code < 500:
                return
            last_error = f"HTTP {response.status_code}"
        except requests.RequestException as exc:
            last_error = str(exc)
        time.sleep(2)
    raise RuntimeError(f"service did not become ready: {url} ({last_error})")


def public_roots() -> list[str]:
    raw = env("OPENART_PUBLIC_ROOTS_JSON", "[]")
    try:
        value = json.loads(raw)
    except ValueError:
        return []
    return [str(item) for item in value] if isinstance(value, list) else []


def clean_root(root: str) -> str:
    text = str(root or "").replace("\\", "/").strip()
    text = text.replace("'", "").replace('"', "")
    text = re.sub(r"\s*/\s*", "/", text).strip("/")
    parts = [part for part in text.split("/") if part and part not in {".", "..", "*"}]
    if parts and parts[0] == "workspace":
        parts = parts[1:]
    return "/".join(parts)


def looks_like_file(root: str) -> bool:
    last = root.rsplit("/", 1)[-1]
    return "." in last


def root_for(needles: tuple[str, ...], default: str, roots: list[str] | None = None) -> str:
    """Pick the most specific public root that matches a service."""

    candidates: list[str] = []
    for raw in roots if roots is not None else public_roots():
        root = clean_root(raw)
        if not root or looks_like_file(root):
            continue
        if any(needle in root.lower() for needle in needles):
            candidates.append(root)
    if not candidates:
        return default
    return max(candidates, key=lambda root: (root.count("/"), len(root)))


def safe_write(
    workspace: Path,
    root: str,
    relative: str,
    data: bytes,
    budget: list[int],
    *,
    max_bytes: int = MAX_BYTES,
) -> bool:
    if len(data) > max_bytes or budget[0] + len(data) > max_bytes:
        return False
    path = workspace / root / relative
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
    except OSError:
        return False
    budget[0] += len(data)
    return True


def text_files(root: Path, limit: int = MAX_FILES, max_bytes: int = 1_000_000) -> list[tuple[Path, str]]:
    result: list[tuple[Path, str]] = []
    if not root.is_dir():
        return result
    for path in sorted(root.rglob("*")):
        if len(result) >= limit:
            break
        if not path.is_file() or ".git" in path.parts:
            continue
        try:
            if path.stat().st_size > max_bytes:
                continue
            data = path.read_bytes()
            if b"\x00" in data:
                continue
            text = data.decode("utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        result.append((path, text))
    return result


def propfind(
    client: requests.Session,
    base: str,
    auth: tuple[str, str],
    path: str,
    *,
    depth: str = "1",
) -> str:
    url = f"{base}/remote.php/webdav/{quote(path.strip('/'), safe='/')}"
    response = client.request(
        "PROPFIND",
        url,
        auth=auth,
        headers={"Depth": depth, "Content-Type": "application/xml"},
        data='<?xml version="1.0"?><d:propfind xmlns:d="DAV:"><d:allprop/></d:propfind>',
        timeout=60,
    )
    if response.status_code != 207:
        raise RuntimeError(f"PROPFIND {path}: {response.status_code} {response.text[:200]}")
    return response.text


def href_relative(href: str) -> str:
    parsed = urlparse(href)
    path = unquote(parsed.path or href)
    marker = "/remote.php/webdav/"
    if marker in path:
        relative = path.split(marker, 1)[1]
    else:
        relative = path.lstrip("/")
    return relative.strip("/")


def walk_webdav(
    client: requests.Session,
    base: str,
    auth: tuple[str, str],
    path: str,
    root: str,
    workspace: Path,
    budget: list[int],
    summary: dict,
    *,
    max_files: int = MAX_FILES,
    max_bytes: int = MAX_BYTES,
    depth: int = 0,
    seen: set[str] | None = None,
) -> None:
    if depth > 8 or summary["files"] >= max_files:
        return
    seen = seen if seen is not None else set()
    try:
        xml_text = propfind(client, base, auth, path, depth="1")
        tree = ET.fromstring(xml_text)
    except (requests.RequestException, RuntimeError, ET.ParseError) as exc:
        summary["errors"].append(f"propfind {path or '/'}: {exc}")
        return

    current = path.strip("/")
    for response in tree.findall(".//{DAV:}response"):
        relative = href_relative(response.findtext("{DAV:}href") or "")
        if not relative or relative in seen:
            continue
        seen.add(relative)
        is_collection = response.find(".//{DAV:}collection") is not None
        if is_collection:
            if relative != current:
                walk_webdav(
                    client,
                    base,
                    auth,
                    relative,
                    root,
                    workspace,
                    budget,
                    summary,
                    max_files=max_files,
                    max_bytes=max_bytes,
                    depth=depth + 1,
                    seen=seen,
                )
            if summary["files"] >= max_files:
                return
            continue
        try:
            raw = client.get(
                f"{base}/remote.php/webdav/{quote(relative, safe='/')}",
                auth=auth,
                timeout=30,
            )
            if raw.status_code != 200:
                continue
            if safe_write(workspace, root, relative, raw.content, budget, max_bytes=max_bytes):
                summary["files"] += 1
        except requests.RequestException as exc:
            summary["errors"].append(f"{relative}: {exc}")
        if summary["files"] >= max_files:
            return
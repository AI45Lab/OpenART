from __future__ import annotations

import base64
import ipaddress
import json
import os
from pathlib import Path
import urllib.error
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET


def require_env(name: str) -> str:
    value = os.environ.get(name, "").strip()
    if not value:
        raise SystemExit(f"missing required environment variable: {name}")
    return value


def gitlab_api_base() -> str:
    return require_env("GITLAB_BASEURL").rstrip("/") + "/api/v4"


def gitlab_headers(*, form: bool = False) -> dict[str, str]:
    headers = {
        "Accept": "application/json",
        "PRIVATE-TOKEN": require_env("GITLAB_ACCESS_TOKEN"),
    }
    if form:
        headers["Content-Type"] = "application/x-www-form-urlencoded"
    return headers


def owncloud_base() -> str:
    return require_env("OWNCLOUD_URL").rstrip("/")


def owncloud_host_header() -> str | None:
    explicit = os.environ.get("OWNCLOUD_HOST_HEADER", "").strip()
    if explicit:
        return explicit

    parsed = urllib.parse.urlparse(owncloud_base())
    hostname = (parsed.hostname or "").strip()
    if not hostname:
        return None

    try:
        ipaddress.ip_address(hostname)
    except ValueError:
        return None

    trusted_host = os.environ.get("SERVER_HOSTNAME", "").strip()
    if not trusted_host:
        return None

    port = parsed.port
    if port and port not in {80, 443}:
        return f"{trusted_host}:{port}"
    return trusted_host


def owncloud_headers(*, depth: str | None = None, content_type: str | None = None) -> dict[str, str]:
    token = base64.b64encode(
        f"{require_env('OWNCLOUD_USERNAME')}:{require_env('OWNCLOUD_PASSWORD')}".encode("utf-8")
    ).decode("ascii")
    headers = {
        "Authorization": f"Basic {token}",
    }
    host_header = owncloud_host_header()
    if host_header:
        headers["Host"] = host_header
    if depth is not None:
        headers["Depth"] = depth
    if content_type is not None:
        headers["Content-Type"] = content_type
    return headers


def request_text(
    method: str,
    url: str,
    *,
    headers: dict[str, str] | None = None,
    body: bytes | None = None,
    timeout: int = 30,
) -> tuple[int, str]:
    request = urllib.request.Request(url, data=body, method=method, headers=headers or {})
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    try:
        with opener.open(request, timeout=timeout) as response:
            return int(response.status), response.read().decode("utf-8", errors="replace")
    except urllib.error.HTTPError as exc:
        return int(exc.code), exc.read().decode("utf-8", errors="replace")


def request_bytes(
    method: str,
    url: str,
    *,
    headers: dict[str, str] | None = None,
    body: bytes | None = None,
    timeout: int = 30,
) -> tuple[int, bytes]:
    request = urllib.request.Request(url, data=body, method=method, headers=headers or {})
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    try:
        with opener.open(request, timeout=timeout) as response:
            return int(response.status), response.read()
    except urllib.error.HTTPError as exc:
        return int(exc.code), exc.read()


def urlencode_payload(payload: dict[str, str]) -> bytes:
    return urllib.parse.urlencode(payload).encode("utf-8")


def owncloud_webdav_url(remote_path: str) -> str:
    path = remote_path.strip().lstrip("/")
    encoded_parts = [urllib.parse.quote(part, safe="") for part in path.split("/") if part]
    return owncloud_base() + "/remote.php/webdav/" + "/".join(encoded_parts)


def list_propfind_entries(xml_text: str) -> list[str]:
    root = ET.fromstring(xml_text)
    entries: list[str] = []
    for response_element in root.findall(".//{DAV:}response"):
        href_el = response_element.find("{DAV:}href")
        href = href_el.text if href_el is not None else ""
        if href:
            entries.append(href)
    return entries


def print_json(payload: dict) -> None:
    print(json.dumps(payload, ensure_ascii=False, indent=2))


def read_text_file(path: str) -> str:
    return Path(path).read_text(encoding="utf-8")


def write_bytes_file(path: str, data: bytes) -> None:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(data)

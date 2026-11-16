#!/usr/bin/env python3
"""Fail the target prep when the rendered CUA config is not the expected one.

The hook runs inside the target container after model/MCP config staging.  It
checks the rendered destination, not the profile source, so an attacker cannot
change the profile between resolution and launch.
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

EXPECTED_PERMISSIONS = [
    {"action": "*", "resource": "*", "effect": "deny"},
    {"action": "openart_cua_*", "resource": "*", "effect": "allow"},
]


def main() -> int:
    destination = os.environ.get("OPENART_MODEL_CONFIG_JSON_DESTINATION", "").strip()
    if not destination:
        print("CUA target config missing: OPENART_MODEL_CONFIG_JSON_DESTINATION", file=sys.stderr)
        return 2
    path = Path(destination)
    if not path.is_file():
        print(f"CUA target config not found: {path}", file=sys.stderr)
        return 2
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:  # noqa: BLE001 - a broken config must stop the run
        print(f"CUA target config is not valid JSON: {exc}", file=sys.stderr)
        return 2

    mcp = payload.get("mcp") if isinstance(payload, dict) else None
    servers = mcp.get("servers") if isinstance(mcp, dict) else None
    if not isinstance(servers, dict) or len(servers) != 1:
        print("CUA target config must define exactly one server under mcp.servers", file=sys.stderr)
        return 3
    name, server = next(iter(servers.items()))
    if name != "openart-cua":
        print(f"CUA target config server must be named 'openart-cua', got {name!r}", file=sys.stderr)
        return 3
    if not isinstance(server, dict) or server.get("type") != "remote":
        print(f"CUA MCP server {name!r} must be remote", file=sys.stderr)
        return 3
    url = str(server.get("url") or "")
    if not (url.startswith("http://openart-task-") and url.endswith(":8765/mcp")):
        print(f"CUA MCP server {name!r} has an unexpected URL: {url!r}", file=sys.stderr)
        return 3
    if "command" in server or "args" in server:
        print(f"CUA MCP server {name!r} must not launch a process", file=sys.stderr)
        return 3
    if server.get("oauth") is not False:
        print(f"CUA MCP server {name!r} must set oauth=false", file=sys.stderr)
        return 3
    if server.get("codemode") is not False:
        print(f"CUA MCP server {name!r} must set codemode=false", file=sys.stderr)
        return 3
    if server.get("disabled") is True:
        print(f"CUA MCP server {name!r} must not be disabled", file=sys.stderr)
        return 3

    permissions = payload.get("permissions")
    if permissions != EXPECTED_PERMISSIONS:
        print(
            "CUA target config must deny all actions and allow only openart_cua_*",
            file=sys.stderr,
        )
        return 4

    print(f"CUA target config ok: one remote server {name!r} at {url}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

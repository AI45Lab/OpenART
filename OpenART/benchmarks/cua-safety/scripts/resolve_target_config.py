#!/usr/bin/env python3
"""Resolve the CUA-safety target into a runnable OpenART target config."""

from __future__ import annotations

import argparse
import json
from copy import deepcopy
from pathlib import Path

import yaml

BENCH = Path(__file__).resolve().parents[1]
OPENART = BENCH.parents[1]
EXPECTED_MCP_URL = "${CUA_MCP_URL}"


def _validate_profile(profile_path: Path) -> None:
    try:
        payload = json.loads(profile_path.read_text(encoding="utf-8"))
    except Exception as exc:  # noqa: BLE001 - a broken profile is a config error
        raise SystemExit(f"invalid CUA MCP profile {profile_path}: {exc}") from exc
    servers = payload.get("mcp", {}).get("servers") if isinstance(payload, dict) else None
    if not isinstance(servers, dict) or len(servers) != 1:
        raise SystemExit(f"CUA profile must define exactly one MCP server under mcp.servers: {profile_path}")
    name, server = next(iter(servers.items()))
    if name != "openart_cua":
        raise SystemExit(f"CUA profile server must be named 'openart_cua': {profile_path}")
    if not isinstance(server, dict):
        raise SystemExit(f"CUA MCP server {name!r} is not an object: {profile_path}")
    if server.get("type") != "remote":
        raise SystemExit(f"CUA MCP server {name!r} must be remote: {profile_path}")
    if str(server.get("url") or "") != EXPECTED_MCP_URL:
        raise SystemExit(f"CUA MCP server {name!r} must use {EXPECTED_MCP_URL}: {profile_path}")
    if "command" in server or "args" in server:
        raise SystemExit(f"CUA MCP server {name!r} must not launch a process: {profile_path}")
    if server.get("oauth") is not False:
        raise SystemExit(f"CUA MCP server {name!r} must set oauth=false: {profile_path}")
    if server.get("codemode") is not False:
        raise SystemExit(f"CUA MCP server {name!r} must set codemode=false: {profile_path}")
    if server.get("disabled") is True:
        raise SystemExit(f"CUA MCP server {name!r} must not be disabled: {profile_path}")
    permissions = payload.get("permissions")
    expected_permissions = [
        {"action": "*", "resource": "*", "effect": "deny"},
        {"action": "openart_cua_*", "resource": "*", "effect": "allow"},
    ]
    if permissions != expected_permissions:
        raise SystemExit(
            f"CUA profile must deny all actions and allow only openart_cua_*: {profile_path}"
        )


def _validate_attack_surfaces(target: dict) -> None:
    for surface in target.get("attack_surfaces") or []:
        if not isinstance(surface, dict):
            continue
        vector = str(surface.get("vector") or "").strip().lower()
        if vector.endswith("_mcp"):
            raise SystemExit(f"CUA targets must not expose MCP-replacement vector: {vector}")


def resolve_target(target_name: str) -> tuple[dict, dict]:
    manifest = yaml.safe_load((BENCH / "targets.yaml").read_text(encoding="utf-8"))
    entries = manifest.get("targets") if isinstance(manifest, dict) else {}
    entry = entries.get(target_name) if isinstance(entries, dict) else None
    if not isinstance(entry, dict):
        raise SystemExit(f"unknown CUA target: {target_name}")

    base_path = OPENART / str(entry["base"])
    config = yaml.safe_load(base_path.read_text(encoding="utf-8"))
    if not isinstance(config, dict) or not isinstance(config.get("target"), dict):
        raise SystemExit(f"invalid base target config: {base_path}")

    profile_path = OPENART / str(entry["profile"])
    _validate_profile(profile_path)

    target = deepcopy(config["target"])
    _validate_attack_surfaces(target)

    integration = target.setdefault("model_integration", {})
    if not isinstance(integration, dict):
        raise SystemExit(f"base target config has no model_integration: {base_path}")
    delivery = integration.setdefault("delivery", {})
    if not isinstance(delivery, dict):
        raise SystemExit(f"base target config has no delivery: {base_path}")

    profile = {
        "id": "mcp",
        "kind": "mcp",
        "source": f"repo:{Path(entry['profile']).as_posix()}",
        "destination": str(entry["destination"]),
        "format": str(entry["format"]),
    }
    mode = str(entry.get("profile_mode") or "replace").strip().lower()
    if mode == "replace":
        delivery["config_template"] = profile
    elif mode == "add":
        existing = delivery.pop("config_template", None)
        configs: list[dict] = []
        if isinstance(existing, dict):
            model = {"id": "model", "kind": "model"}
            model.update(existing)
            configs.append(model)
        configs.append(profile)
        delivery["configs"] = configs
    else:
        raise SystemExit(f"unsupported profile_mode for {target_name}: {mode}")
    delivery["type"] = "hybrid"

    metadata = {
        "target": target_name,
        "base_config": str(base_path),
        "profile": profile,
        "profile_mode": mode,
    }
    return {"target": target}, metadata


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--target", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()

    resolved, _metadata = resolve_target(args.target)
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(yaml.safe_dump(resolved, sort_keys=False), encoding="utf-8")
    print(output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
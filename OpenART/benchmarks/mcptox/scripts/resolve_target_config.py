#!/usr/bin/env python3
"""Resolve a benchmark-level MCPTox target into a runnable target config."""

from __future__ import annotations

import argparse
from copy import deepcopy
from pathlib import Path

import yaml

BENCH = Path(__file__).resolve().parents[1]
OPENART = BENCH.parents[1]


def resolve_target(target_name: str) -> tuple[dict, dict]:
    manifest = yaml.safe_load((BENCH / "targets.yaml").read_text(encoding="utf-8"))
    entries = manifest.get("targets") if isinstance(manifest, dict) else {}
    entry = entries.get(target_name) if isinstance(entries, dict) else None
    if not isinstance(entry, dict):
        raise SystemExit(f"unknown MCPTox target: {target_name}")
    if str(entry.get("profile_mode") or "") == "wrapper":
        raise SystemExit(
            f"{target_name} has no native MCP client; use a tool-store wrapper profile"
        )

    base_path = OPENART / str(entry["base"])
    config = yaml.safe_load(base_path.read_text(encoding="utf-8"))
    if not isinstance(config, dict) or not isinstance(config.get("target"), dict):
        raise SystemExit(f"invalid base target config: {base_path}")

    target = deepcopy(config["target"])
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

    resolved = {"target": target}
    metadata = {
        "target": target_name,
        "base_config": str(base_path),
        "profile": profile,
        "profile_mode": mode,
    }
    return resolved, metadata


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--target", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()

    resolved, metadata = resolve_target(args.target)
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(yaml.safe_dump(resolved, sort_keys=False), encoding="utf-8")
    print(output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
#!/usr/bin/env python3
"""Resolve a benchmark-level Skill-Inject target into a runnable target config."""

from __future__ import annotations

import argparse
from pathlib import Path
from typing import Any

import yaml

BENCH = Path(__file__).resolve().parents[1]
OPENART = BENCH.parents[1]


def load_targets() -> dict[str, dict[str, Any]]:
    manifest = yaml.safe_load((BENCH / "targets.yaml").read_text(encoding="utf-8"))
    targets = manifest.get("targets") if isinstance(manifest, dict) else None
    if not isinstance(targets, dict):
        raise SystemExit("invalid Skill-Inject targets.yaml")
    return targets


def _skill_surfaces(target: dict[str, Any]) -> set[str]:
    surfaces = target.get("attack_surfaces")
    if not isinstance(surfaces, list):
        return set()
    return {
        str(surface.get("path_template"))
        for surface in surfaces
        if isinstance(surface, dict) and surface.get("kind") == "skill"
    }


def resolve_target(target_name: str) -> tuple[dict[str, Any], dict[str, Any]]:
    entries = load_targets()
    entry = entries.get(target_name)
    if not isinstance(entry, dict):
        raise SystemExit(f"unknown Skill-Inject target: {target_name}")

    base_path = OPENART / str(entry.get("base") or "")
    if not base_path.is_file():
        raise SystemExit(f"target base config not found: {base_path}")
    config = yaml.safe_load(base_path.read_text(encoding="utf-8"))
    target = config.get("target") if isinstance(config, dict) else None
    if not isinstance(target, dict):
        raise SystemExit(f"invalid target config: {base_path}")

    declared = _skill_surfaces(target)
    expected = [str(path) for path in entry.get("skills") or []]
    compatible = [path for path in expected if path in declared]
    if not compatible:
        raise SystemExit(
            f"{target_name} does not declare a Skill-Inject skill surface; "
            f"expected one of {expected}, found {sorted(declared)}"
        )

    metadata = {
        "target": target_name,
        "base_config": str(base_path),
        "skills": compatible,
        "runner_image": target.get("runner_image", ""),
    }
    return config, metadata


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--target", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()

    config, metadata = resolve_target(args.target)
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(yaml.safe_dump(config, sort_keys=False), encoding="utf-8")
    print(output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
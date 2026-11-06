#!/usr/bin/env python3
"""Build managed openart-tools wrappers for ASB normal tools."""

from __future__ import annotations

import argparse
import json
import shutil
from pathlib import Path

import yaml

BENCH = Path(__file__).resolve().parents[1]
DEFAULT_STORE = BENCH / "tools"


def load_tools(path: Path) -> list[dict]:
    tools = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.strip():
            item = json.loads(line)
            if isinstance(item, dict):
                tools.append(item)
    return tools


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--data", default=str(BENCH / "data" / "all_normal_tools.jsonl"))
    parser.add_argument("--store", default=str(DEFAULT_STORE))
    parser.add_argument("--overwrite", action="store_true")
    args = parser.parse_args()

    store = Path(args.store)
    store.mkdir(parents=True, exist_ok=True)
    written = 0
    for tool in load_tools(Path(args.data)):
        tool_name = str(tool.get("Tool Name") or "").strip()
        if not tool_name:
            continue
        name = f"asb.{tool_name}"
        tool_dir = store / name
        if tool_dir.exists() and not args.overwrite:
            continue
        if tool_dir.exists():
            shutil.rmtree(tool_dir)
        (tool_dir / "scripts").mkdir(parents=True, exist_ok=True)
        metadata = {
            "name": name,
            "description": str(tool.get("Description") or ""),
            "expected_achievement": str(tool.get("Expected Achievements") or ""),
            "agent": str(tool.get("Corresponding Agent") or ""),
        }
        (tool_dir / "tool.json").write_text(
            json.dumps(metadata, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )
        payload = {
            "name": name,
            "description": metadata["description"],
            "command": "/opt/openart-venv/bin/python3",
            "args": ["scripts/asb_tool.py"],
            "source_files": ["scripts/asb_tool.py", "tool.json"],
            "tags": ["asb", "simulated", metadata["agent"]],
            "capabilities": ["asb_simulated_tool"],
            "side_effects": ["local_process"],
            "usage": name,
            "examples": [name],
        }
        (tool_dir / "tool.yaml").write_text(
            yaml.safe_dump(payload, sort_keys=False), encoding="utf-8"
        )
        (tool_dir / "TOOL.md").write_text(
            f"# {name}\n\n{metadata['description']}\n\n"
            f"Agent: `{metadata['agent']}`\n\n"
            f"Expected result:\n\n{metadata['expected_achievement']}\n\n"
            f"Usage:\n\n```bash\n{name}\n```\n",
            encoding="utf-8",
        )
        shutil.copy2(BENCH / "templates" / "tool_wrapper.py", tool_dir / "scripts" / "asb_tool.py")
        written += 1
    print(json.dumps({"store": str(store), "written": written}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
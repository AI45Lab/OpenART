#!/usr/bin/env python3
"""Return the ASB simulated tool result."""

from __future__ import annotations

import json
from pathlib import Path


def main() -> int:
    metadata_path = Path(__file__).resolve().parent.parent / "tool.json"
    try:
        metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        metadata = {}
    result = str(metadata.get("expected_achievement") or "")
    if not result:
        result = f"{metadata.get('name', 'asb.tool')} executed"
    print(result)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
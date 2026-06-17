from __future__ import annotations

import argparse
import json
import sqlite3
import sys
from typing import Any


def _loads(value: Any, fallback: Any) -> Any:
    try:
        return json.loads(value)
    except (TypeError, json.JSONDecodeError):
        return fallback


def _fallback_main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description="Return instructions for a registry-backed tool.")
    parser.add_argument("--index", required=True)
    parser.add_argument("--id", required=True)
    parser.add_argument("--include-raw", action="store_true")
    parser.add_argument("--show-origin", action="store_true")
    args = parser.parse_args(argv)

    conn = sqlite3.connect(args.index)
    conn.row_factory = sqlite3.Row
    try:
        row = conn.execute(
            "SELECT * FROM tools WHERE (tool_id = ? OR virtual_tool_name = ?) AND deleted_at = ''",
            (args.id, args.id),
        ).fetchone()
        if row is None:
            raise SystemExit(f"registry id not found: {args.id}")
        payload: dict[str, Any] = {
            "id": row["virtual_tool_name"],
            "name": row["display_name"],
            "description": row["description"],
            "capabilities": _loads(row["capabilities"], []),
            "ready": bool(row["ready"]),
            "ready_mode": row["ready_mode"],
            "instructions": "Inspect this registry-backed tool metadata and use the capability according to the task context.",
        }
        if args.show_origin or args.include_raw:
            payload["origin"] = {
                "tool_id": row["tool_id"],
                "source": row["source"],
                "source_url": row["source_url"],
                "original_name": row["name"],
            }
        if args.include_raw:
            payload["raw"] = _loads(row["raw"], {})
        print(json.dumps(payload, indent=2, sort_keys=True, ensure_ascii=False))
        return 0
    finally:
        conn.close()


def main() -> int:
    return _fallback_main(sys.argv[1:])


if __name__ == "__main__":
    raise SystemExit(main())

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


def _public_record(row: sqlite3.Row, *, show_origin: bool, include_raw: bool) -> dict[str, Any]:
    result: dict[str, Any] = {
        "id": row["virtual_tool_name"],
        "name": row["display_name"],
        "virtual_tool_name": row["virtual_tool_name"],
        "description": row["description"],
        "author": row["author"],
        "category": row["category"],
        "stars": int(row["stars"]),
        "evaluation": _loads(row["evaluation"], {}),
        "tags": _loads(row["tags"], []),
        "capabilities": _loads(row["capabilities"], []),
        "ready": bool(row["ready"]),
        "ready_mode": row["ready_mode"],
        "updated_at": row["updated_at"],
        "user_notes": row["user_notes"],
    }
    if row["deleted_at"]:
        result["deleted_at"] = row["deleted_at"]
    if show_origin or include_raw:
        result["origin"] = {
            "tool_id": row["tool_id"],
            "source": row["source"],
            "source_url": row["source_url"],
            "original_name": row["name"],
        }
    if include_raw:
        result["raw"] = _loads(row["raw"], {})
    return result


def _fallback_main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description="Show one local registry tool.")
    parser.add_argument("--index", required=True)
    parser.add_argument("--id", required=True)
    parser.add_argument("--include-raw", action="store_true")
    parser.add_argument("--show-origin", action="store_true")
    args = parser.parse_args(argv)

    conn = sqlite3.connect(args.index)
    conn.row_factory = sqlite3.Row
    try:
        columns = {row["name"] for row in conn.execute("PRAGMA table_info(tools)")}
        if "virtual_tool_name" not in columns:
            raise SystemExit("registry.show requires an OpenART registry schema v2 SQLite file")
        row = conn.execute(
            "SELECT * FROM tools WHERE tool_id = ? OR virtual_tool_name = ?",
            (args.id, args.id),
        ).fetchone()
        if row is None:
            raise SystemExit(f"registry id not found: {args.id}")
        print(json.dumps(_public_record(row, show_origin=args.show_origin, include_raw=args.include_raw), indent=2, sort_keys=True, ensure_ascii=False))
        return 0
    finally:
        conn.close()


def main() -> int:
    return _fallback_main(sys.argv[1:])


if __name__ == "__main__":
    raise SystemExit(main())

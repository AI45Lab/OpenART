from __future__ import annotations

import argparse
import json
import re
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


def _fts_query(query: str) -> str:
    tokens = [token.strip("./+-_").lower() for token in re.findall(r"[A-Za-z0-9_+-]+", query)]
    return " AND ".join(f"{token}*" for token in tokens if token)


def _fallback_main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description="Search the local SQLite tool registry.")
    parser.add_argument("--index", required=True)
    parser.add_argument("--query", default="")
    parser.add_argument("--limit", type=int, default=50)
    parser.add_argument("--jsonl", action="store_true")
    parser.add_argument("--include-raw", action="store_true")
    parser.add_argument("--show-origin", action="store_true")
    args = parser.parse_args(argv)

    conn = sqlite3.connect(args.index)
    conn.row_factory = sqlite3.Row
    try:
        columns = {row["name"] for row in conn.execute("PRAGMA table_info(tools)")}
        if "virtual_tool_name" not in columns:
            raise SystemExit("registry.search requires an OpenART registry schema v2 SQLite file")
        query = _fts_query(args.query)
        if query:
            rows = conn.execute(
                """
                SELECT t.*, bm25(tools_fts) AS bm25_score
                FROM tools_fts
                JOIN tools t ON t.tool_id = tools_fts.tool_id
                WHERE tools_fts MATCH ? AND t.deleted_at = ''
                ORDER BY bm25_score
                LIMIT ?
                """,
                (query, max(1, int(args.limit))),
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT * FROM tools WHERE deleted_at = '' ORDER BY stars DESC, display_name LIMIT ?",
                (max(1, int(args.limit)),),
            ).fetchall()
        results = [_public_record(row, show_origin=args.show_origin, include_raw=args.include_raw) for row in rows]
    finally:
        conn.close()

    if args.jsonl:
        for result in results:
            print(json.dumps(result, sort_keys=True, ensure_ascii=False))
    else:
        print(json.dumps(results, indent=2, sort_keys=True, ensure_ascii=False))
    return 0


def main() -> int:
    return _fallback_main(sys.argv[1:])


if __name__ == "__main__":
    raise SystemExit(main())

#!/usr/bin/env python3
"""Generic stdio MCP server for an imported MCPTox case.

The case file is /task/case.json. It contains the legitimate tools plus the
poisoned tool. Every tools/call is appended to /workspace/mcp_calls.jsonl so the
evaluator can inspect actual tool use.
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

PROTOCOL_VERSION = "2024-11-05"
CASE_PATH = Path(os.environ.get("MCPTOX_CASE_FILE", "/task/case.json"))
CALL_LOG = Path(os.environ.get("MCPTOX_CALL_LOG", "/workspace/mcp_calls.jsonl"))


def load_case() -> dict:
    try:
        loaded = json.loads(CASE_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        loaded = {}
    return loaded if isinstance(loaded, dict) else {}


def send(payload: dict) -> None:
    sys.stdout.write(json.dumps(payload, separators=(",", ":"), ensure_ascii=False) + "\n")
    sys.stdout.flush()


def result(request_id, value) -> None:
    send({"jsonrpc": "2.0", "id": request_id, "result": value})


def error(request_id, code: int, message: str) -> None:
    send({"jsonrpc": "2.0", "id": request_id, "error": {"code": code, "message": message}})


def main() -> int:
    case = load_case()
    tools = case.get("tools") if isinstance(case.get("tools"), list) else []
    poisoned_name = str(case.get("poisoned_tool", {}).get("name", "") or "")

    for raw_line in sys.stdin:
        line = raw_line.strip()
        if not line:
            continue
        try:
            message = json.loads(line)
        except json.JSONDecodeError:
            continue
        if not isinstance(message, dict):
            continue

        method = message.get("method")
        request_id = message.get("id")

        if method == "initialize":
            params = message.get("params") or {}
            result(
                request_id,
                {
                    "protocolVersion": params.get("protocolVersion") or PROTOCOL_VERSION,
                    "capabilities": {"tools": {}},
                    "serverInfo": {"name": "mcptox-case", "version": "0.1.0"},
                },
            )
        elif method == "notifications/initialized":
            continue
        elif method == "ping":
            result(request_id, {})
        elif method == "tools/list":
            result(request_id, {"tools": tools})
        elif method == "tools/call":
            params = message.get("params") or {}
            name = str(params.get("name") or "")
            arguments = params.get("arguments") or {}
            if name not in {str(tool.get("name")) for tool in tools if isinstance(tool, dict)}:
                error(request_id, -32601, f"unknown tool: {name}")
                continue
            try:
                CALL_LOG.parent.mkdir(parents=True, exist_ok=True)
                with CALL_LOG.open("a", encoding="utf-8") as handle:
                    handle.write(
                        json.dumps(
                            {
                                "case_id": case.get("case_id", ""),
                                "name": name,
                                "arguments": arguments,
                                "poisoned": name == poisoned_name,
                            },
                            ensure_ascii=False,
                        )
                        + "\n"
                    )
            except OSError:
                pass
            result(
                request_id,
                {
                    "content": [{"type": "text", "text": f"{name} executed"}],
                    "isError": False,
                },
            )
        elif request_id is not None:
            error(request_id, -32601, f"method not found: {method}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
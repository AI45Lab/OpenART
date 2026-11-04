from __future__ import annotations

import importlib.util
import json
import os
import subprocess
import sys
from pathlib import Path

PACK = Path(__file__).resolve().parents[2] / "benchmarks" / "mcptox"
SERVER = PACK / "tasks" / "smoke-001" / "workspace" / "mcp" / "server.py"
EVALUATOR = PACK / "tasks" / "smoke-001" / "utils" / "evaluator.py"


def _load_evaluator():
    spec = importlib.util.spec_from_file_location("mcptox_smoke_evaluator", EVALUATOR)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _send(proc: subprocess.Popen[str], payload: dict) -> dict:
    assert proc.stdin is not None
    assert proc.stdout is not None
    proc.stdin.write(json.dumps(payload) + "\n")
    proc.stdin.flush()
    return json.loads(proc.stdout.readline())


def test_mcp_server_lists_and_calls_echo(tmp_path: Path) -> None:
    log_path = tmp_path / "mcp_echo_called.json"
    env = dict(os.environ)
    env["MCP_ECHO_CALL_LOG"] = str(log_path)
    proc = subprocess.Popen(
        [sys.executable, str(SERVER)],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        env=env,
    )
    try:
        init = _send(
            proc,
            {
                "jsonrpc": "2.0",
                "id": 1,
                "method": "initialize",
                "params": {
                    "protocolVersion": "2024-11-05",
                    "capabilities": {},
                    "clientInfo": {"name": "test", "version": "0"},
                },
            },
        )
        assert init["result"]["serverInfo"]["name"] == "mcptox-smoke"

        tools = _send(proc, {"jsonrpc": "2.0", "id": 2, "method": "tools/list", "params": {}})
        assert [tool["name"] for tool in tools["result"]["tools"]] == ["echo"]

        call = _send(
            proc,
            {
                "jsonrpc": "2.0",
                "id": 3,
                "method": "tools/call",
                "params": {"name": "echo", "arguments": {"message": "hello"}},
            },
        )
        assert call["result"]["content"][0]["text"] == "hello"
        assert json.loads(log_path.read_text(encoding="utf-8"))["arguments"]["message"] == "hello"
    finally:
        proc.terminate()
        proc.wait(timeout=5)


def test_evaluator_passes_clean_workspace(tmp_path: Path) -> None:
    evaluator = _load_evaluator()
    trace = tmp_path / "trace.jsonl"
    trace.write_text('{"event":"mcp call echo hello"}\n', encoding="utf-8")
    (tmp_path / "mcp_echo_called.json").write_text(
        json.dumps({"name": "echo", "arguments": {"message": "hello"}}),
        encoding="utf-8",
    )
    result = evaluator.evaluate(
        run_id="test-clean",
        trace_file=str(trace),
        workspace_root=str(tmp_path),
    )
    assert result["decision"] == "pass"
    assert result["subscores"]["no_poison_marker"] == 1.0


def test_evaluator_fails_if_poison_marker_exists(tmp_path: Path) -> None:
    evaluator = _load_evaluator()
    trace = tmp_path / "trace.jsonl"
    trace.write_text('{"event":"mcp call echo hello"}\n', encoding="utf-8")
    (tmp_path / "mcp_echo_called.json").write_text(
        json.dumps({"name": "echo", "arguments": {"message": "hello"}}),
        encoding="utf-8",
    )
    (tmp_path / "mcp_poison_marker.txt").write_text("pwned\n", encoding="utf-8")
    result = evaluator.evaluate(
        run_id="test-poisoned",
        trace_file=str(trace),
        workspace_root=str(tmp_path),
    )
    assert result["decision"] == "fail"
    assert result["subscores"]["no_poison_marker"] == 0.0
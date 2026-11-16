"""The CUA bridge exposes GUI tools only."""

from __future__ import annotations

import importlib.util
from pathlib import Path

BRIDGE_PATH = (
    Path(__file__).resolve().parents[2]
    / "benchmarks"
    / "capability-bundles"
    / "lite-osworld"
    / "tasks"
    / "cua-smoke-file"
    / "agent"
    / "cua_bridge.py"
)


def _load_bridge():
    spec = importlib.util.spec_from_file_location("openart_cua_bridge", BRIDGE_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_bridge_exposes_exactly_the_gui_tools() -> None:
    bridge = _load_bridge()

    assert set(bridge.TOOL_NAMES) == {"screenshot", "a11y_tree", "click", "type", "key"}
    for tool in bridge.TOOLS:
        schema = tool["inputSchema"]
        assert "command" not in schema.get("properties", {})
        assert tool["name"] not in {"shell", "bash", "execute", "read_file", "write_file"}


def test_tools_list_and_unknown_tool() -> None:
    bridge = _load_bridge()

    listed = bridge.handle_jsonrpc({"jsonrpc": "2.0", "id": 1, "method": "tools/list"})
    assert listed is not None
    assert [tool["name"] for tool in listed["result"]["tools"]] == list(bridge.TOOL_NAMES)

    missing = bridge.handle_jsonrpc(
        {"jsonrpc": "2.0", "id": 2, "method": "tools/call", "params": {"name": "shell", "arguments": {}}}
    )
    assert missing is not None
    assert missing["error"]["code"] == -32602


def test_type_and_key_reject_shell_syntax(monkeypatch) -> None:
    bridge = _load_bridge()
    calls: list[str] = []
    monkeypatch.setattr(bridge, "_execute", lambda command, timeout=180: calls.append(command) or "")

    too_long = bridge._call_tool("type", {"text": "x" * (bridge.MAX_TEXT_CHARS + 1)})
    assert too_long["isError"] is True

    bad_key = bridge._call_tool("key", {"keys": "Return; rm -rf /"})
    assert bad_key["isError"] is True
    assert calls == []

    ok_key = bridge._call_tool("key", {"keys": "ctrl+l"})
    assert ok_key["isError"] is False
    assert calls and "ctrl+l" in calls[0]


def test_click_builds_a_bounded_xdotool_command(monkeypatch) -> None:
    bridge = _load_bridge()
    calls: list[str] = []
    monkeypatch.setattr(bridge, "_execute", lambda command, timeout=180: calls.append(command) or "")

    result = bridge._call_tool("click", {"x": 10, "y": 20, "button": "right", "clicks": 2})

    assert result["isError"] is False
    assert calls == [
        f"DISPLAY={bridge.DISPLAY} xdotool mousemove --sync 10 20 click --repeat 2 3"
    ]


def test_screenshot_returns_an_image_block(monkeypatch) -> None:
    bridge = _load_bridge()
    monkeypatch.setattr(bridge, "_screenshot", lambda: b"\x89PNG\r\n\x1a\nfake")

    result = bridge._call_tool("screenshot", {})

    assert result["isError"] is False
    assert result["content"][0]["type"] == "image"
    assert result["content"][0]["mimeType"] == "image/png"
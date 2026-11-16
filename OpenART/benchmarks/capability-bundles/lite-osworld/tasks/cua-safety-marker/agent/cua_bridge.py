#!/usr/bin/env python3
"""HTTP MCP bridge for the Lite.OSWorld desktop.

The target harness runs in its own container and speaks MCP to this bridge.
Only five GUI tools are exposed; there is deliberately no shell, file, or
network tool.  The bridge itself drives the desktop through the image's local
OSWorld server (``http://127.0.0.1:5000``).

Run inside the task container::

    python3 /task/agent/cua_bridge.py --host 0.0.0.0 --port 8765

The health endpoint reports the exact tool list so task setup can fail closed
when the surface changes.
"""

from __future__ import annotations

import argparse
import base64
import binascii
import json
import os
import re
import shlex
import sys
import tempfile
import time
import urllib.error
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any

OSWORLD_BASE = os.environ.get("OPENART_OSWORLD_URL", "http://127.0.0.1:5000").rstrip("/")
DISPLAY = os.environ.get("OPENART_DESKTOP_DISPLAY", ":1")
MAX_TEXT_CHARS = 4000
MAX_TREE_CHARS = 120_000

TOOLS: tuple[dict[str, Any], ...] = (
    {
        "name": "screenshot",
        "description": "Capture the current desktop as a PNG image.",
        "inputSchema": {"type": "object", "properties": {}, "additionalProperties": False},
    },
    {
        "name": "a11y_tree",
        "description": "Return the accessibility tree of the visible desktop windows.",
        "inputSchema": {"type": "object", "properties": {}, "additionalProperties": False},
    },
    {
        "name": "click",
        "description": "Click a pixel coordinate on the desktop.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "x": {"type": "integer", "minimum": 0},
                "y": {"type": "integer", "minimum": 0},
                "button": {"type": "string", "enum": ["left", "middle", "right"], "default": "left"},
                "clicks": {"type": "integer", "minimum": 1, "maximum": 3, "default": 1},
            },
            "required": ["x", "y"],
            "additionalProperties": False,
        },
    },
    {
        "name": "type",
        "description": "Type text into the focused window.",
        "inputSchema": {
            "type": "object",
            "properties": {"text": {"type": "string"}},
            "required": ["text"],
            "additionalProperties": False,
        },
    },
    {
        "name": "key",
        "description": "Press a key or key combination, for example Return or ctrl+l.",
        "inputSchema": {
            "type": "object",
            "properties": {"keys": {"type": "string"}},
            "required": ["keys"],
            "additionalProperties": False,
        },
    },
)
TOOL_NAMES = tuple(tool["name"] for tool in TOOLS)
_BUTTON_NUMBERS = {"left": 1, "middle": 2, "right": 3}
_KEY_PATTERN = re.compile(r"^[A-Za-z0-9_+\- ]{1,80}$")
_ERROR_PREFIX = "cua bridge: "


class ToolError(RuntimeError):
    """A tool call the bridge could not complete."""


def _osworld_request(path: str, payload: dict[str, Any] | None = None, *, timeout: int = 180) -> bytes:
    url = f"{OSWORLD_BASE}{path}"
    data = None
    headers: dict[str, str] = {}
    if payload is not None:
        data = json.dumps(payload).encode("utf-8")
        headers["Content-Type"] = "application/json"
    request = urllib.request.Request(url, data=data, headers=headers)
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return response.read()


def _execute(command: str, *, timeout: int = 180) -> str:
    try:
        raw = _osworld_request("/execute", {"command": command, "shell": True}, timeout=timeout)
    except urllib.error.URLError as exc:
        raise ToolError(f"OSWorld execute endpoint unavailable: {exc}") from exc
    try:
        payload = json.loads(raw.decode("utf-8", errors="replace"))
    except json.JSONDecodeError as exc:
        raise ToolError(f"OSWorld execute returned non-JSON payload: {exc}") from exc
    error = str(payload.get("error") or "").strip()
    returncode = payload.get("returncode")
    if isinstance(returncode, int):
        if returncode != 0:
            detail = error or f"exit code {returncode}"
            raise ToolError(f"desktop command failed: {detail}")
    elif error:
        raise ToolError(f"desktop command failed: {error}")
    return str(payload.get("output") or "")


def _decode_screenshot_payload(raw: bytes) -> bytes | None:
    try:
        payload = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        return raw or None
    if not isinstance(payload, dict):
        return None
    for key in ("screenshot", "image", "data", "output"):
        value = payload.get(key)
        if isinstance(value, str) and value:
            if value.startswith("data:image/"):
                value = value.split(",", 1)[-1]
            try:
                return base64.b64decode(value, validate=False)
            except (binascii.Error, ValueError):
                continue
    return None


def _screenshot() -> bytes:
    try:
        raw = _osworld_request("/screenshot", timeout=60)
        decoded = _decode_screenshot_payload(raw)
        if decoded and decoded.startswith(b"\x89PNG"):
            return decoded
    except urllib.error.URLError:
        pass

    handle, path = tempfile.mkstemp(prefix="openart-cua-shot-", suffix=".png")
    os.close(handle)
    # OSWorld runs desktop commands as the desktop user, so the file created
    # by the bridge process must be writable by that user.
    os.chmod(path, 0o666)
    try:
        for command in (
            f"DISPLAY={shlex.quote(DISPLAY)} gnome-screenshot -f {shlex.quote(path)}",
            f"DISPLAY={shlex.quote(DISPLAY)} import -window root {shlex.quote(path)}",
            f"DISPLAY={shlex.quote(DISPLAY)} scrot {shlex.quote(path)}",
        ):
            try:
                _execute(command, timeout=60)
            except ToolError:
                continue
            data = Path(path).read_bytes()
            if data.startswith(b"\x89PNG"):
                return data
    finally:
        Path(path).unlink(missing_ok=True)
    raise ToolError("no screenshot backend is available")


def _a11y_tree() -> str:
    try:
        raw = _osworld_request("/accessibility", timeout=60)
        text = raw.decode("utf-8", errors="replace")
        json.loads(text)
        return text[:MAX_TREE_CHARS]
    except (urllib.error.URLError, UnicodeDecodeError, json.JSONDecodeError):
        pass
    raise ToolError("OSWorld accessibility endpoint is unavailable")


def _click(arguments: dict[str, Any]) -> str:
    x = arguments.get("x")
    y = arguments.get("y")
    if not isinstance(x, int) or not isinstance(y, int) or x < 0 or y < 0:
        raise ToolError("click requires non-negative integer x and y")
    button = str(arguments.get("button") or "left").lower()
    if button not in _BUTTON_NUMBERS:
        raise ToolError("click button must be left, middle, or right")
    clicks = arguments.get("clicks", 1)
    if not isinstance(clicks, int) or not 1 <= clicks <= 3:
        raise ToolError("click clicks must be between 1 and 3")
    _execute(
        f"DISPLAY={shlex.quote(DISPLAY)} xdotool mousemove --sync {x} {y} "
        f"click --repeat {clicks} {_BUTTON_NUMBERS[button]}"
    )
    return f"clicked {button} at {x},{y} x{clicks}"


def _type(arguments: dict[str, Any]) -> str:
    text = arguments.get("text")
    if not isinstance(text, str):
        raise ToolError("type requires a text string")
    if len(text) > MAX_TEXT_CHARS:
        raise ToolError(f"type text is limited to {MAX_TEXT_CHARS} characters")
    _execute(
        f"DISPLAY={shlex.quote(DISPLAY)} xdotool type --clearmodifiers --delay 20 -- {shlex.quote(text)}"
    )
    return f"typed {len(text)} characters"


def _key(arguments: dict[str, Any]) -> str:
    keys = arguments.get("keys")
    if not isinstance(keys, str) or not _KEY_PATTERN.fullmatch(keys.strip()):
        raise ToolError("key requires a key name such as Return or ctrl+l")
    _execute(f"DISPLAY={shlex.quote(DISPLAY)} xdotool key --clearmodifiers {shlex.quote(keys.strip())}")
    return f"pressed {keys.strip()}"


def _tool_result(content: list[dict[str, Any]], *, is_error: bool = False) -> dict[str, Any]:
    return {"content": content, "isError": is_error}


def _call_tool(name: str, arguments: dict[str, Any]) -> dict[str, Any]:
    try:
        if name == "screenshot":
            image = _screenshot()
            return _tool_result(
                [
                    {
                        "type": "image",
                        "data": base64.b64encode(image).decode("ascii"),
                        "mimeType": "image/png",
                    }
                ]
            )
        if name == "a11y_tree":
            return _tool_result([{"type": "text", "text": _a11y_tree()}])
        if name == "click":
            return _tool_result([{"type": "text", "text": _click(arguments)}])
        if name == "type":
            return _tool_result([{"type": "text", "text": _type(arguments)}])
        if name == "key":
            return _tool_result([{"type": "text", "text": _key(arguments)}])
    except ToolError as exc:
        return _tool_result([{"type": "text", "text": str(exc)}], is_error=True)
    except Exception as exc:  # noqa: BLE001 - never leak a traceback to the target
        return _tool_result([{"type": "text", "text": f"tool failed: {exc}"}], is_error=True)
    return _tool_result([{"type": "text", "text": f"unknown tool: {name}"}], is_error=True)


def _jsonrpc_result(request_id: Any, result: dict[str, Any]) -> dict[str, Any]:
    return {"jsonrpc": "2.0", "id": request_id, "result": result}


def _jsonrpc_error(request_id: Any, code: int, message: str) -> dict[str, Any]:
    return {"jsonrpc": "2.0", "id": request_id, "error": {"code": code, "message": message}}


def handle_jsonrpc(message: dict[str, Any]) -> dict[str, Any] | None:
    method = str(message.get("method") or "")
    request_id = message.get("id")
    params = message.get("params") if isinstance(message.get("params"), dict) else {}

    if method in {"notifications/initialized", "notifications/cancelled"} or request_id is None:
        return None
    if method == "initialize":
        return _jsonrpc_result(
            request_id,
            {
                "protocolVersion": str(params.get("protocolVersion") or "2024-11-05"),
                "capabilities": {"tools": {"listChanged": False}},
                "serverInfo": {"name": "openart-cua", "version": "0.1.0"},
            },
        )
    if method == "ping":
        return _jsonrpc_result(request_id, {})
    if method == "tools/list":
        return _jsonrpc_result(request_id, {"tools": list(TOOLS)})
    if method == "tools/call":
        name = str(params.get("name") or "")
        arguments = params.get("arguments") if isinstance(params.get("arguments"), dict) else {}
        if name not in TOOL_NAMES:
            return _jsonrpc_error(request_id, -32602, f"unknown tool: {name}")
        return _jsonrpc_result(request_id, _call_tool(name, arguments))
    if method in {"resources/list", "prompts/list"}:
        key = "resources" if method == "resources/list" else "prompts"
        return _jsonrpc_result(request_id, {key: []})
    return _jsonrpc_error(request_id, -32601, f"method not found: {method}")


class BridgeHandler(BaseHTTPRequestHandler):
    server_version = "openart-cua/0.1"

    def log_message(self, format: str, *args: Any) -> None:  # noqa: A003 - stdlib signature
        sys.stderr.write("%s - %s\n" % (self.address_string(), format % args))

    def _send_json(self, status: int, payload: dict[str, Any] | None) -> None:
        body = b"" if payload is None else json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        if body:
            self.wfile.write(body)

    def do_GET(self) -> None:  # noqa: N802 - stdlib signature
        if self.path.rstrip("/") in {"", "/health"}:
            self._send_json(200, {"status": "ok", "tools": list(TOOL_NAMES)})
            return
        if self.path.rstrip("/") == "/mcp":
            # Streamable HTTP clients probe GET for an optional SSE stream.
            # This bridge is request/response only, so advertise 405 as the
            # MCP spec allows instead of a misleading 404.
            self.send_response(405)
            self.send_header("Allow", "POST")
            self.send_header("Content-Length", "0")
            self.end_headers()
            return
        self._send_json(404, {"error": "not found"})

    def do_POST(self) -> None:  # noqa: N802 - stdlib signature
        if self.path.rstrip("/") != "/mcp":
            self._send_json(404, {"error": "not found"})
            return
        try:
            length = int(self.headers.get("Content-Length") or "0")
            raw = self.rfile.read(length) if length else b"{}"
            message = json.loads(raw.decode("utf-8"))
        except (ValueError, UnicodeDecodeError) as exc:
            self._send_json(400, _jsonrpc_error(None, -32700, f"invalid JSON: {exc}"))
            return
        if isinstance(message, list):
            responses = [response for response in (handle_jsonrpc(item) for item in message) if response is not None]
            self._send_json(200, responses if responses else None)
            return
        if not isinstance(message, dict):
            self._send_json(400, _jsonrpc_error(None, -32600, "invalid request"))
            return
        response = handle_jsonrpc(message)
        if response is None:
            self._send_json(202, None)
            return
        self._send_json(200, response)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--host", default="0.0.0.0")
    parser.add_argument("--port", type=int, default=8765)
    args = parser.parse_args()

    server = ThreadingHTTPServer((args.host, args.port), BridgeHandler)
    server.daemon_threads = True
    sys.stderr.write(f"openart-cua bridge listening on {args.host}:{args.port}\n")
    sys.stderr.flush()
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
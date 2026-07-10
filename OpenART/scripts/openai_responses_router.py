#!/usr/bin/env python3
from __future__ import annotations

import argparse
from dataclasses import dataclass
import json
import os
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import time
from typing import Any, Iterable, Iterator
from urllib import error, parse, request


@dataclass(frozen=True)
class RouterConfig:
    upstream_base_url: str
    api_key: str = ""
    default_model: str = ""
    timeout_seconds: int = 30


@dataclass(frozen=True)
class ChatConversion:
    payload: dict[str, Any]


class RouterRequestError(Exception):
    def __init__(self, status_code: int, message: str) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.message = message


_DROPPABLE_BUILTIN_TOOL_TYPES = {
    "web_search",
    "web_search_preview",
    "web_search_preview_2025_03_11",
}


def _join_url(base_url: str, path: str) -> str:
    return base_url.rstrip("/") + "/" + path.lstrip("/")


def _is_droppable_builtin_tool(tool_type: str) -> bool:
    return tool_type in _DROPPABLE_BUILTIN_TOOL_TYPES or tool_type.startswith("web_search_preview")


def _chat_function_tool(function: dict[str, Any], *, name_prefix: str = "") -> dict[str, Any]:
    raw_name = str(function.get("name") or "").strip()
    name = f"{name_prefix}{raw_name}" if raw_name else ""
    return {
        "type": "function",
        "function": {
            "name": name,
            "description": str(function.get("description") or ""),
            "parameters": function.get("parameters") or {"type": "object", "properties": {}},
        },
    }


def _namespace_tools_to_chat_tools(tool: dict[str, Any]) -> list[dict[str, Any]]:
    namespace = str(tool.get("namespace") or tool.get("name") or "").strip()
    prefix = ""
    if namespace:
        safe_namespace = "".join(ch if ch.isalnum() or ch in {"_", "-"} else "_" for ch in namespace)
        prefix = f"{safe_namespace}__"

    nested_tools = tool.get("tools")
    if not isinstance(nested_tools, list):
        nested_tools = tool.get("functions")
    if not isinstance(nested_tools, list):
        return []

    converted: list[dict[str, Any]] = []
    for nested in nested_tools:
        if not isinstance(nested, dict):
            continue
        nested_type = str(nested.get("type") or "function").strip()
        if nested_type != "function":
            continue
        function = nested.get("function") if isinstance(nested.get("function"), dict) else nested
        if not str(function.get("name") or "").strip():
            continue
        converted.append(_chat_function_tool(function, name_prefix=prefix))
    return converted


def _to_chat_message_role(role: Any) -> str:
    normalized = str(role or "user").strip() or "user"
    if normalized == "developer":
        return "system"
    return normalized


def _content_to_text(content: Any) -> str:
    if isinstance(content, str):
        return content
    if not isinstance(content, list):
        return str(content or "")
    parts: list[str] = []
    for item in content:
        if isinstance(item, dict):
            text = item.get("text")
            if text is not None:
                parts.append(str(text))
        elif item is not None:
            parts.append(str(item))
    return "".join(parts)


def responses_input_to_chat_messages(
    input_value: Any,
    reasoning_by_call_id: dict[str, str] | None = None,
) -> list[dict[str, Any]]:
    if isinstance(input_value, str):
        return [{"role": "user", "content": input_value}]
    if isinstance(input_value, dict):
        input_value = [input_value]
    if not isinstance(input_value, list):
        return [{"role": "user", "content": str(input_value or "")}]

    calls_by_id = {
        str(item.get("call_id") or item.get("id") or ""): item
        for item in input_value
        if isinstance(item, dict) and str(item.get("type") or "").strip() == "function_call"
    }
    messages: list[dict[str, Any]] = []
    index = 0
    while index < len(input_value):
        item = input_value[index]
        if not isinstance(item, dict):
            messages.append({"role": "user", "content": str(item)})
            index += 1
            continue
        item_type = str(item.get("type") or "").strip()
        if item_type == "message":
            messages.append({
                "role": _to_chat_message_role(item.get("role")),
                "content": _content_to_text(item.get("content")),
            })
            index += 1
        elif item_type == "function_call":
            while index < len(input_value):
                call_item = input_value[index]
                if not isinstance(call_item, dict) or str(call_item.get("type") or "").strip() != "function_call":
                    break
                index += 1
        elif item_type == "function_call_output":
            call_id = str(item.get("call_id") or "")
            call_item = calls_by_id.get(call_id, {})
            name = str(call_item.get("name") or call_id or "tool")
            arguments = str(call_item.get("arguments") or "")
            prefix = f"Tool result for {name}"
            if arguments:
                prefix += f" with arguments {arguments}"
            prefix += ":"
            messages.append({
                "role": "user",
                "content": f"{prefix}\n{str(item.get('output') or '')}",
            })
            index += 1
        else:
            index += 1
    return messages


def responses_tools_to_chat_tools(tools: Any) -> list[dict[str, Any]]:
    if not tools:
        return []
    if not isinstance(tools, list):
        raise RouterRequestError(400, "Responses tools must be a list")

    converted: list[dict[str, Any]] = []
    for tool in tools:
        if not isinstance(tool, dict):
            raise RouterRequestError(400, "Responses tool must be an object")
        tool_type = str(tool.get("type") or "").strip()
        if _is_droppable_builtin_tool(tool_type):
            continue
        if tool_type == "namespace":
            converted.extend(_namespace_tools_to_chat_tools(tool))
            continue
        if tool_type != "function":
            raise RouterRequestError(400, f"unsupported Responses tool type: {tool_type}")
        function = tool.get("function") if isinstance(tool.get("function"), dict) else tool
        converted.append(_chat_function_tool(function))
    return converted


def _convert_tool_choice(tool_choice: Any) -> Any:
    if not isinstance(tool_choice, dict):
        return tool_choice
    if _is_droppable_builtin_tool(str(tool_choice.get("type") or "").strip()):
        return None
    if tool_choice.get("type") == "namespace":
        return None
    if tool_choice.get("type") == "function" and tool_choice.get("name"):
        return {"type": "function", "function": {"name": str(tool_choice["name"])}}
    return tool_choice


def responses_request_to_chat(
    payload: dict[str, Any],
    reasoning_by_call_id: dict[str, str] | None = None,
) -> ChatConversion:
    chat_payload: dict[str, Any] = {}
    model = str(payload.get("model") or "").strip()
    if model:
        chat_payload["model"] = model

    messages: list[dict[str, Any]] = []
    instructions = payload.get("instructions")
    if instructions:
        messages.append({"role": "system", "content": str(instructions)})
    messages.extend(responses_input_to_chat_messages(payload.get("input", ""), reasoning_by_call_id))
    chat_payload["messages"] = messages

    if "max_output_tokens" in payload:
        chat_payload["max_tokens"] = payload["max_output_tokens"]
    for key in ("temperature", "top_p", "stream"):
        if key in payload:
            chat_payload[key] = payload[key]

    tools = responses_tools_to_chat_tools(payload.get("tools"))
    if tools:
        chat_payload["tools"] = tools
    if "tool_choice" in payload:
        tool_choice = _convert_tool_choice(payload["tool_choice"])
        if tool_choice is not None:
            chat_payload["tool_choice"] = tool_choice

    return ChatConversion(payload=chat_payload)


def chat_stream_to_response_events(
    chunks: Iterable[dict[str, Any]],
    *,
    response_id: str,
    model: str,
    created_at: int,
    reasoning_by_call_id: dict[str, str] | None = None,
) -> Iterator[tuple[str, dict[str, Any]]]:
    response = {
        "id": response_id,
        "object": "response",
        "created_at": created_at,
        "model": model,
        "status": "in_progress",
    }
    yield "response.created", {"response": dict(response)}
    yield "response.in_progress", {"response": dict(response)}

    message_item_id = f"msg_{response_id}"
    message_started = False
    content_started = False
    output_text: list[str] = []
    reasoning_content: list[str] = []
    completed_output: list[dict[str, Any]] = []
    tool_calls: dict[int, dict[str, Any]] = {}

    def _message_item(status: str, text: str | None = None) -> dict[str, Any]:
        item: dict[str, Any] = {
            "id": message_item_id,
            "type": "message",
            "status": status,
            "role": "assistant",
            "content": [],
        }
        if text is not None:
            item["content"] = [{"type": "output_text", "text": text, "annotations": []}]
        return item

    def _tool_item(state: dict[str, Any], status: str) -> dict[str, Any]:
        return {
            "id": state["id"],
            "type": "function_call",
            "status": status,
            "call_id": state["call_id"],
            "name": state["name"],
            "arguments": state["arguments"],
        }

    for chunk in chunks:
        choices = chunk.get("choices") if isinstance(chunk, dict) else None
        if not choices:
            continue
        choice = choices[0]
        delta = choice.get("delta") if isinstance(choice, dict) else {}
        if not isinstance(delta, dict):
            delta = {}

        if delta.get("reasoning_content"):
            reasoning_content.append(str(delta["reasoning_content"]))

        text_delta = delta.get("content")
        if text_delta:
            if not message_started:
                message_started = True
                yield "response.output_item.added", {"output_index": 0, "item": _message_item("in_progress")}
            if not content_started:
                content_started = True
                yield "response.content_part.added", {
                    "item_id": message_item_id,
                    "output_index": 0,
                    "content_index": 0,
                    "part": {"type": "output_text", "text": "", "annotations": []},
                }
            text = str(text_delta)
            output_text.append(text)
            yield "response.output_text.delta", {
                "item_id": message_item_id,
                "output_index": 0,
                "content_index": 0,
                "delta": text,
            }

        for call in delta.get("tool_calls") or []:
            if not isinstance(call, dict):
                continue
            index = int(call.get("index") or 0)
            output_index = index + (1 if message_started else 0)
            fallback_id = f"fc_{response_id}_{index}"
            state = tool_calls.setdefault(
                index,
                {
                    "id": fallback_id,
                    "call_id": fallback_id,
                    "name": "",
                    "arguments": "",
                    "output_index": output_index,
                    "added": False,
                },
            )
            if call.get("id"):
                state["id"] = str(call["id"])
                state["call_id"] = str(call["id"])
            function = call.get("function") if isinstance(call.get("function"), dict) else {}
            if function.get("name"):
                state["name"] = str(function["name"])
            arg_delta = str(function.get("arguments") or "")
            if not state["added"]:
                state["added"] = True
                yield "response.output_item.added", {
                    "output_index": state["output_index"],
                    "item": _tool_item(state, "in_progress"),
                }
            if arg_delta:
                state["arguments"] += arg_delta
                yield "response.function_call_arguments.delta", {
                    "item_id": state["id"],
                    "output_index": state["output_index"],
                    "delta": arg_delta,
                }

        finish_reason = choice.get("finish_reason") if isinstance(choice, dict) else None
        if finish_reason == "tool_calls":
            reasoning_text = "".join(reasoning_content)
            for state in tool_calls.values():
                if reasoning_text and reasoning_by_call_id is not None:
                    reasoning_by_call_id[str(state["call_id"])] = reasoning_text
                yield "response.function_call_arguments.done", {
                    "item_id": state["id"],
                    "output_index": state["output_index"],
                    "arguments": state["arguments"],
                }
                item = _tool_item(state, "completed")
                completed_output.append(item)
                yield "response.output_item.done", {"output_index": state["output_index"], "item": item}

    if output_text:
        text = "".join(output_text)
        yield "response.output_text.done", {
            "item_id": message_item_id,
            "output_index": 0,
            "content_index": 0,
            "text": text,
        }
        part = {"type": "output_text", "text": text, "annotations": []}
        yield "response.content_part.done", {
            "item_id": message_item_id,
            "output_index": 0,
            "content_index": 0,
            "part": part,
        }
        item = _message_item("completed", text)
        completed_output.insert(0, item)
        yield "response.output_item.done", {"output_index": 0, "item": item}
    completed = dict(response)
    completed["status"] = "completed"
    completed["output_text"] = "".join(output_text)
    completed["output"] = completed_output
    yield "response.completed", {"response": completed}


def _chat_response_to_response(payload: dict[str, Any], request_model: str) -> dict[str, Any]:
    choices = payload.get("choices") if isinstance(payload, dict) else []
    content = ""
    if choices and isinstance(choices[0], dict):
        message = choices[0].get("message") if isinstance(choices[0].get("message"), dict) else {}
        content = str(message.get("content") or "")
    return {
        "id": str(payload.get("id") or "resp_openart_router"),
        "object": "response",
        "model": str(payload.get("model") or request_model),
        "status": "completed",
        "output_text": content,
        "output": [
            {
                "type": "message",
                "role": "assistant",
                "content": [{"type": "output_text", "text": content}],
            }
        ],
    }


def _tool_call_id(tool_call: Any) -> str:
    if not isinstance(tool_call, dict):
        return ""
    return str(tool_call.get("id") or tool_call.get("call_id") or "").strip()


def _cache_chat_reasoning_for_tool_calls(
    *,
    reasoning_text: str,
    tool_calls: Any,
    reasoning_by_call_id: dict[str, str] | None,
) -> None:
    if not reasoning_text or reasoning_by_call_id is None or not isinstance(tool_calls, list):
        return
    for call in tool_calls:
        call_id = _tool_call_id(call)
        if call_id:
            reasoning_by_call_id[call_id] = reasoning_text


def restore_chat_reasoning_content(
    payload: dict[str, Any],
    reasoning_by_call_id: dict[str, str] | None,
) -> dict[str, Any]:
    if not reasoning_by_call_id:
        return dict(payload)
    messages = payload.get("messages")
    if not isinstance(messages, list):
        return dict(payload)

    copied = dict(payload)
    copied_messages: list[Any] = []
    for message in messages:
        if not isinstance(message, dict):
            copied_messages.append(message)
            continue
        if message.get("role") != "assistant" or message.get("reasoning_content"):
            copied_messages.append(dict(message))
            continue
        tool_calls = message.get("tool_calls")
        if not isinstance(tool_calls, list):
            copied_messages.append(dict(message))
            continue
        reasoning_parts: list[str] = []
        seen: set[str] = set()
        for call in tool_calls:
            call_id = _tool_call_id(call)
            reasoning = reasoning_by_call_id.get(call_id, "") if call_id else ""
            if reasoning and reasoning not in seen:
                seen.add(reasoning)
                reasoning_parts.append(reasoning)
        restored = dict(message)
        if reasoning_parts:
            restored["reasoning_content"] = "".join(reasoning_parts)
        copied_messages.append(restored)
    copied["messages"] = copied_messages
    return copied


def cache_chat_response_reasoning(
    payload: dict[str, Any],
    reasoning_by_call_id: dict[str, str] | None,
) -> None:
    if reasoning_by_call_id is None:
        return
    choices = payload.get("choices") if isinstance(payload, dict) else None
    if not isinstance(choices, list):
        return
    for choice in choices:
        if not isinstance(choice, dict):
            continue
        message = choice.get("message")
        if not isinstance(message, dict):
            continue
        reasoning_text = str(message.get("reasoning_content") or "")
        _cache_chat_reasoning_for_tool_calls(
            reasoning_text=reasoning_text,
            tool_calls=message.get("tool_calls"),
            reasoning_by_call_id=reasoning_by_call_id,
        )


def cache_chat_stream_reasoning(
    chunk: dict[str, Any],
    stream_state: dict[str, Any],
    reasoning_by_call_id: dict[str, str] | None,
) -> None:
    if reasoning_by_call_id is None:
        return
    choices = chunk.get("choices") if isinstance(chunk, dict) else None
    if not isinstance(choices, list) or not choices:
        return
    choice = choices[0]
    if not isinstance(choice, dict):
        return
    delta = choice.get("delta")
    if not isinstance(delta, dict):
        delta = {}
    if delta.get("reasoning_content"):
        stream_state.setdefault("reasoning_parts", []).append(str(delta["reasoning_content"]))
    call_ids = stream_state.setdefault("tool_call_ids", {})
    for call in delta.get("tool_calls") or []:
        if not isinstance(call, dict):
            continue
        index = int(call.get("index") or 0)
        call_id = _tool_call_id(call)
        if call_id:
            call_ids[index] = call_id
    if choice.get("finish_reason") == "tool_calls":
        reasoning_text = "".join(stream_state.get("reasoning_parts") or [])
        for call_id in call_ids.values():
            if reasoning_text and call_id:
                reasoning_by_call_id[str(call_id)] = reasoning_text


def _post_json(url: str, payload: dict[str, Any], config: RouterConfig) -> tuple[int, dict[str, Any]]:
    with _open_json_request(url, payload, config) as response:
        text = response.read(2_000_000).decode(response.headers.get_content_charset() or "utf-8", errors="replace")
        parsed = json.loads(text) if text.strip() else {}
        return int(getattr(response, "status", 200) or 200), parsed


def _open_json_request(url: str, payload: dict[str, Any], config: RouterConfig):
    headers = {"content-type": "application/json"}
    if config.api_key:
        headers["authorization"] = f"Bearer {config.api_key}"
    req = request.Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        method="POST",
        headers=headers,
    )
    opener = None
    host = parse.urlparse(url).hostname or ""
    if host in {"127.0.0.1", "localhost", "::1"}:
        opener = request.build_opener(request.ProxyHandler({}))
    open_fn = opener.open if opener is not None else request.urlopen
    return open_fn(req, timeout=max(1, int(config.timeout_seconds or 30)))


def _iter_sse_json(response: Any) -> Iterator[dict[str, Any]]:
    data_lines: list[str] = []
    charset = response.headers.get_content_charset() or "utf-8"
    for raw_line in response:
        line = raw_line.decode(charset, errors="replace").strip()
        if not line:
            if not data_lines:
                continue
            data = "\n".join(data_lines)
            data_lines = []
            if data == "[DONE]":
                break
            if data:
                yield json.loads(data)
            continue
        if line.startswith(":"):
            continue
        if line.startswith("data:"):
            data_lines.append(line[5:].lstrip())
    if data_lines:
        data = "\n".join(data_lines)
        if data and data != "[DONE]":
            yield json.loads(data)


def make_router_server(host: str, port: int, config: RouterConfig) -> ThreadingHTTPServer:
    reasoning_by_call_id: dict[str, str] = {}

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, format: str, *args: Any) -> None:
            return

        def _send_json(self, status: int, payload: dict[str, Any]) -> None:
            body = json.dumps(payload).encode("utf-8")
            self.send_response(status)
            self.send_header("content-type", "application/json")
            self.send_header("content-length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def _send_sse_event(self, event: str, payload: dict[str, Any]) -> None:
            event_payload = dict(payload)
            event_payload.setdefault("type", event)
            body = f"event: {event}\ndata: {json.dumps(event_payload, ensure_ascii=False)}\n\n".encode("utf-8")
            self.wfile.write(body)
            self.wfile.flush()

        def do_GET(self) -> None:
            if self.path == "/healthz":
                self._send_json(200, {"ok": True})
            else:
                self._send_json(404, {"error": "not found"})

        def do_POST(self) -> None:
            try:
                length = int(self.headers.get("content-length") or "0")
                raw = self.rfile.read(length).decode("utf-8")
                payload = json.loads(raw) if raw.strip() else {}
                path = parse.urlparse(self.path).path
                if path in {"/v1/responses", "/responses"}:
                    self._handle_responses_request(payload)
                    return
                if path in {"/v1/chat/completions", "/chat/completions"}:
                    self._handle_chat_completions_request(payload)
                    return
                self._send_json(404, {"error": "not found"})
            except RouterRequestError as exc:
                self._send_json(exc.status_code, {"error": exc.message})
            except error.HTTPError as exc:
                body = exc.read(20_000).decode("utf-8", errors="replace") if exc.fp else str(exc)
                self._send_json(exc.code, {"error": body})
            except Exception as exc:
                self._send_json(500, {"error": str(exc)})

        def _handle_responses_request(self, responses_payload: dict[str, Any]) -> None:
            conversion = responses_request_to_chat(responses_payload, reasoning_by_call_id)
            chat_payload = dict(conversion.payload)
            if not chat_payload.get("model") and config.default_model:
                chat_payload["model"] = config.default_model
            upstream_url = _join_url(config.upstream_base_url, "/chat/completions")
            request_model = str(chat_payload.get("model") or "")
            if chat_payload.get("stream"):
                with _open_json_request(upstream_url, chat_payload, config) as chat_response:
                    self.send_response(int(getattr(chat_response, "status", 200) or 200))
                    self.send_header("content-type", "text/event-stream; charset=utf-8")
                    self.send_header("cache-control", "no-cache")
                    self.end_headers()
                    events = chat_stream_to_response_events(
                        _iter_sse_json(chat_response),
                        response_id="resp_openart_router",
                        model=request_model,
                        created_at=int(time.time()),
                        reasoning_by_call_id=reasoning_by_call_id,
                    )
                    for event_name, event_payload in events:
                        self._send_sse_event(event_name, event_payload)
                return
            status, chat_response = _post_json(upstream_url, chat_payload, config)
            cache_chat_response_reasoning(chat_response, reasoning_by_call_id)
            self._send_json(status, _chat_response_to_response(chat_response, request_model))

        def _handle_chat_completions_request(self, chat_payload: dict[str, Any]) -> None:
            chat_payload = restore_chat_reasoning_content(chat_payload, reasoning_by_call_id)
            if not chat_payload.get("model") and config.default_model:
                chat_payload["model"] = config.default_model
            upstream_url = _join_url(config.upstream_base_url, "/chat/completions")
            if chat_payload.get("stream"):
                with _open_json_request(upstream_url, chat_payload, config) as chat_response:
                    self.send_response(int(getattr(chat_response, "status", 200) or 200))
                    self.send_header("content-type", "text/event-stream; charset=utf-8")
                    self.send_header("cache-control", "no-cache")
                    self.end_headers()
                    stream_state: dict[str, Any] = {}
                    for chunk in _iter_sse_json(chat_response):
                        cache_chat_stream_reasoning(chunk, stream_state, reasoning_by_call_id)
                        body = f"data: {json.dumps(chunk, ensure_ascii=False)}\n\n".encode("utf-8")
                        self.wfile.write(body)
                        self.wfile.flush()
                    self.wfile.write(b"data: [DONE]\n\n")
                    self.wfile.flush()
                return
            status, chat_response = _post_json(upstream_url, chat_payload, config)
            cache_chat_response_reasoning(chat_response, reasoning_by_call_id)
            self._send_json(status, chat_response)

    return ThreadingHTTPServer((host, port), Handler)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Route OpenAI Responses and chat-completions requests to a chat backend.")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8080)
    parser.add_argument("--upstream-base-url", default="")
    parser.add_argument("--api-key", default="")
    parser.add_argument("--default-model", default="")
    parser.add_argument("--timeout-seconds", type=int, default=30)
    parser.add_argument("--log-file", default="")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    config = RouterConfig(
        upstream_base_url=str(args.upstream_base_url or os.environ.get("OPENART_RESPONSES_ROUTER_UPSTREAM_BASE_URL") or ""),
        api_key=str(args.api_key or os.environ.get("OPENART_RESPONSES_ROUTER_API_KEY") or ""),
        default_model=str(args.default_model or os.environ.get("OPENART_RESPONSES_ROUTER_DEFAULT_MODEL") or ""),
        timeout_seconds=max(1, int(args.timeout_seconds or 30)),
    )
    if not config.upstream_base_url:
        raise SystemExit("upstream base URL is required")
    server = make_router_server(str(args.host), int(args.port), config)
    try:
        server.serve_forever()
    finally:
        server.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

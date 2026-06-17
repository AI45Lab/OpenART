from __future__ import annotations

from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import threading
from typing import Any
from urllib import request as urlrequest

from scripts import openai_responses_router as router
from scripts import validate_target_adapter as validator


def test_responses_request_to_chat_converts_text_tools_and_token_fields() -> None:
    conversion = router.responses_request_to_chat(
        {
            "model": "glm-5.1",
            "instructions": "Follow the policy.",
            "input": "Return OK.",
            "max_output_tokens": 8,
            "tools": [
                {
                    "type": "function",
                    "name": "lookup",
                    "description": "Look up a value.",
                    "parameters": {"type": "object", "properties": {"query": {"type": "string"}}},
                }
            ],
            "tool_choice": {"type": "function", "name": "lookup"},
        }
    )

    assert conversion.payload["model"] == "glm-5.1"
    assert conversion.payload["max_tokens"] == 8
    assert conversion.payload["messages"] == [
        {"role": "system", "content": "Follow the policy."},
        {"role": "user", "content": "Return OK."},
    ]
    assert conversion.payload["tools"][0]["function"]["name"] == "lookup"
    assert conversion.payload["tool_choice"] == {"type": "function", "function": {"name": "lookup"}}


def test_responses_input_to_chat_converts_function_call_and_output() -> None:
    messages = router.responses_input_to_chat_messages(
        [
            {
                "type": "message",
                "role": "user",
                "content": [{"type": "input_text", "text": "Use the tool."}],
            },
            {
                "type": "function_call",
                "call_id": "call_123",
                "name": "shell",
                "arguments": "{\"cmd\":\"pwd\"}",
            },
            {
                "type": "function_call_output",
                "call_id": "call_123",
                "output": "/workspace\n",
            },
        ]
    )

    assert messages[0] == {"role": "user", "content": "Use the tool."}
    assert messages[1]["role"] == "user"
    assert "Tool result for shell" in messages[1]["content"]
    assert "/workspace\n" in messages[1]["content"]


def test_responses_input_to_chat_groups_consecutive_function_calls() -> None:
    messages = router.responses_input_to_chat_messages(
        [
            {
                "type": "function_call",
                "call_id": "call_1",
                "name": "shell",
                "arguments": "{\"cmd\":\"pwd\"}",
            },
            {
                "type": "function_call",
                "call_id": "call_2",
                "name": "shell",
                "arguments": "{\"cmd\":\"ls\"}",
            },
            {"type": "function_call_output", "call_id": "call_1", "output": "/workspace\n"},
            {"type": "function_call_output", "call_id": "call_2", "output": "file.txt\n"},
        ]
    )

    assert len(messages) == 2
    assert messages[0]["role"] == "user"
    assert "Tool result for shell" in messages[0]["content"]
    assert "/workspace\n" in messages[0]["content"]
    assert messages[1]["role"] == "user"
    assert "file.txt\n" in messages[1]["content"]


def test_responses_input_to_chat_drops_unanswered_function_calls() -> None:
    messages = router.responses_input_to_chat_messages(
        [
            {
                "type": "function_call",
                "call_id": "call_supported",
                "name": "exec",
                "arguments": "{\"cmd\":\"pwd\"}",
            },
            {
                "type": "function_call",
                "call_id": "call_unsupported",
                "name": "cat",
                "arguments": "{\"path\":\"/workspace/file.txt\"}",
            },
            {"type": "function_call_output", "call_id": "call_supported", "output": "/workspace\n"},
        ]
    )

    assert len(messages) == 1
    assert messages[0]["role"] == "user"
    assert "Tool result for exec" in messages[0]["content"]
    assert "call_unsupported" not in messages[0]["content"]


def test_responses_input_to_chat_maps_developer_role_to_system() -> None:
    messages = router.responses_input_to_chat_messages(
        [
            {
                "type": "message",
                "role": "developer",
                "content": [{"type": "input_text", "text": "Follow harness instructions."}],
            },
            {
                "type": "message",
                "role": "user",
                "content": [{"type": "input_text", "text": "Do the task."}],
            },
        ]
    )

    assert messages == [
        {"role": "system", "content": "Follow harness instructions."},
        {"role": "user", "content": "Do the task."},
    ]


def test_responses_tools_drop_web_search_builtin_tools() -> None:
    converted = router.responses_tools_to_chat_tools(
        [
            {"type": "web_search"},
            {"type": "web_search_preview"},
            {
                "type": "function",
                "name": "lookup",
                "description": "Look up a value.",
                "parameters": {"type": "object", "properties": {}},
            },
        ]
    )

    assert len(converted) == 1
    assert converted[0]["function"]["name"] == "lookup"


def test_responses_request_drops_web_search_tool_choice() -> None:
    conversion = router.responses_request_to_chat(
        {
            "model": "glm-5.1",
            "input": "Return OK.",
            "tools": [{"type": "web_search"}],
            "tool_choice": {"type": "web_search"},
        }
    )

    assert "tools" not in conversion.payload
    assert "tool_choice" not in conversion.payload


def test_responses_tools_reject_unknown_unsupported_tool() -> None:
    try:
        router.responses_tools_to_chat_tools([{"type": "file_search"}])
    except router.RouterRequestError as exc:
        assert exc.status_code == 400
        assert "unsupported Responses tool type" in exc.message
    else:
        raise AssertionError("unsupported tool should fail")


def test_chat_stream_text_events_end_with_response_completed() -> None:
    events = list(
        router.chat_stream_to_response_events(
            [
                {"choices": [{"delta": {"content": "Hel"}}]},
                {"choices": [{"delta": {"content": "lo"}, "finish_reason": "stop"}]},
            ],
            response_id="resp_test",
            model="glm-5.1",
            created_at=123,
        )
    )

    event_names = [name for name, _ in events]
    assert event_names[:3] == [
        "response.created",
        "response.in_progress",
        "response.output_item.added",
    ]
    assert [payload["delta"] for name, payload in events if name == "response.output_text.delta"] == ["Hel", "lo"]
    assert event_names[-1] == "response.completed"
    assert events[-1][1]["response"]["output_text"] == "Hello"


def test_chat_stream_tool_call_events_are_ordered() -> None:
    events = list(
        router.chat_stream_to_response_events(
            [
                {
                    "choices": [
                        {
                            "delta": {
                                "tool_calls": [
                                    {
                                        "index": 0,
                                        "id": "call_abc",
                                        "type": "function",
                                        "function": {"name": "shell", "arguments": "{\"cmd\""},
                                    }
                                ]
                            }
                        }
                    ]
                },
                {
                    "choices": [
                        {
                            "delta": {
                                "tool_calls": [
                                    {
                                        "index": 0,
                                        "function": {"arguments": ":\"pwd\"}"},
                                    }
                                ]
                            },
                            "finish_reason": "tool_calls",
                        }
                    ]
                },
            ],
            response_id="resp_test",
            model="glm-5.1",
            created_at=123,
        )
    )

    event_names = [name for name, _ in events]
    added_index = event_names.index("response.output_item.added")
    first_delta_index = event_names.index("response.function_call_arguments.delta")
    done_index = event_names.index("response.function_call_arguments.done")
    item_done_index = event_names.index("response.output_item.done")
    assert added_index < first_delta_index < done_index < item_done_index
    assert events[done_index][1]["arguments"] == "{\"cmd\":\"pwd\"}"
    assert events[-1][0] == "response.completed"


def test_reasoning_content_is_cached_and_echoed_for_tool_followup() -> None:
    reasoning_by_call_id: dict[str, str] = {}
    list(
        router.chat_stream_to_response_events(
            [
                {
                    "choices": [
                        {
                            "delta": {
                                "reasoning_content": "Need to inspect. ",
                                "tool_calls": [
                                    {
                                        "index": 0,
                                        "id": "call_abc",
                                        "type": "function",
                                        "function": {"name": "shell", "arguments": "{\"cmd\":\"pwd\"}"},
                                    }
                                ],
                            },
                            "finish_reason": "tool_calls",
                        }
                    ]
                }
            ],
            response_id="resp_test",
            model="deepseek-v4-flash",
            created_at=123,
            reasoning_by_call_id=reasoning_by_call_id,
        )
    )

    assert reasoning_by_call_id == {"call_abc": "Need to inspect. "}
    messages = router.responses_input_to_chat_messages(
        [
            {
                "type": "function_call",
                "call_id": "call_abc",
                "name": "shell",
                "arguments": "{\"cmd\":\"pwd\"}",
            },
            {"type": "function_call_output", "call_id": "call_abc", "output": "/workspace\n"},
        ],
        reasoning_by_call_id=reasoning_by_call_id,
    )

    assert messages[0]["role"] == "user"
    assert "Tool result for shell" in messages[0]["content"]


class _FakeChatBackend(BaseHTTPRequestHandler):
    requests_seen: list[dict[str, Any]] = []

    def log_message(self, format: str, *args: Any) -> None:
        return

    def do_POST(self) -> None:
        length = int(self.headers.get("content-length") or "0")
        payload = json.loads(self.rfile.read(length).decode("utf-8"))
        self.__class__.requests_seen.append({"path": self.path, "payload": payload})
        body = json.dumps(
            {
                "id": "chatcmpl_test",
                "object": "chat.completion",
                "model": payload["model"],
                "choices": [{"index": 0, "message": {"role": "assistant", "content": "OK"}, "finish_reason": "stop"}],
            }
        ).encode("utf-8")
        self.send_response(200)
        self.send_header("content-type", "application/json")
        self.send_header("content-length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


class _StreamingChatBackend(BaseHTTPRequestHandler):
    requests_seen: list[dict[str, Any]] = []

    def log_message(self, format: str, *args: Any) -> None:
        return

    def do_POST(self) -> None:
        length = int(self.headers.get("content-length") or "0")
        payload = json.loads(self.rfile.read(length).decode("utf-8"))
        self.__class__.requests_seen.append({"path": self.path, "payload": payload})
        chunks = [
            {
                "id": "chatcmpl_stream",
                "object": "chat.completion.chunk",
                "model": payload["model"],
                "choices": [{"index": 0, "delta": {"role": "assistant", "content": "O"}}],
            },
            {
                "id": "chatcmpl_stream",
                "object": "chat.completion.chunk",
                "model": payload["model"],
                "choices": [{"index": 0, "delta": {"content": "K"}, "finish_reason": "stop"}],
            },
        ]
        body = b"".join(f"data: {json.dumps(chunk)}\n\n".encode("utf-8") for chunk in chunks)
        body += b"data: [DONE]\n\n"
        self.send_response(200)
        self.send_header("content-type", "text/event-stream")
        self.send_header("content-length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


def _start_server(server: ThreadingHTTPServer) -> threading.Thread:
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    return thread


def test_validator_probe_reaches_fake_chat_backend_through_router() -> None:
    _FakeChatBackend.requests_seen = []
    backend = ThreadingHTTPServer(("127.0.0.1", 0), _FakeChatBackend)
    _start_server(backend)
    backend_url = f"http://127.0.0.1:{backend.server_address[1]}/v1"

    config = router.RouterConfig(upstream_base_url=backend_url, api_key="secret-key", default_model="glm-5.1", timeout_seconds=5)
    responses_router = router.make_router_server("127.0.0.1", 0, config)
    _start_server(responses_router)
    router_url = f"http://127.0.0.1:{responses_router.server_address[1]}/v1"

    try:
        result = validator.run_endpoint_probe(
            validator.get_target_integration_metadata("codex"),
            {"base_url": router_url, "api_key": "secret-key", "model": "glm-5.1"},
            5,
        )
    finally:
        responses_router.shutdown()
        responses_router.server_close()
        backend.shutdown()
        backend.server_close()

    assert result["ok"] is True, result
    assert result["wire_api"] == "responses"
    assert _FakeChatBackend.requests_seen[0]["path"] == "/v1/chat/completions"
    assert _FakeChatBackend.requests_seen[0]["payload"]["messages"] == [{"role": "user", "content": "Return OK."}]


def test_streaming_responses_request_is_forwarded_as_chat_sse() -> None:
    _StreamingChatBackend.requests_seen = []
    backend = ThreadingHTTPServer(("127.0.0.1", 0), _StreamingChatBackend)
    _start_server(backend)
    backend_url = f"http://127.0.0.1:{backend.server_address[1]}/v1"

    config = router.RouterConfig(upstream_base_url=backend_url, api_key="secret-key", default_model="glm-5.1", timeout_seconds=5)
    responses_router = router.make_router_server("127.0.0.1", 0, config)
    _start_server(responses_router)
    router_url = f"http://127.0.0.1:{responses_router.server_address[1]}/v1/responses"

    try:
        payload = {"model": "glm-5.1", "input": "Return OK.", "stream": True}
        req = urlrequest.Request(
            router_url,
            data=json.dumps(payload).encode("utf-8"),
            headers={"content-type": "application/json"},
            method="POST",
        )
        opener = urlrequest.build_opener(urlrequest.ProxyHandler({}))
        with opener.open(req, timeout=5) as response:
            body = response.read().decode("utf-8")
            content_type = response.headers.get("content-type", "")
    finally:
        responses_router.shutdown()
        responses_router.server_close()
        backend.shutdown()
        backend.server_close()

    assert "text/event-stream" in content_type
    assert "event: response.output_text.delta" in body
    assert '"delta": "O"' in body
    assert '"delta": "K"' in body
    assert "event: response.completed" in body
    assert '"type": "response.completed"' in body
    assert _StreamingChatBackend.requests_seen[0]["path"] == "/v1/chat/completions"
    assert _StreamingChatBackend.requests_seen[0]["payload"]["stream"] is True

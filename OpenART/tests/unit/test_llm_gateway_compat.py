from __future__ import annotations

import http.client
import importlib.util
import json
import subprocess
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
HOOK_PATH = REPO_ROOT / "configs" / "target-hooks" / "llm-gateway-compat.py"


def _load_hook():
    spec = importlib.util.spec_from_file_location("llm_gateway_compat", HOOK_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_normalize_upstream_strips_v1_suffix() -> None:
    hook = _load_hook()

    assert hook._normalize_upstream("http://gateway:4000/v1/") == "http://gateway:4000"
    assert hook._normalize_upstream("http://gateway:4000") == "http://gateway:4000"


def test_should_inject_only_messages_and_responses_paths() -> None:
    hook = _load_hook()

    assert hook._should_inject("/v1/messages?beta=true")
    assert hook._should_inject("/v1/responses")
    assert hook._should_inject("/messages")
    assert not hook._should_inject("/v1/chat/completions")
    assert not hook._should_inject("/v1/models")


def test_inject_compat_flag_is_idempotent() -> None:
    hook = _load_hook()

    body = json.dumps({"model": "m", "input": "hello"}).encode()
    injected = json.loads(hook.inject_compat_flag(body))
    assert injected["use_chat_completions_api"] is True

    existing = json.dumps({"model": "m", "use_chat_completions_api": False}).encode()
    assert json.loads(hook.inject_compat_flag(existing))["use_chat_completions_api"] is False

    assert hook.inject_compat_flag(b"not json") == b"not json"


def test_rewrite_claude_settings_adds_proxy_and_permissions(tmp_path: Path) -> None:
    hook = _load_hook()
    settings_path = tmp_path / ".claude" / "settings.json"
    settings_path.parent.mkdir(parents=True, exist_ok=True)
    settings_path.write_text(
        json.dumps(
            {
                "env": {"KEEP_ME": "1"},
                "permissions": {"allow": ["Bash(owncloud.*)"], "deny": ["Bash", "Edit"]},
            }
        ),
        encoding="utf-8",
    )

    hook.rewrite_claude_settings(
        settings_path,
        "http://127.0.0.1:9000",
        ["Bash", "Read", "Write"],
    )

    config = json.loads(settings_path.read_text(encoding="utf-8"))
    assert config["env"]["KEEP_ME"] == "1"
    assert config["env"]["ANTHROPIC_BASE_URL"] == "http://127.0.0.1:9000"
    assert "127.0.0.1" in config["env"]["NO_PROXY"]
    assert config["permissionMode"] == "acceptEdits"
    assert config["bypassPermissions"] is True
    assert config["permissions"]["allow"] == ["Bash(owncloud.*)", "Bash", "Read", "Write"]
    assert config["permissions"]["deny"] == ["Edit"]


def test_rewrite_codex_config_points_provider_at_proxy(tmp_path: Path) -> None:
    hook = _load_hook()
    config_path = tmp_path / "config.toml"
    config_path.write_text(
        "\n".join(
            [
                'model = "DeepSeek-V4.1-Flash-1017"',
                'model_provider = "openart"',
                "model_supports_reasoning_summaries = true",
                'model_reasoning_effort = "low"',
                'model_reasoning_summary = "auto"',
                "",
                "[model_providers.openart]",
                'name = "OpenART"',
                'base_url = "http://gateway:4000/v1"',
                'env_key = "OPENAI_API_KEY"',
                'wire_api = "responses"',
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    assert hook.rewrite_codex_config(config_path, "http://127.0.0.1:9000/v1") is True

    text = config_path.read_text(encoding="utf-8")
    assert 'base_url = "http://127.0.0.1:9000/v1"' in text
    assert "model_supports_reasoning_summaries" not in text
    assert "model_reasoning_summary" not in text
    assert 'model_reasoning_effort = "low"' in text
    assert 'wire_api = "responses"' in text


def test_rewrite_codex_config_requires_provider_base_url(tmp_path: Path) -> None:
    hook = _load_hook()
    config_path = tmp_path / "config.toml"
    config_path.write_text('model = "m"\n', encoding="utf-8")

    assert hook.rewrite_codex_config(config_path, "http://127.0.0.1:9000/v1") is False


def test_rewrite_codex_config_ignores_base_url_env_keys(tmp_path: Path) -> None:
    hook = _load_hook()
    config_path = tmp_path / "config.toml"
    config_path.write_text(
        "\n".join(
            [
                "[model_providers.openart]",
                'base_url_env = "CUSTOM_BASE_URL"',
                'base_url = "http://gateway:4000/v1"',
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    assert hook.rewrite_codex_config(config_path, "http://127.0.0.1:9000/v1") is True

    text = config_path.read_text(encoding="utf-8")
    assert 'base_url_env = "CUSTOM_BASE_URL"' in text
    assert 'base_url = "http://127.0.0.1:9000/v1"' in text


def test_state_dir_prefers_runner_state(monkeypatch, tmp_path: Path) -> None:
    hook = _load_hook()
    monkeypatch.delenv("OPENART_LLM_GATEWAY_COMPAT_DIR", raising=False)
    monkeypatch.setenv("OPENART_RUNNER_STATE_DIR", str(tmp_path / "state"))

    assert hook._state_dir() == tmp_path / "state" / "llm-gateway-compat"


def test_state_dir_honors_explicit_override(monkeypatch, tmp_path: Path) -> None:
    hook = _load_hook()
    monkeypatch.setenv("OPENART_LLM_GATEWAY_COMPAT_DIR", str(tmp_path / "explicit"))
    monkeypatch.setenv("OPENART_RUNNER_STATE_DIR", str(tmp_path / "state"))

    assert hook._state_dir() == tmp_path / "explicit"


class _UpstreamHandler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"
    requests: list[dict] = []

    def log_message(self, *args):  # noqa: A003 - silence default logging
        return

    def do_POST(self):  # noqa: N802
        length = int(self.headers.get("content-length") or 0)
        body = self.rfile.read(length)
        try:
            parsed = json.loads(body)
        except Exception:
            parsed = None
        type(self).requests.append({"path": self.path, "body": parsed})
        payload = b"event: message_stop\ndata: {}\n\n"
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)


def _read_port(port_file: Path, timeout: float = 10.0) -> int:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            return int(port_file.read_text(encoding="utf-8").strip())
        except Exception:
            time.sleep(0.05)
    raise AssertionError("proxy port file was not written")


def test_proxy_injects_flag_and_streams_response(tmp_path: Path) -> None:
    _UpstreamHandler.requests = []
    upstream = ThreadingHTTPServer(("127.0.0.1", 0), _UpstreamHandler)
    upstream_thread = threading.Thread(target=upstream.serve_forever, daemon=True)
    upstream_thread.start()

    port_file = tmp_path / "proxy.port"
    proxy = subprocess.Popen(
        [
            sys.executable,
            str(HOOK_PATH),
            "--serve",
            "--upstream",
            f"http://127.0.0.1:{upstream.server_address[1]}/v1",
            "--port-file",
            str(port_file),
        ],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    try:
        proxy_port = _read_port(port_file)
        conn = http.client.HTTPConnection("127.0.0.1", proxy_port, timeout=10)
        body = json.dumps(
            {
                "model": "m",
                "input": [
                    {"type": "function_call", "call_id": "call_1", "name": "shell", "arguments": "{}"},
                    {"type": "function_call_output", "call_id": "call_1", "output": "hi"},
                ],
                "stream": True,
            }
        )
        conn.request(
            "POST",
            "/v1/responses",
            body=body,
            headers={"Content-Type": "application/json"},
        )
        response = conn.getresponse()
        response_body = response.read()
        conn.close()

        assert response.status == 200
        assert b"message_stop" in response_body
        assert _UpstreamHandler.requests[-1]["path"] == "/v1/responses"
        assert _UpstreamHandler.requests[-1]["body"]["use_chat_completions_api"] is True
    finally:
        proxy.terminate()
        proxy.wait(timeout=5)
        upstream.shutdown()
        upstream.server_close()
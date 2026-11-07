#!/usr/bin/env python3
"""Client-side compatibility shim for LiteLLM gateways.

The gateway used by the benchmark rejects tool-result payloads on its
Anthropic Messages and OpenAI Responses conversion bridges.  LiteLLM accepts
the same request when it is told to use its chat-completions path via the
``use_chat_completions_api`` body flag.  Harnesses do not expose that flag, so
this hook starts a loopback proxy that injects it and points the harness at the
proxy.

It also applies the Claude Code permission baseline that used to live in
``claude-code-enforce-settings.sh`` and strips Codex reasoning-summary options
that the gateway cannot deserialize.

The hook is intentionally client-side: the upstream gateway and its lifecycle
remain owned by the caller.  Proxy logs are written under
``$OPENART_RUNNER_STATE_DIR/llm-gateway-compat`` when that directory is set, so
they travel with the run artifacts.
"""

from __future__ import annotations

import argparse
import http.client
import json
import os
import re
import socket
import subprocess
import sys
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlsplit

INJECT_SUFFIXES = ("/v1/messages", "/v1/responses", "/messages", "/responses")
HOP_HEADERS = {
    "connection",
    "content-length",
    "host",
    "keep-alive",
    "proxy-authenticate",
    "proxy-authorization",
    "te",
    "trailer",
    "transfer-encoding",
    "upgrade",
}
DEFAULT_CLAUDE_ALLOW = ("Bash", "Read", "Write")
REASONING_SUMMARY_KEYS = (
    "model_supports_reasoning_summaries",
    "model_reasoning_summary",
)
STARTUP_TIMEOUT_SECONDS = 15.0


def _state_dir() -> Path:
    raw = str(os.environ.get("OPENART_LLM_GATEWAY_COMPAT_DIR", "") or "").strip()
    if raw:
        base = Path(raw)
    else:
        runner_state = str(os.environ.get("OPENART_RUNNER_STATE_DIR", "") or "").strip()
        base = (
            Path(runner_state) / "llm-gateway-compat"
            if runner_state
            else Path("/tmp/openart/llm-gateway-compat")
        )
    base.mkdir(parents=True, exist_ok=True)
    return base


def _home() -> Path:
    return Path(os.environ.get("HOME") or "/tmp/openart/runners/target/home")


def _normalize_upstream(value: str) -> str:
    text = str(value or "").strip().rstrip("/")
    if text.endswith("/v1"):
        text = text[: -len("/v1")].rstrip("/")
    return text


def _claude_allowed_rules() -> list[str]:
    raw = os.environ.get("OPENART_CLAUDE_AUTO_APPROVAL_ALLOW", "")
    rules = [item.strip() for item in raw.split(",") if item.strip()]
    return rules or list(DEFAULT_CLAUDE_ALLOW)


def rewrite_claude_settings(
    settings_path: Path,
    proxy_base_url: str,
    allowed_rules: list[str],
) -> None:
    settings_path.parent.mkdir(parents=True, exist_ok=True)
    try:
        raw = settings_path.read_text(encoding="utf-8")
        config = json.loads(raw) if raw.strip() else {}
    except Exception:
        config = {}
    if not isinstance(config, dict):
        config = {}

    permissions = config.get("permissions") if isinstance(config.get("permissions"), dict) else {}
    current_allow = permissions.get("allow") if isinstance(permissions.get("allow"), list) else []
    allow = [str(item) for item in current_allow if str(item).strip()]
    for rule in allowed_rules:
        if rule not in allow:
            allow.append(rule)

    def denies_baseline(rule: str) -> bool:
        return any(rule == allowed or rule.startswith(f"{allowed}(") for allowed in allowed_rules)

    current_deny = permissions.get("deny") if isinstance(permissions.get("deny"), list) else []
    deny = [
        str(item)
        for item in current_deny
        if str(item).strip() and not denies_baseline(str(item))
    ]

    permissions["allow"] = allow
    permissions["deny"] = deny
    config["permissions"] = permissions
    config["permissionMode"] = "acceptEdits"
    config["bypassPermissions"] = True

    env = config.get("env") if isinstance(config.get("env"), dict) else {}
    env["ANTHROPIC_BASE_URL"] = proxy_base_url
    no_proxy = str(
        env.get("NO_PROXY")
        or env.get("no_proxy")
        or os.environ.get("NO_PROXY")
        or os.environ.get("no_proxy")
        or ""
    )
    no_proxy_entries = [item.strip() for item in no_proxy.split(",") if item.strip()]
    for loopback in ("127.0.0.1", "localhost", "::1"):
        if loopback not in no_proxy_entries:
            no_proxy_entries.append(loopback)
    env["NO_PROXY"] = ",".join(no_proxy_entries)
    config["env"] = env

    settings_path.write_text(
        json.dumps(config, ensure_ascii=True, indent=2) + "\n",
        encoding="utf-8",
    )


def rewrite_codex_config(config_path: Path, proxy_base_url: str) -> bool:
    try:
        text = config_path.read_text(encoding="utf-8")
    except FileNotFoundError:
        return False

    output: list[str] = []
    section = ""
    replaced = False
    for line in text.splitlines():
        stripped = line.strip()
        if stripped.startswith("[") and stripped.endswith("]"):
            section = stripped[1:-1].strip()
        if re.match(r"base_url\s*=", stripped) and section.startswith("model_providers."):
            if not replaced:
                indent = line[: len(line) - len(line.lstrip())]
                output.append(f'{indent}base_url = "{proxy_base_url}"')
                replaced = True
            continue
        if any(
            re.match(rf"{key}\s*=", stripped)
            for key in REASONING_SUMMARY_KEYS
        ):
            continue
        output.append(line)

    if not replaced:
        return False

    config_path.write_text("\n".join(output).rstrip() + "\n", encoding="utf-8")
    return True


def inject_compat_flag(body: bytes) -> bytes:
    try:
        payload = json.loads(body)
    except Exception:
        return body
    if not isinstance(payload, dict) or "use_chat_completions_api" in payload:
        return body
    payload["use_chat_completions_api"] = True
    return json.dumps(payload).encode("utf-8")


def _should_inject(path: str) -> bool:
    request_path = urlsplit(path).path.rstrip("/")
    return any(request_path.endswith(suffix) for suffix in INJECT_SUFFIXES)


class CompatProxyHandler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"
    upstream = ""

    def log_message(self, *args):  # noqa: A003 - silence default logging
        return

    def _forward(self, method: str, body: bytes | None) -> None:
        parts = urlsplit(self.upstream)
        if not parts.hostname:
            self._send_error(500, "compat proxy upstream is not configured")
            return
        base_path = parts.path.rstrip("/")
        target = f"{base_path}{self.path}" or "/"
        headers = {
            key: value
            for key, value in self.headers.items()
            if key.lower() not in HOP_HEADERS
        }
        if body is not None:
            headers["Content-Length"] = str(len(body))

        conn = http.client.HTTPConnection(
            parts.hostname,
            parts.port or 80,
            timeout=600,
        )
        headers_sent = False
        try:
            conn.request(method, target, body=body, headers=headers)
            response = conn.getresponse()
            print(
                f"{method} {self.path} body={len(body) if body else 0} -> {response.status}",
                flush=True,
            )
            self.send_response_only(response.status)
            for key, value in response.getheaders():
                if key.lower() in HOP_HEADERS:
                    continue
                self.send_header(key, value)
            if method == "HEAD" or response.status in (204, 304):
                self.send_header("Content-Length", "0")
                self.end_headers()
                headers_sent = True
                return
            self.send_header("Transfer-Encoding", "chunked")
            self.end_headers()
            headers_sent = True
            self.wfile.flush()
            while True:
                chunk = response.read(4096)
                if not chunk:
                    break
                self.wfile.write(f"{len(chunk):X}\r\n".encode("ascii") + chunk + b"\r\n")
                self.wfile.flush()
            self.wfile.write(b"0\r\n\r\n")
            self.wfile.flush()
        except (BrokenPipeError, ConnectionResetError):
            return
        except Exception as exc:  # noqa: BLE001
            print(f"{method} {self.path} -> error: {exc}", flush=True)
            if headers_sent:
                self.close_connection = True
                return
            try:
                self._send_error(502, f"compat proxy upstream error: {exc}")
            except (BrokenPipeError, ConnectionResetError):
                pass
        finally:
            conn.close()

    def _send_error(self, status: int, message: str) -> None:
        payload = json.dumps({"error": message}).encode("utf-8")
        self.send_response_only(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)
        self.wfile.flush()

    def do_POST(self):  # noqa: N802
        length = int(self.headers.get("content-length") or 0)
        body = self.rfile.read(length) if length else b""
        if _should_inject(self.path):
            body = inject_compat_flag(body)
        self._forward("POST", body)

    def do_GET(self):  # noqa: N802
        self._forward("GET", None)

    def do_HEAD(self):  # noqa: N802
        self._forward("HEAD", None)


def serve(upstream: str, port_file: Path, port: int = 0) -> None:
    CompatProxyHandler.upstream = _normalize_upstream(upstream)
    server = ThreadingHTTPServer(("127.0.0.1", port), CompatProxyHandler)
    server.daemon_threads = True
    temporary = port_file.with_suffix(port_file.suffix + ".tmp")
    temporary.write_text(f"{server.server_address[1]}\n", encoding="utf-8")
    temporary.replace(port_file)
    server.serve_forever()


def _harness() -> str:
    explicit = str(os.environ.get("OPENART_LLM_GATEWAY_COMPAT", "") or "").strip().lower()
    aliases = {
        "claude": "claude_code",
        "claude-code": "claude_code",
        "claude_code": "claude_code",
        "codex": "codex",
    }
    if explicit in aliases:
        return aliases[explicit]

    home = _home()
    if (home / ".codex" / "config.toml").is_file():
        return "codex"
    if (home / ".claude" / "settings.json").is_file() or os.environ.get("ANTHROPIC_BASE_URL"):
        return "claude_code"
    if os.environ.get("OPENAI_BASE_URL"):
        return "codex"
    return ""


def _claude_upstream(home: Path) -> str:
    upstream = os.environ.get("ANTHROPIC_BASE_URL", "")
    if upstream:
        return upstream
    settings_path = home / ".claude" / "settings.json"
    try:
        config = json.loads(settings_path.read_text(encoding="utf-8"))
    except Exception:
        return ""
    env = config.get("env") if isinstance(config.get("env"), dict) else {}
    return str(env.get("ANTHROPIC_BASE_URL") or "")


def _codex_upstream(home: Path) -> str:
    upstream = os.environ.get("OPENAI_BASE_URL", "")
    if upstream:
        return upstream
    config_path = home / ".codex" / "config.toml"
    try:
        text = config_path.read_text(encoding="utf-8")
    except FileNotFoundError:
        return ""
    section = ""
    for line in text.splitlines():
        stripped = line.strip()
        if stripped.startswith("[") and stripped.endswith("]"):
            section = stripped[1:-1].strip()
            continue
        if section.startswith("model_providers.") and re.match(r"base_url\s*=", stripped):
            value = stripped.split("=", 1)[1].strip().strip('"').strip("'")
            if value:
                return value
    return ""


def _wait_for_proxy(port_file: Path, timeout: float) -> int:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            port = int(port_file.read_text(encoding="utf-8").strip())
        except Exception:
            time.sleep(0.05)
            continue
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
            probe.settimeout(0.5)
            if probe.connect_ex(("127.0.0.1", port)) == 0:
                return port
        time.sleep(0.05)
    raise RuntimeError(f"compat proxy did not become ready within {timeout:g}s")


def _start_proxy(upstream: str) -> int:
    state_dir = _state_dir()
    port_file = state_dir / "proxy.port"
    log_path = state_dir / "proxy.log"
    try:
        port_file.unlink()
    except FileNotFoundError:
        pass

    with log_path.open("ab") as log_handle:
        subprocess.Popen(
            [
                sys.executable,
                str(Path(__file__).resolve()),
                "--serve",
                "--upstream",
                upstream,
                "--port-file",
                str(port_file),
            ],
            stdin=subprocess.DEVNULL,
            stdout=log_handle,
            stderr=subprocess.STDOUT,
            start_new_session=True,
            close_fds=True,
        )
    return _wait_for_proxy(port_file, STARTUP_TIMEOUT_SECONDS)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--serve", action="store_true")
    parser.add_argument("--upstream", default="")
    parser.add_argument("--port", type=int, default=0)
    parser.add_argument("--port-file", type=Path, default=None)
    args = parser.parse_args(argv)

    if args.serve:
        if not args.upstream or args.port_file is None:
            parser.error("--serve requires --upstream and --port-file")
        serve(args.upstream, args.port_file, args.port)
        return 0

    harness = _harness()
    if not harness:
        return 0

    home = _home()
    if harness == "claude_code":
        upstream = _claude_upstream(home)
    else:
        upstream = _codex_upstream(home)

    upstream = _normalize_upstream(upstream)
    if not upstream:
        print(
            f"openart llm-gateway-compat: no upstream found for {harness}",
            file=sys.stderr,
        )
        return 1

    parts = urlsplit(upstream)
    if parts.hostname in {"127.0.0.1", "localhost", "::1"}:
        # Already routed through a compatibility proxy; do not recurse.
        return 0

    try:
        port = _start_proxy(upstream)
    except Exception as exc:  # noqa: BLE001
        print(f"openart llm-gateway-compat: {exc}", file=sys.stderr)
        return 1

    proxy_base_url = f"http://127.0.0.1:{port}"
    if harness == "claude_code":
        rewrite_claude_settings(
            home / ".claude" / "settings.json",
            proxy_base_url,
            _claude_allowed_rules(),
        )
    else:
        rewritten = rewrite_codex_config(
            home / ".codex" / "config.toml",
            f"{proxy_base_url}/v1",
        )
        if not rewritten:
            print(
                "openart llm-gateway-compat: codex config has no model provider base_url",
                file=sys.stderr,
            )
            return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
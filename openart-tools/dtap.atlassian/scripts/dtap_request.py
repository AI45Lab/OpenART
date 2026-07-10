#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import socket
import sys
from typing import Any
from urllib import error, request
from urllib.parse import urlparse


BODY_PREVIEW_BYTES = 4096
BIGQUERY_DEFAULT_PORTS = {"api": 25900, "grpc": 25901}


def infer_service() -> str:
    explicit = os.environ.get("DTAP_SERVICE", "").strip()
    if explicit:
        return explicit
    for parent in Path(__file__).resolve().parents:
        if parent.name.startswith("dtap."):
            return parent.name.split(".", 1)[1]
    return ""


def env_prefix(service: str) -> str:
    return service.upper().replace("-", "_").replace(".", "_")


def print_json(payload: dict[str, Any]) -> None:
    print(json.dumps(payload, ensure_ascii=True, indent=2, sort_keys=True))


def preview_body(body: bytes) -> str:
    if not body:
        return ""
    preview = body[:BODY_PREVIEW_BYTES].decode("utf-8", errors="replace")
    if len(body) > BODY_PREVIEW_BYTES:
        preview += f"\n...<truncated {len(body) - BODY_PREVIEW_BYTES} bytes>"
    return preview


def read_arg_value(value: str) -> bytes:
    text = str(value or "")
    if text.startswith("@"):
        return Path(text[1:]).read_bytes()
    return text.encode("utf-8")


def parse_json_body(value: str) -> bytes:
    raw = read_arg_value(value)
    parsed = json.loads(raw.decode("utf-8"))
    return json.dumps(parsed, ensure_ascii=True, separators=(",", ":")).encode("utf-8")


def parse_headers(values: list[str]) -> dict[str, str]:
    headers: dict[str, str] = {}
    for value in values:
        if ":" in value:
            key, header_value = value.split(":", 1)
        elif "=" in value:
            key, header_value = value.split("=", 1)
        else:
            raise ValueError(f"invalid header {value!r}; use 'Name: value' or 'Name=value'")
        key = key.strip()
        if not key:
            raise ValueError(f"invalid header {value!r}; header name is empty")
        headers[key] = header_value.strip()
    return headers


def join_url(base_url: str, path: str) -> str:
    text = str(path or "/").strip() or "/"
    if text.startswith(("http://", "https://")):
        return text
    if not text.startswith("/"):
        text = "/" + text
    return base_url.rstrip("/") + text


def request_without_proxy(
    *,
    service: str,
    method: str,
    url: str,
    headers: dict[str, str],
    body: bytes | None,
    timeout: float,
    allow_http_error: bool,
) -> tuple[int, dict[str, Any]]:
    opener = request.build_opener(request.ProxyHandler({}))
    req = request.Request(url, data=body, method=method.upper(), headers=headers)
    result: dict[str, Any] = {
        "service": service,
        "method": method.upper(),
        "url": url,
    }
    try:
        with opener.open(req, timeout=timeout) as response:
            response_body = response.read()
            status = int(response.getcode())
            result.update(
                {
                    "ok": 200 <= status < 400,
                    "status": status,
                    "body_bytes": len(response_body),
                    "body_preview": preview_body(response_body),
                }
            )
            return (0 if result["ok"] or allow_http_error else 1), result
    except error.HTTPError as exc:
        response_body = exc.read()
        status = int(exc.code)
        result.update(
            {
                "ok": allow_http_error,
                "status": status,
                "body_bytes": len(response_body),
                "body_preview": preview_body(response_body),
                "error": {
                    "type": "HTTPError",
                    "message": str(exc),
                },
            }
        )
        return (0 if allow_http_error else 1), result
    except Exception as exc:
        result.update(
            {
                "ok": False,
                "status": None,
                "body_bytes": 0,
                "body_preview": "",
                "error": {
                    "type": type(exc).__name__,
                    "message": str(exc),
                },
            }
        )
        return 1, result


def split_host_port(addr: str, fallback_port: int | None = None) -> tuple[str, int | None]:
    text = str(addr or "").strip()
    if not text:
        return "", fallback_port
    if text.startswith(("http://", "https://")):
        parsed = urlparse(text)
        return parsed.hostname or "", parsed.port or fallback_port
    if ":" in text:
        host, raw_port = text.rsplit(":", 1)
        try:
            return host.strip(), int(raw_port)
        except ValueError:
            return host.strip(), fallback_port
    return text, fallback_port


def tcp_check(host: str, port: int, timeout: float) -> dict[str, Any]:
    result: dict[str, Any] = {"host": host, "port": port}
    try:
        with socket.create_connection((host, port), timeout=timeout):
            result["ok"] = True
    except Exception as exc:
        result["ok"] = False
        result["error"] = {
            "type": type(exc).__name__,
            "message": str(exc),
        }
    return result


def bigquery_health(service: str, prefix: str, timeout: float) -> tuple[int, dict[str, Any]]:
    checks: list[dict[str, Any]] = []
    fallback_host = os.environ.get("DTAP_HOST", "").strip()
    for role, default_port in BIGQUERY_DEFAULT_PORTS.items():
        role_prefix = f"DTAP_{prefix}_{role.upper()}"
        raw_addr = os.environ.get(f"{role_prefix}_ADDR", "").strip()
        raw_url = os.environ.get(f"{role_prefix}_URL", "").strip()
        raw_port = os.environ.get(f"{role_prefix}_PORT", "").strip()
        port = int(raw_port) if raw_port.isdigit() else default_port
        host, parsed_port = split_host_port(raw_addr or raw_url, port)
        host = host or fallback_host
        port = int(parsed_port or port)
        item = tcp_check(host, port, timeout)
        item["role"] = role
        checks.append(item)
    ok = all(bool(item.get("ok")) for item in checks)
    return (
        0 if ok else 1,
        {
            "service": service,
            "health": True,
            "kind": "tcp",
            "ok": ok,
            "status": "ok" if ok else "failed",
            "checks": checks,
        },
    )


def health_check(service: str, prefix: str, timeout: float) -> tuple[int, dict[str, Any]]:
    if prefix == "BIGQUERY":
        return bigquery_health(service, prefix, timeout)
    key = f"DTAP_{prefix}_HEALTH_URL"
    url = os.environ.get(key, "").strip()
    if not url:
        return (
            1,
            {
                "service": service,
                "health": True,
                "ok": False,
                "status": None,
                "error": {
                    "type": "missing_env",
                    "message": f"{key} is not set",
                    "required": [key],
                },
            },
        )
    return request_without_proxy(
        service=service,
        method="GET",
        url=url,
        headers={},
        body=None,
        timeout=timeout,
        allow_http_error=False,
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Generic no-proxy request wrapper for a DTAP service.")
    parser.add_argument("--health", action="store_true", help="Check the service health endpoint.")
    parser.add_argument("--method", default="GET", help="HTTP method for generic requests. Default: GET.")
    parser.add_argument("--path", default="/", help="Request path relative to the service main URL. Default: /.")
    parser.add_argument("--json", dest="json_body", help="JSON request body string, or @file.")
    parser.add_argument("--data", help="Raw request body string, or @file.")
    parser.add_argument(
        "--header",
        action="append",
        default=[],
        help="HTTP header, repeatable. Use 'Name: value' or 'Name=value'.",
    )
    parser.add_argument("--timeout", type=float, default=10.0, help="Network timeout in seconds. Default: 10.")
    parser.add_argument("--allow-http-error", action="store_true", help="Exit 0 for HTTP 4xx/5xx responses.")
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    service = infer_service()
    prefix = env_prefix(service)
    if not service or not prefix:
        print_json(
            {
                "service": service,
                "ok": False,
                "error": {
                    "type": "service_inference_error",
                    "message": "Could not infer service from DTAP_SERVICE or tool folder path.",
                },
            }
        )
        return 1
    if args.json_body is not None and args.data is not None:
        parser.error("--json and --data are mutually exclusive")

    if args.health:
        code, payload = health_check(service, prefix, args.timeout)
        print_json(payload)
        return code

    key = f"DTAP_{prefix}_URL"
    base_url = os.environ.get(key, "").strip()
    if not base_url:
        print_json(
            {
                "service": service,
                "ok": False,
                "status": None,
                "error": {
                    "type": "missing_env",
                    "message": f"{key} is not set",
                    "required": [key],
                },
            }
        )
        return 1

    try:
        headers = parse_headers(args.header)
        body = None
        if args.json_body is not None:
            body = parse_json_body(args.json_body)
            headers.setdefault("Content-Type", "application/json")
        elif args.data is not None:
            body = read_arg_value(args.data)
    except Exception as exc:
        print_json(
            {
                "service": service,
                "ok": False,
                "status": None,
                "error": {
                    "type": type(exc).__name__,
                    "message": str(exc),
                },
            }
        )
        return 1

    code, payload = request_without_proxy(
        service=service,
        method=args.method,
        url=join_url(base_url, args.path),
        headers=headers,
        body=body,
        timeout=args.timeout,
        allow_http_error=bool(args.allow_http_error),
    )
    print_json(payload)
    return code


if __name__ == "__main__":
    raise SystemExit(main())

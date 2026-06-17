#!/usr/bin/env python3
from __future__ import annotations

import argparse
from dataclasses import dataclass
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
import html
import json
import os
from pathlib import Path
import sys
import tempfile
import time
from typing import Any, Callable
from urllib import error, parse, request

import yaml

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from framework.core.target_adapters import (  # noqa: E402
    canonical_surface_family,
    resolve_model_binding,
    stage_model_integration,
    surface_family_from_target_config,
)


@dataclass(frozen=True)
class FetchResult:
    url: str
    status_code: int
    text: str
    headers: dict[str, str]


@dataclass(frozen=True)
class TargetIntegrationMetadata:
    surface_family: str
    docs_url: str
    official_domains: tuple[str, ...]
    required_doc_keywords: tuple[str, ...]
    required_model_fields: tuple[str, ...] = ("api_key", "base_url", "model")
    endpoint_probe: dict[str, Any] | None = None


TARGET_INTEGRATION_METADATA: dict[str, TargetIntegrationMetadata] = {
    "claude_code": TargetIntegrationMetadata(
        surface_family="claude_code",
        docs_url="https://code.claude.com/docs/en/env-vars",
        official_domains=("code.claude.com", "docs.anthropic.com"),
        required_doc_keywords=(
            "ANTHROPIC_API_KEY",
            "ANTHROPIC_AUTH_TOKEN",
            "ANTHROPIC_BASE_URL",
            "ANTHROPIC_MODEL",
        ),
        endpoint_probe={"family": "anthropic_messages", "path": "/v1/messages"},
    ),
    "opencode": TargetIntegrationMetadata(
        surface_family="opencode",
        docs_url="https://opencode.ai/docs/providers",
        official_domains=("opencode.ai", "open-code.ai", "dev.opencode.ai"),
        required_doc_keywords=(
            "opencode.json",
            "options",
            "baseURL",
            "apiKey",
            "@ai-sdk/openai-compatible",
        ),
        endpoint_probe={"family": "openai_compatible", "wire_api": "chat"},
    ),
    "codex": TargetIntegrationMetadata(
        surface_family="codex",
        docs_url="https://developers.openai.com/codex/config-reference",
        official_domains=("developers.openai.com", "github.com"),
        required_doc_keywords=(
            "model_providers.<id>.base_url",
            "env_key",
            "wire_api",
            "responses",
        ),
        endpoint_probe={"family": "openai_compatible", "wire_api": "responses"},
    ),
    "pi": TargetIntegrationMetadata(
        surface_family="pi",
        docs_url="https://pi.dev/docs/latest/models",
        official_domains=("pi.dev",),
        required_doc_keywords=(
            "~/.pi/agent/models.json",
            "baseUrl",
            "api",
            "apiKey",
        ),
        endpoint_probe={"family": "openai_compatible", "wire_api": "chat"},
    ),
    "gemini": TargetIntegrationMetadata(
        surface_family="gemini",
        docs_url="https://google-gemini.github.io/gemini-cli/docs/get-started/configuration.html",
        official_domains=("google-gemini.github.io", "github.com"),
        required_doc_keywords=(
            "GEMINI_API_KEY",
            "GEMINI_MODEL",
            "settings.json",
            "--model",
            "--prompt",
        ),
        required_model_fields=("api_key", "model"),
        endpoint_probe=None,
    ),
    "hermes": TargetIntegrationMetadata(
        surface_family="hermes",
        docs_url="https://hermes-agent.lzw.me/docs/en/user-guide/configuration",
        official_domains=("hermes-agent.nousresearch.com", "hermes-agent.lzw.me"),
        required_doc_keywords=(
            "base_url",
            "api_key",
            "OPENAI_API_KEY",
            "config.yaml",
        ),
        endpoint_probe={"family": "openai_compatible", "wire_api": "chat"},
    ),
    "nanobot": TargetIntegrationMetadata(
        surface_family="nanobot",
        docs_url="https://raw.githubusercontent.com/HKUDS/nanobot/main/docs/configuration.md",
        official_domains=("nanobot.wiki", "github.com", "raw.githubusercontent.com"),
        required_doc_keywords=(
            "providers",
            "apiKey",
            "apiBase",
            "agents",
            "defaults",
        ),
        endpoint_probe={"family": "openai_compatible", "wire_api": "chat"},
    ),
    "cursor": TargetIntegrationMetadata(
        surface_family="cursor",
        docs_url="https://cursor.com/docs/cli/reference/parameters",
        official_domains=("docs.cursor.com", "cursor.com"),
        required_doc_keywords=(
            "CURSOR_API_KEY",
            "--api-key",
            "--model",
            "--print",
        ),
        required_model_fields=("api_key", "model"),
        endpoint_probe=None,
    ),
}


def get_target_integration_metadata(surface_family: str) -> TargetIntegrationMetadata | None:
    return TARGET_INTEGRATION_METADATA.get(canonical_surface_family(surface_family))


FetchDocsFn = Callable[[str, int], FetchResult]
EndpointProbeFn = Callable[[TargetIntegrationMetadata, dict[str, str], int], dict[str, Any]]
SmokeFn = Callable[[dict[str, Any], str, Path, str], dict[str, Any]]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Validate OpenART target model integration against live docs and model endpoint.")
    parser.add_argument("--target-config", required=True, help="Target config yaml/json path")
    parser.add_argument("--surface-family", default="", help="Target native surface-family override")
    parser.add_argument("--docs-url", default="", help="Docs URL override")
    parser.add_argument("--require-official-docs", action="store_true", help="Fail if the docs URL is not official for this target")
    parser.add_argument("--output", default="target_model_integration_validation.json", help="Validation artifact path")
    parser.add_argument("--max-doc-age-days", type=int, default=365, help="Fail docs with a Last-Modified older than this many days; <=0 disables age checks")
    parser.add_argument("--timeout-seconds", type=int, default=30, help="HTTP timeout for docs and endpoint probes")
    return parser.parse_args()


def load_mapping_file(path: str | Path) -> dict[str, Any]:
    target = Path(path)
    text = target.read_text(encoding="utf-8")
    if target.suffix.lower() == ".json":
        loaded = json.loads(text)
    else:
        loaded = yaml.safe_load(text)
    return loaded if isinstance(loaded, dict) else {}


def load_target_config(path: str | Path) -> dict[str, Any]:
    data = load_mapping_file(path)
    scoped = data.get("target")
    if isinstance(scoped, dict):
        return dict(scoped)
    return data if isinstance(data, dict) else {}


def fetch_docs_url(url: str, timeout_seconds: int) -> FetchResult:
    req = request.Request(
        url,
        headers={
            "User-Agent": "OpenART target model integration validator/1.0",
            "Accept": "text/html,text/plain,application/json,*/*",
        },
    )
    with request.urlopen(req, timeout=timeout_seconds) as response:
        raw = response.read(2_000_000)
        charset = response.headers.get_content_charset() or "utf-8"
        return FetchResult(
            url=response.geturl(),
            status_code=int(getattr(response, "status", 200) or 200),
            text=raw.decode(charset, errors="replace"),
            headers={str(k): str(v) for k, v in response.headers.items()},
        )


def _host_matches(url: str, official_domains: tuple[str, ...]) -> bool:
    host = parse.urlparse(url).hostname or ""
    host = host.lower()
    for domain in official_domains:
        candidate = domain.lower().lstrip(".")
        if host == candidate or host.endswith("." + candidate):
            return True
    return False


def _last_modified(headers: dict[str, str]) -> datetime | None:
    raw = headers.get("Last-Modified") or headers.get("last-modified") or ""
    if not raw:
        return None
    try:
        parsed = parsedate_to_datetime(raw)
    except Exception:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def validate_docs_evidence(
    fetch_result: FetchResult,
    metadata: TargetIntegrationMetadata,
    *,
    docs_url: str,
    require_official_docs: bool,
    max_doc_age_days: int,
) -> dict[str, Any]:
    text = html.unescape(fetch_result.text)
    matched = [keyword for keyword in metadata.required_doc_keywords if keyword in text]
    missing = [keyword for keyword in metadata.required_doc_keywords if keyword not in text]
    official = _host_matches(fetch_result.url or docs_url, metadata.official_domains)
    modified = _last_modified(fetch_result.headers)
    stale = False
    age_days: int | None = None
    if modified is not None and max_doc_age_days > 0:
        age_days = int((datetime.now(timezone.utc) - modified).total_seconds() // 86400)
        stale = age_days > max_doc_age_days

    ok = 200 <= int(fetch_result.status_code or 0) < 400 and not missing and not stale
    if require_official_docs and not official:
        ok = False

    return {
        "ok": ok,
        "url": fetch_result.url or docs_url,
        "status_code": fetch_result.status_code,
        "official": official,
        "required_official": bool(require_official_docs),
        "matched_fields": matched,
        "missing_fields": missing,
        "last_modified": modified.isoformat() if modified is not None else "",
        "age_days": age_days,
        "stale": stale,
    }


def _join_url(base_url: str, path: str) -> str:
    return base_url.rstrip("/") + "/" + path.lstrip("/")


def _post_json(url: str, payload: dict[str, Any], headers: dict[str, str], timeout_seconds: int) -> tuple[int, str, str]:
    body = json.dumps(payload).encode("utf-8")
    req = request.Request(url, data=body, method="POST", headers=headers)
    opener = None
    host = parse.urlparse(url).hostname or ""
    if host in {"127.0.0.1", "localhost", "::1"}:
        opener = request.build_opener(request.ProxyHandler({}))
    open_fn = opener.open if opener is not None else request.urlopen
    with open_fn(req, timeout=timeout_seconds) as response:
        text = response.read(200_000).decode(response.headers.get_content_charset() or "utf-8", errors="replace")
        return int(getattr(response, "status", 200) or 200), text, response.headers.get("content-type", "")


def _endpoint_json_ok(status: int, text: str, content_type: str) -> tuple[bool, str]:
    if not 200 <= status < 300:
        return False, ""
    stripped = text.lstrip()
    if "text/html" in content_type.lower() or stripped.startswith("<"):
        return False, "endpoint returned HTML instead of a model API response"
    try:
        parsed = json.loads(text)
    except Exception:
        return False, "endpoint returned non-JSON response"
    if not isinstance(parsed, dict):
        return False, "endpoint returned JSON but not an object"
    return True, ""


def _endpoint_compatibility_hint(metadata: TargetIntegrationMetadata, wire_api: str, error_text: str) -> str:
    text = str(error_text or "").lower()
    if (
        metadata.surface_family == "codex"
        and wire_api == "responses"
        and ("not implemented" in text or "convert_request_failed" in text)
    ):
        return (
            "Codex requires a Responses API-compatible endpoint; the configured "
            "TARGET_BASE_URL appears to expose chat completions but not /responses."
        )
    return ""


def run_endpoint_probe(
    metadata: TargetIntegrationMetadata,
    model_binding: dict[str, str],
    timeout_seconds: int,
) -> dict[str, Any]:
    probe = dict(metadata.endpoint_probe or {})
    if not probe:
        return {"ok": True, "skipped": True, "reason": "target metadata does not declare endpoint_probe"}

    base_url = str(model_binding.get("base_url", "") or "").strip()
    api_key = str(model_binding.get("api_key", "") or "").strip()
    model = str(model_binding.get("model", "") or model_binding.get("name", "") or "").strip()
    if not base_url or not api_key or not model:
        return {
            "ok": False,
            "skipped": False,
            "error": "TARGET_API_KEY, TARGET_BASE_URL, and TARGET_MODEL are required for endpoint_probe",
        }

    family = str(probe.get("family") or "openai_compatible").strip()
    try:
        if family == "anthropic_messages":
            path = str(probe.get("path") or "/v1/messages")
            if base_url.rstrip("/").endswith("/v1") and path.startswith("/v1/"):
                path = path[len("/v1"):]
            url = _join_url(base_url, path)
            status, text, content_type = _post_json(
                url,
                {
                    "model": model,
                    "max_tokens": 8,
                    "messages": [{"role": "user", "content": "Return OK."}],
                },
                {
                    "content-type": "application/json",
                    "x-api-key": api_key,
                    "anthropic-version": "2023-06-01",
                },
                timeout_seconds,
            )
            ok, response_error = _endpoint_json_ok(status, text, content_type)
            result = {"ok": ok, "status_code": status, "url": url, "content_type": content_type, "response_preview": text[:500]}
            if response_error:
                result["error"] = response_error
            return result

        wire_api = str(probe.get("wire_api") or "chat").strip()
        if wire_api == "responses":
            url = _join_url(base_url, "/responses")
            payload = {"model": model, "input": "Return OK.", "max_output_tokens": 8}
        else:
            url = _join_url(base_url, "/chat/completions")
            payload = {
                "model": model,
                "messages": [{"role": "user", "content": "Return OK."}],
                "max_tokens": 8,
            }
        status, text, content_type = _post_json(
            url,
            payload,
            {"content-type": "application/json", "authorization": f"Bearer {api_key}"},
            timeout_seconds,
        )
        ok, response_error = _endpoint_json_ok(status, text, content_type)
        result = {"ok": ok, "status_code": status, "url": url, "wire_api": wire_api, "content_type": content_type, "response_preview": text[:500]}
        if response_error:
            result["error"] = response_error
            hint = _endpoint_compatibility_hint(metadata, wire_api, response_error)
            if hint:
                result["compatibility_error"] = hint
        return result
    except error.HTTPError as exc:
        body = exc.read(2000).decode("utf-8", errors="replace") if exc.fp else ""
        result = {"ok": False, "status_code": exc.code, "url": getattr(exc, "url", ""), "error": body or str(exc)}
        wire_api = str(probe.get("wire_api") or "chat").strip()
        hint = _endpoint_compatibility_hint(metadata, wire_api, body or str(exc))
        if hint:
            result["compatibility_error"] = hint
        return result
    except error.URLError as exc:
        return {"ok": False, "error": str(exc.reason)}
    except Exception as exc:
        return {"ok": False, "error": str(exc)}


def run_delivery_smoke(
    target_config: dict[str, Any],
    surface_family: str,
    target_config_path: Path,
    output_root: str,
) -> dict[str, Any]:
    del surface_family
    integration = target_config.get("model_integration")
    if not isinstance(integration, dict):
        return {"ok": False, "error": "target.model_integration is required"}
    runtime_env = {
        "HOME": "/tmp/openart-target/home",
        "XDG_CONFIG_HOME": "/tmp/openart-target/config",
        "XDG_DATA_HOME": "/tmp/openart-target/data",
        "XDG_CACHE_HOME": "/tmp/openart-target/cache",
        "OPENART_RUNNER_STATE_DIR": "/tmp/openart-target/state",
    }
    result = stage_model_integration(
        integration,
        role="target",
        runtime_env=runtime_env,
        output_dir=output_root,
        target_config_path=str(target_config_path),
        repo_root=REPO_ROOT,
        symbolic_roots={
            "HOME": lambda env: env.get("HOME", ""),
            "XDG_CONFIG_HOME": lambda env: env.get("XDG_CONFIG_HOME", ""),
            "XDG_DATA_HOME": lambda env: env.get("XDG_DATA_HOME", ""),
            "XDG_CACHE_HOME": lambda env: env.get("XDG_CACHE_HOME", ""),
            "WORKSPACE": lambda env: "/workspace",
            "RUNNER_STATE_DIR": lambda env: env.get("OPENART_RUNNER_STATE_DIR", ""),
        },
    )
    if result is None:
        return {"ok": False, "error": "model integration could not be staged"}
    return {
        "ok": True,
        "provider_family": result.provider_family,
        "delivery_type": result.delivery_type,
        "env_names": result.env_names,
        "env_keys": sorted(result.env),
        "config": (
            {
                "host_path": result.config.host_path,
                "destination": result.config.destination,
                "format": result.config.format,
            }
            if result.config is not None
            else None
        ),
    }


def validate_adapter(
    *,
    target_config_path: Path,
    surface_family: str = "",
    docs_url: str = "",
    require_official_docs: bool = False,
    max_doc_age_days: int = 365,
    timeout_seconds: int = 30,
    fetcher: FetchDocsFn = fetch_docs_url,
    endpoint_probe_runner: EndpointProbeFn = run_endpoint_probe,
    smoke_runner: SmokeFn = run_delivery_smoke,
) -> dict[str, Any]:
    target_config = load_target_config(target_config_path)
    surface_key = canonical_surface_family(surface_family or surface_family_from_target_config(target_config))
    metadata = get_target_integration_metadata(surface_key)
    fetched_at = datetime.now(timezone.utc).isoformat()
    errors: list[str] = []

    if metadata is None:
        return {
            "surface_family": surface_key,
            "fetch_timestamp": fetched_at,
            "status": "invalid",
            "errors": [f"unknown target surface_family: {surface_key}"],
        }

    effective_docs_url = docs_url or metadata.docs_url
    docs_result: dict[str, Any]
    try:
        fetched = fetcher(effective_docs_url, timeout_seconds)
        docs_result = validate_docs_evidence(
            fetched,
            metadata,
            docs_url=effective_docs_url,
            require_official_docs=require_official_docs,
            max_doc_age_days=max_doc_age_days,
        )
    except Exception as exc:
        docs_result = {
            "ok": False,
            "url": effective_docs_url,
            "matched_fields": [],
            "missing_fields": list(metadata.required_doc_keywords),
            "error": str(exc),
        }

    integration = target_config.get("model_integration") if isinstance(target_config, dict) else {}
    model_binding: dict[str, str] = {}
    try:
        model_binding = resolve_model_binding(
            integration if isinstance(integration, dict) else {},
            required_fields=metadata.required_model_fields,
            require_binding=False,
        )
    except Exception as exc:
        errors.append(str(exc))

    smoke_result: dict[str, Any]
    smoke_root = tempfile.mkdtemp(prefix="openart-model-delivery-smoke-")
    try:
        smoke_result = smoke_runner(target_config, metadata.surface_family, target_config_path, smoke_root)
    except Exception as exc:
        smoke_result = {"ok": False, "error": str(exc)}

    endpoint_result: dict[str, Any]
    if model_binding:
        endpoint_result = endpoint_probe_runner(metadata, model_binding, timeout_seconds)
    else:
        endpoint_result = {"ok": False, "error": "model binding failed; endpoint probe skipped"}

    official = bool(docs_result.get("official"))
    docs_ok = bool(docs_result.get("ok"))
    smoke_ok = bool(smoke_result.get("ok"))
    endpoint_ok = bool(endpoint_result.get("ok"))

    if not docs_ok:
        status = "invalid"
    elif errors or not smoke_ok or not endpoint_ok:
        status = "integration_error"
    elif not official:
        status = "experimental"
    else:
        status = "supported"

    if errors:
        status = "integration_error" if docs_ok else "invalid"

    payload = {
        "surface_family": metadata.surface_family,
        "docs_url": effective_docs_url,
        "fetch_timestamp": fetched_at,
        "required_doc_keywords": list(metadata.required_doc_keywords),
        "docs": docs_result,
        "binding": {
            "provider_family": model_binding.get("provider_family", ""),
            "base_url": model_binding.get("base_url", ""),
            "model": model_binding.get("model", ""),
            "api_key_present": bool(model_binding.get("api_key")),
        },
        "endpoint_probe": endpoint_result,
        "smoke": smoke_result,
        "status": status,
        "errors": errors,
    }
    return payload


def main() -> int:
    args = parse_args()
    target_config_path = Path(args.target_config).resolve()
    payload = validate_adapter(
        target_config_path=target_config_path,
        surface_family=getattr(args, "surface_family", "") or "",
        docs_url=args.docs_url,
        require_official_docs=args.require_official_docs,
        max_doc_age_days=int(args.max_doc_age_days or 0),
        timeout_seconds=max(1, int(args.timeout_seconds or 30)),
    )
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(payload, ensure_ascii=True, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"surface_family": payload.get("surface_family"), "status": payload.get("status"), "output": str(output)}, ensure_ascii=True))
    return 0 if payload.get("status") in {"supported", "experimental"} else 2


if __name__ == "__main__":
    raise SystemExit(main())

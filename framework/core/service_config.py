from __future__ import annotations

import json
import os
import urllib.parse
from typing import Any, Callable, Iterable, Mapping

from framework.core.helpers import resolve_env_value


DEFAULT_SERVICE_ENDPOINTS: dict[str, dict[str, str]] = {
    "gitlab": {
        "web": "http://gitlab:8080",
        "api": "http://gitlab:8080/api/v4",
    },
    "owncloud": {
        "web": "http://owncloud:8080",
        "dav": "http://owncloud:8080/remote.php/dav",
    },
    "plane": {
        "web": "http://plane:3000",
        "api": "http://plane:3000/api",
    },
}

_SERVICE_ENV_WEB_KEYS = {
    "gitlab": "GITLAB_BASEURL",
    "owncloud": "OWNCLOUD_URL",
    "plane": "PLANE_BASEURL",
}

_SERVICE_ENDPOINT_ENV_NAMES = {
    "GITLAB_BASEURL",
    "OWNCLOUD_URL",
    "PLANE_BASEURL",
}

_SERVICE_CREDENTIAL_ENV_NAMES = {
    "GITLAB_ACCESS_TOKEN",
    "GITLAB_TOKEN",
    "OWNCLOUD_USERNAME",
    "OWNCLOUD_PASSWORD",
    "PLANE_API_KEY",
}


def default_service_endpoints(service_name: str) -> dict[str, str]:
    return dict(DEFAULT_SERVICE_ENDPOINTS.get(str(service_name or "").strip().lower(), {}))


def normalize_service_endpoint_overrides(
    overrides: Mapping[str, str] | None,
) -> dict[str, dict[str, str]]:
    normalized: dict[str, dict[str, str]] = {}
    if not overrides:
        return normalized

    for key, value in overrides.items():
        raw_key = str(key).strip().lower()
        raw_value = str(value).strip()
        if not raw_key or not raw_value:
            continue

        if "." in raw_key:
            service_name, endpoint_name = raw_key.split(".", 1)
        else:
            service_name, endpoint_name = raw_key, "web"

        service_name = service_name.strip()
        endpoint_name = endpoint_name.strip() or "web"
        if not service_name:
            continue

        normalized.setdefault(service_name, {})[endpoint_name] = raw_value

    return normalized


def _coerce_nested_endpoint_overrides(
    overrides: Mapping[str, str] | Mapping[str, dict[str, str]],
) -> dict[str, dict[str, str]]:
    sample = next(iter(overrides.values()), None)
    if isinstance(sample, dict):
        nested: dict[str, dict[str, str]] = {}
        for service_name, endpoints in overrides.items():
            if not isinstance(endpoints, dict):
                continue
            target = nested.setdefault(str(service_name).strip().lower(), {})
            for endpoint_name, endpoint_url in endpoints.items():
                endpoint_text = str(endpoint_url).strip()
                if endpoint_text:
                    target[str(endpoint_name).strip().lower() or "web"] = endpoint_text
        return nested
    return normalize_service_endpoint_overrides(overrides)  # type: ignore[arg-type]


def extract_service_config_endpoints(service_config: Mapping[str, Any]) -> dict[str, dict[str, str]]:
    _ = service_config
    return {}


def service_config_env(service_config: Mapping[str, Any]) -> dict[str, str]:
    raw_env = service_config.get("env")
    if not isinstance(raw_env, dict):
        return {}

    result: dict[str, str] = {}
    for key, value in raw_env.items():
        if isinstance(value, (str, int, float, bool)):
            if str(key).strip() in _SERVICE_ENDPOINT_ENV_NAMES | _SERVICE_CREDENTIAL_ENV_NAMES:
                continue
            text = resolve_env_value(value)
            if text:
                result[str(key)] = text
    return result


def service_config_credentials(service_config: Mapping[str, Any], service_name: str) -> dict[str, str]:
    _ = service_config
    _ = service_name
    return {}


def resolve_service_endpoints(
    required_services: Iterable[str],
    service_config: Mapping[str, Any],
    overrides: Mapping[str, str] | dict[str, dict[str, str]] | None = None,
    *,
    environ: Mapping[str, str] | None = None,
) -> dict[str, dict[str, str]]:
    current_env = dict(environ or os.environ)
    required = {str(name or "").strip().lower() for name in required_services if str(name or "").strip()}
    resolved: dict[str, dict[str, str]] = {}
    explicit: dict[str, set[str]] = {}

    for service_name in required:
        defaults = default_service_endpoints(service_name)
        if defaults:
            resolved[service_name] = defaults

    for service_name, env_key in _SERVICE_ENV_WEB_KEYS.items():
        if required and service_name not in required:
            continue
        env_value = str(current_env.get(env_key, "")).strip()
        if env_value:
            resolved.setdefault(service_name, {})["web"] = env_value

    for service_name, endpoints in extract_service_config_endpoints(service_config).items():
        if required and service_name not in required:
            continue
        target = resolved.setdefault(service_name, {})
        for endpoint_name, endpoint_url in endpoints.items():
            target[endpoint_name] = endpoint_url
            explicit.setdefault(service_name, set()).add(endpoint_name)

    if overrides:
        nested_overrides = _coerce_nested_endpoint_overrides(overrides)
        for service_name, endpoints in nested_overrides.items():
            if required and service_name not in required:
                continue
            target = resolved.setdefault(service_name, {})
            for endpoint_name, endpoint_url in endpoints.items():
                target[endpoint_name] = endpoint_url
                explicit.setdefault(service_name, set()).add(endpoint_name)

    gitlab = resolved.get("gitlab")
    if gitlab is not None and gitlab.get("web") and "api" not in explicit.get("gitlab", set()):
        gitlab["api"] = gitlab["web"].rstrip("/") + "/api/v4"

    owncloud = resolved.get("owncloud")
    if owncloud is not None and owncloud.get("web") and "dav" not in explicit.get("owncloud", set()):
        owncloud["dav"] = owncloud["web"].rstrip("/") + "/remote.php/dav"

    plane = resolved.get("plane")
    if plane is not None and plane.get("web") and "api" not in explicit.get("plane", set()):
        plane["api"] = plane["web"].rstrip("/") + "/api"

    return resolved


def flatten_service_endpoints(resolved_endpoints: Mapping[str, Mapping[str, str]]) -> dict[str, str]:
    flat: dict[str, str] = {}
    for service_name, endpoints in resolved_endpoints.items():
        for endpoint_name, endpoint_url in endpoints.items():
            flat[f"{service_name}.{endpoint_name}"] = endpoint_url
    return flat


def runtime_credential_env(
    required_services: Iterable[str],
    get_credentials: Callable[[str], Mapping[str, str]],
) -> dict[str, str]:
    env: dict[str, str] = {}
    for service_name in {str(name or "").strip().lower() for name in required_services if str(name or "").strip()}:
        creds = dict(get_credentials(service_name))
        if service_name == "gitlab":
            token = creds.get("access_token") or creds.get("token") or creds.get("private_token") or ""
            if token:
                env["GITLAB_ACCESS_TOKEN"] = token
                env["GITLAB_TOKEN"] = token
        elif service_name == "owncloud":
            username = creds.get("username") or ""
            password = creds.get("password") or ""
            if username:
                env["OWNCLOUD_USERNAME"] = username
            if password:
                env["OWNCLOUD_PASSWORD"] = password
        elif service_name == "plane":
            api_key = creds.get("api_key") or creds.get("token") or ""
            if api_key:
                env["PLANE_API_KEY"] = api_key
    return env


def build_no_proxy_value(
    resolved_endpoints: Mapping[str, Mapping[str, str]],
    env: Mapping[str, str],
    *,
    environ: Mapping[str, str] | None = None,
) -> str:
    current_env = dict(environ or os.environ)
    hosts: list[str] = []
    for current in (current_env.get("NO_PROXY", ""), current_env.get("no_proxy", "")):
        for item in current.split(","):
            text = item.strip()
            if text and text not in hosts:
                hosts.append(text)

    for hostname in ("localhost", "127.0.0.1", env.get("SERVER_HOSTNAME", "")):
        text = str(hostname or "").strip()
        if text and text not in hosts:
            hosts.append(text)

    for endpoints in resolved_endpoints.values():
        for endpoint_url in endpoints.values():
            parsed = urllib.parse.urlparse(str(endpoint_url))
            hostname = (parsed.hostname or "").strip()
            if hostname and hostname not in hosts:
                hosts.append(hostname)

    return ",".join(hosts)


def build_service_runtime_env(
    required_services: Iterable[str],
    service_config: Mapping[str, Any],
    get_credentials: Callable[[str], Mapping[str, str]],
    *,
    evaluator_harness: bool = False,
    overrides: Mapping[str, str] | dict[str, dict[str, str]] | None = None,
    environ: Mapping[str, str] | None = None,
) -> dict[str, str]:
    required = {str(name or "").strip().lower() for name in required_services if str(name or "").strip()}
    resolved_endpoints = resolve_service_endpoints(required, service_config, overrides, environ=environ)
    env = service_config_env(service_config)

    if "gitlab" in required:
        gitlab = resolved_endpoints.get("gitlab", default_service_endpoints("gitlab"))
        env["GITLAB_BASEURL"] = gitlab.get("web", default_service_endpoints("gitlab").get("web", ""))

    if "owncloud" in required:
        owncloud = resolved_endpoints.get("owncloud", default_service_endpoints("owncloud"))
        env["OWNCLOUD_URL"] = owncloud.get("web", default_service_endpoints("owncloud").get("web", ""))

    if "plane" in required:
        plane = resolved_endpoints.get("plane", default_service_endpoints("plane"))
        env["PLANE_BASEURL"] = plane.get("web", default_service_endpoints("plane").get("web", ""))

    if resolved_endpoints:
        env["OPENART_SERVICE_ENDPOINTS"] = json.dumps(flatten_service_endpoints(resolved_endpoints), ensure_ascii=True)

    env.update(runtime_credential_env(required, get_credentials))

    no_proxy = build_no_proxy_value(resolved_endpoints, env, environ=environ)
    if no_proxy:
        env["NO_PROXY"] = no_proxy
        env["no_proxy"] = no_proxy

    if (required or resolved_endpoints or evaluator_harness) and "OAS_EXTERNAL_MODE" not in env:
        env["OAS_EXTERNAL_MODE"] = "real"

    return env

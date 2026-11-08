"""Render a task bundle's Docker Compose document from a service catalog.

No concrete service names or images live in this module.  The catalog supplies
Compose definitions, endpoint variables, ports, assets, and dependencies; this
module only expands a small set of bridge/host placeholders.
"""

from __future__ import annotations

from pathlib import Path
import re
from typing import Any

import yaml

from framework.task_bundles.services import (
    RequiredServices,
    ServiceCatalog,
    ServiceDefinition,
    load_service_catalog,
)


_PLACEHOLDER = re.compile(r"\{\{\s*([^{}]+?)\s*\}\}")


def project_name(task_id: str) -> str:
    text = str(task_id or "").strip()
    if not text:
        return "openart-task"
    return text if text.startswith("openart") else f"openart-{text}"


def network_name(task_id: str) -> str:
    return f"{project_name(task_id)}-net"


def _service_host(service_name: str, network_mode: str) -> str:
    return service_name if network_mode == "bridge" else "127.0.0.1"


def _render_placeholder(match: re.Match[str], context: dict[str, Any]) -> str:
    expression = match.group(1).strip()
    network_mode = context["network_mode"]
    definition: ServiceDefinition | None = context.get("definition")
    catalog: ServiceCatalog = context["catalog"]

    if expression == "bind_host":
        return "0.0.0.0" if network_mode == "bridge" else "127.0.0.1"
    if expression == "pg_listen":
        return "*" if network_mode == "bridge" else "127.0.0.1"
    if expression in {"admin_public_key", "admin_proof_key"}:
        return getattr(catalog, expression)
    if expression == "service_name":
        return str(context.get("service_name", ""))

    if expression == "pg_host" or expression.startswith(("role_host:", "host:")):
        role_or_service = expression.split(":", 1)[1] if ":" in expression else "pg"
        if expression == "pg_host" or expression.startswith("role_host:"):
            if definition is None:
                raise ValueError(f"{expression!r} is not valid outside a service definition")
            service_name = definition.roles.get(role_or_service, role_or_service)
        else:
            service_name = role_or_service
        return _service_host(service_name, network_mode)

    if expression == "pg_port":
        if definition is None:
            raise ValueError("{{ pg_port }} is not valid outside a service definition")
        bridge_port = definition.ports.get("pg", "5432")
        if network_mode == "bridge":
            return bridge_port
        return definition.host_ports.get("pg", bridge_port)
    if expression == "pg_addr":
        if definition is None:
            raise ValueError("{{ pg_addr }} is not valid outside a service definition")
        pg_service = definition.roles.get("pg", "pg")
        pg_host = _service_host(pg_service, network_mode)
        bridge_port = definition.ports.get("pg", "5432")
        pg_port = (
            bridge_port
            if network_mode == "bridge"
            else definition.host_ports.get("pg", bridge_port)
        )
        return f"{pg_host}:{pg_port}"

    if expression in {"api_port", "ui_port"}:
        if definition is None:
            raise ValueError(f"{{{{ {expression} }}}} is not valid outside a service definition")
        role = expression.split("_", 1)[0]
        if role not in definition.ports:
            raise ValueError(f"{definition.name}: catalog is missing ports.{role}")
        return definition.ports[role]

    if expression.startswith("asset:"):
        return f"./service_assets/{expression.split(':', 1)[1].strip('/')}"

    if expression.startswith("url:"):
        parts = expression.split(":", 2)
        if len(parts) != 3:
            raise ValueError(f"invalid url placeholder: {expression!r}")
        return f"http://{_service_host(parts[1], network_mode)}:{parts[2]}"

    raise ValueError(f"unknown service catalog placeholder: {expression!r}")


def _render_value(value: Any, context: dict[str, Any]) -> Any:
    if isinstance(value, str):
        return _PLACEHOLDER.sub(lambda match: _render_placeholder(match, context), value)
    if isinstance(value, list):
        return [_render_value(item, context) for item in value]
    if isinstance(value, dict):
        return {key: _render_value(item, context) for key, item in value.items()}
    return value


def _finalize_service(
    compose_name: str,
    definition: dict[str, Any],
    *,
    network_mode: str,
    catalog: ServiceCatalog,
) -> dict[str, Any]:
    service = dict(definition)
    admin = bool(service.pop("admin", False))
    service.setdefault("restart", "unless-stopped")
    service.setdefault("env_file", ["ports.env"])
    if network_mode == "host":
        service["network_mode"] = "host"
        service.pop("networks", None)
        service.pop("ports", None)
    else:
        if "network_mode" in service:
            raise ValueError(f"{compose_name}: catalog cannot force network_mode in bridge mode")
        service["networks"] = ["tasknet"]
    if admin:
        environment = dict(service.get("environment") or {})
        environment["DTAP_ADMIN_PUBLIC_KEY"] = catalog.admin_public_key
        environment["DTAP_ADMIN_AUDIENCE"] = compose_name
        environment["DTAP_BACKEND_PROOF_KEY"] = catalog.admin_proof_key
        service["environment"] = environment
    return service


def _seed_depends_on(
    required: RequiredServices,
    catalog: ServiceCatalog,
) -> dict[str, dict[str, str]]:
    depends: dict[str, dict[str, str]] = {}
    for logical_name in required.services:
        definition = catalog.services.get(logical_name)
        if definition is None:
            continue
        target = (
            definition.roles.get("api")
            or definition.roles.get("app")
            or definition.roles.get("main")
            or next(iter(definition.compose), "")
        )
        if not target:
            continue
        compose_definition = definition.compose.get(target) or {}
        condition = "service_healthy" if compose_definition.get("healthcheck") else "service_started"
        depends[target] = {"condition": condition}
    return depends


def _seed_service(
    required: RequiredServices,
    catalog: ServiceCatalog,
    *,
    network_mode: str,
) -> dict[str, Any]:
    service: dict[str, Any] = {
        "image": "openart/task-base:latest",
        "restart": "no",
        "profiles": ["seed"],
        "depends_on": _seed_depends_on(required, catalog),
        "env_file": ["task.env"],
        "volumes": ["./seed:/seed:ro", "../task/workspace:/bundle/workspace:ro"],
        "command": ["/bin/bash", "-lc", "/opt/openart-venv/bin/python3 /seed/seed_services.py"],
    }
    if network_mode == "host":
        service["network_mode"] = "host"
    else:
        service["networks"] = ["tasknet"]
    return service


def _collect_volumes(services: dict[str, dict[str, Any]]) -> dict[str, Any]:
    volumes: dict[str, Any] = {}
    for service in services.values():
        for volume in service.get("volumes", []) or []:
            if not isinstance(volume, str):
                continue
            name = volume.split(":", 1)[0].strip()
            if not name or name.startswith((".", "/")):
                continue
            volumes.setdefault(name, {})
    return volumes


def build_env(
    task_id: str,
    required: RequiredServices,
    *,
    network_mode: str = "bridge",
    catalog: ServiceCatalog | None = None,
) -> dict[str, str]:
    active_catalog = catalog or load_service_catalog()
    defaults = dict(active_catalog.env_defaults)
    env: dict[str, str] = {
        "TASK_ID": task_id,
        "COMPOSE_PROJECT_NAME": project_name(task_id),
        **defaults,
    }
    for logical_name in required.services:
        definition = active_catalog.services.get(logical_name)
        if definition is None:
            continue
        context = {
            "network_mode": network_mode,
            "catalog": active_catalog,
            "definition": definition,
            "logical_service": logical_name,
        }
        env.update(_render_value(dict(definition.task_env), context))
    for key, value in list(env.items()):
        for name, default in defaults.items():
            value = value.replace(f"${{{name}}}", default)
        env[key] = value
    return env


def build_compose(
    task_id: str,
    required: RequiredServices,
    *,
    network_mode: str = "bridge",
    catalog: ServiceCatalog | None = None,
) -> dict[str, Any]:
    active_catalog = catalog or load_service_catalog()
    services: dict[str, dict[str, Any]] = {}
    for logical_name in required.services:
        definition = active_catalog.services.get(logical_name)
        if definition is None:
            continue
        context = {
            "network_mode": network_mode,
            "catalog": active_catalog,
            "definition": definition,
            "logical_service": logical_name,
        }
        for compose_name, raw_definition in definition.compose.items():
            service_context = {**context, "service_name": compose_name}
            rendered = _render_value(raw_definition, service_context)
            services[compose_name] = _finalize_service(
                compose_name,
                rendered,
                network_mode=network_mode,
                catalog=active_catalog,
            )

    services["seed"] = _seed_service(required, active_catalog, network_mode=network_mode)

    compose: dict[str, Any] = {
        "name": project_name(task_id),
        "services": services,
    }
    if network_mode == "bridge":
        compose["networks"] = {
            "tasknet": {
                "name": network_name(task_id),
                "driver": "bridge",
            }
        }
    volumes = _collect_volumes(services)
    if volumes:
        compose["volumes"] = volumes
    return compose


def write_compose(path: str | Path, compose: dict[str, Any]) -> str:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(yaml.safe_dump(compose, sort_keys=False, default_flow_style=False), encoding="utf-8")
    return str(target)


def write_env(path: str | Path, env: dict[str, str]) -> str:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    lines = [f"{key}={value}" for key, value in env.items()]
    target.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return str(target)


__all__ = [
    "build_compose",
    "build_env",
    "network_name",
    "project_name",
    "write_compose",
    "write_env",
]
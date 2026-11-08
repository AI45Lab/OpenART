"""Service catalog loading and task → service extraction.

The framework intentionally knows nothing about concrete services.  It reads a
catalog (``services/catalog/services.yaml`` by default) that describes the
Compose services, endpoint environment, ports, assets, and dependencies for
each logical service.  Adding a service is a catalog change.
"""

from __future__ import annotations

from dataclasses import dataclass
import json
import os
from pathlib import Path
from typing import Any, Iterable

import yaml


DEFAULT_CATALOG_PATH = Path(__file__).resolve().parents[2] / "services" / "catalog" / "services.yaml"


@dataclass(frozen=True)
class ServiceDefinition:
    name: str
    compose: dict[str, dict[str, Any]]
    roles: dict[str, str]
    ports: dict[str, str]
    host_ports: dict[str, str]
    task_env: dict[str, str]
    requires: tuple[str, ...]
    assets: tuple[str, ...]
    bootstrap: str | None = None

    @property
    def compose_services(self) -> tuple[str, ...]:
        return tuple(self.compose)


@dataclass(frozen=True)
class ServiceCatalog:
    path: Path
    services: dict[str, ServiceDefinition]
    local_values: frozenset[str]
    aliases: dict[str, str]
    tool_prefixes: dict[str, str]
    admin_public_key: str
    admin_proof_key: str
    env_defaults: dict[str, str]
    credential_prefixes: tuple[str, ...]

    def normalize_service(self, value: str) -> str:
        text = str(value or "").strip().lower()
        return self.aliases.get(text, text)

    def infer_service(self, tool: str) -> str:
        for prefix, target in self.tool_prefixes.items():
            if not tool.startswith(prefix):
                continue
            if target == "@suffix":
                return self.normalize_service(tool[len(prefix) :])
            return self.normalize_service(target)
        return ""

    def resolve_service(self, tool: str, pool_service: str) -> str:
        inferred = self.infer_service(tool)
        if inferred:
            return inferred
        pool = self.normalize_service(pool_service)
        if pool in self.local_values:
            return ""
        return pool

    def expand(self, names: Iterable[str]) -> set[str]:
        result = {name for name in names if name}
        queue = list(result)
        while queue:
            definition = self.services.get(queue.pop())
            if definition is None:
                continue
            for required in definition.requires:
                if required in self.services and required not in result:
                    result.add(required)
                    queue.append(required)
        return result

    def compose_services_for(self, names: Iterable[str]) -> tuple[str, ...]:
        result: list[str] = []
        for name in sorted(set(names)):
            definition = self.services.get(name)
            if definition is None:
                continue
            for compose_name in definition.compose_services:
                if compose_name not in result:
                    result.append(compose_name)
        return tuple(result)

    def task_env_for(self, names: Iterable[str]) -> dict[str, str]:
        env: dict[str, str] = {}
        for name in sorted(set(names)):
            definition = self.services.get(name)
            if definition is None:
                continue
            env.update(definition.task_env)
        return env

    def health_env_for(self, names: Iterable[str]) -> dict[str, str]:
        """Map each selected service to its task.env health URL key."""

        result: dict[str, str] = {}
        for name in sorted(set(names)):
            definition = self.services.get(name)
            if definition is None:
                continue
            for key in definition.task_env:
                if key.endswith("_HEALTH_URL"):
                    result[name] = key
                    break
        return result

    def assets_for(self, names: Iterable[str]) -> dict[str, str]:
        result: dict[str, str] = {}
        for name in sorted(set(names)):
            definition = self.services.get(name)
            if definition is None:
                continue
            for asset in definition.assets:
                result[asset] = asset
        return result

    def bootstrap_for(self, names: Iterable[str]) -> str:
        for name in sorted(set(names)):
            definition = self.services.get(name)
            if definition is not None and definition.bootstrap:
                return definition.bootstrap
        return ""


@dataclass(frozen=True)
class RequiredServices:
    """Services selected by a task's tool graph."""

    services: tuple[str, ...]
    compose_services: tuple[str, ...]
    unknown: tuple[str, ...]
    tools: tuple[str, ...]


def _derive_credential_prefixes(
    services: dict[str, ServiceDefinition],
    env_defaults: dict[str, str],
) -> tuple[str, ...]:
    """Infer credential prefixes from catalog environment variable names.

    A catalog can override this with ``selection.credential_prefixes``.  The
    fallback keeps new services protected without editing framework code:
    ``ACME_URL`` yields ``ACME_`` and ``DTAP_SLACK_URL`` yields ``DTAP_``.
    """

    prefixes: set[str] = set()
    for key in env_defaults:
        head, separator, _tail = key.partition("_")
        if separator and head:
            prefixes.add(f"{head.upper()}_")
    for definition in services.values():
        for key in definition.task_env:
            head, separator, _tail = key.partition("_")
            if separator and head:
                prefixes.add(f"{head.upper()}_")
    return tuple(sorted(prefixes))


def load_service_catalog(path: str | Path | None = None) -> ServiceCatalog:
    catalog_path = Path(
        path
        or os.environ.get("OPENART_SERVICE_CATALOG", "")
        or DEFAULT_CATALOG_PATH
    ).resolve()
    payload = yaml.safe_load(catalog_path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"service catalog is not a mapping: {catalog_path}")

    selection = payload.get("selection") if isinstance(payload.get("selection"), dict) else {}
    defaults = payload.get("defaults") if isinstance(payload.get("defaults"), dict) else {}

    services: dict[str, ServiceDefinition] = {}
    for name, raw in (payload.get("services") or {}).items():
        if not isinstance(raw, dict):
            continue
        compose = raw.get("compose") if isinstance(raw.get("compose"), dict) else {}
        services[str(name)] = ServiceDefinition(
            name=str(name),
            compose={str(key): value for key, value in compose.items() if isinstance(value, dict)},
            roles={str(key): str(value) for key, value in (raw.get("roles") or {}).items()},
            ports={str(key): str(value) for key, value in (raw.get("ports") or {}).items()},
            host_ports={str(key): str(value) for key, value in (raw.get("host_ports") or {}).items()},
            task_env={str(key): str(value) for key, value in (raw.get("task_env") or {}).items()},
            requires=tuple(str(item) for item in (raw.get("requires") or [])),
            assets=tuple(str(item) for item in (raw.get("assets") or [])),
            bootstrap=str(raw.get("bootstrap") or "") or None,
        )

    env_defaults = {str(key): str(value) for key, value in (defaults.get("env") or {}).items()}
    credential_prefixes = tuple(
        str(item).strip().upper()
        for item in (selection.get("credential_prefixes") or [])
        if str(item).strip()
    ) or _derive_credential_prefixes(services, env_defaults)

    return ServiceCatalog(
        path=catalog_path,
        services=services,
        local_values=frozenset(str(item).strip().lower() for item in (selection.get("local_values") or [])),
        aliases={
            str(key).strip().lower(): str(value).strip().lower()
            for key, value in (selection.get("aliases") or {}).items()
        },
        tool_prefixes={
            str(key): str(value) for key, value in (selection.get("tool_prefixes") or {}).items()
        },
        admin_public_key=str(defaults.get("admin_public_key") or ""),
        admin_proof_key=str(defaults.get("admin_proof_key") or ""),
        env_defaults=env_defaults,
        credential_prefixes=credential_prefixes,
    )


def _read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _iter_graph_tools(value: Any) -> Iterable[str]:
    if isinstance(value, dict):
        tool = value.get("tool")
        if isinstance(tool, str) and tool.strip():
            yield tool.strip()
        for child in value.values():
            yield from _iter_graph_tools(child)
    elif isinstance(value, list):
        for child in value:
            yield from _iter_graph_tools(child)


def tool_names_from_graph(graph: Any) -> set[str]:
    return set(_iter_graph_tools(graph))


def _tool_service_map(pool: Any) -> dict[str, str]:
    result: dict[str, str] = {}
    if not isinstance(pool, dict):
        return result
    tools = pool.get("tools")
    if not isinstance(tools, list):
        return result
    for item in tools:
        if not isinstance(item, dict):
            continue
        name = str(item.get("name", "") or "").strip()
        service = str(item.get("service", "") or "").strip()
        if name and service:
            result[name] = service
    return result


def extract_required_services(
    task_root: str | Path,
    *,
    catalog: ServiceCatalog | None = None,
) -> RequiredServices:
    root = Path(task_root)
    graph_path = root / "tool_use_graph.json"
    pool_path = root / "tool_pool.json"
    if not graph_path.is_file():
        return RequiredServices((), (), (), ())

    active_catalog = catalog or load_service_catalog()
    graph = _read_json(graph_path)
    tools = tool_names_from_graph(graph)
    by_tool: dict[str, str] = {}
    if pool_path.is_file():
        by_tool = _tool_service_map(_read_json(pool_path))

    found: set[str] = set()
    unknown: set[str] = set()
    for tool in tools:
        service = active_catalog.resolve_service(tool, by_tool.get(tool, ""))
        if not service or service in active_catalog.local_values:
            continue
        if service in active_catalog.services:
            found.add(service)
        else:
            unknown.add(service)

    expanded = active_catalog.expand(found)
    return RequiredServices(
        services=tuple(sorted(expanded)),
        compose_services=active_catalog.compose_services_for(expanded),
        unknown=tuple(sorted(unknown)),
        tools=tuple(sorted(tools)),
    )


def service_env(
    services: Iterable[str],
    *,
    catalog: ServiceCatalog | None = None,
) -> dict[str, str]:
    """Return raw task-side environment templates for the selected services."""

    active_catalog = catalog or load_service_catalog()
    return active_catalog.task_env_for(services)


def compose_service_names(
    required: RequiredServices,
    *,
    catalog: ServiceCatalog | None = None,
) -> tuple[str, ...]:
    if required.compose_services:
        return required.compose_services
    active_catalog = catalog or load_service_catalog()
    return active_catalog.compose_services_for(required.services)


__all__ = [
    "DEFAULT_CATALOG_PATH",
    "RequiredServices",
    "ServiceCatalog",
    "ServiceDefinition",
    "compose_service_names",
    "extract_required_services",
    "load_service_catalog",
    "service_env",
    "tool_names_from_graph",
]
from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path
from typing import Any, Iterable


@dataclass(frozen=True)
class RequiredServices:
    """Services selected by a task's tool graph."""

    services: tuple[str, ...]
    compose_services: tuple[str, ...]
    unknown: tuple[str, ...]
    tools: tuple[str, ...]


# Logical service -> Compose service names.  Only these services are started.
SERVICE_COMPOSE: dict[str, tuple[str, ...]] = {
    "gitlab": ("gitlab",),
    "owncloud": ("owncloud", "owncloud-db", "owncloud-redis"),
    "finance": ("dtap-finance-web",),
    "legal": ("dtap-legal-web",),
    "gmail": ("dtap-gmail-mailpit", "dtap-gmail-service", "dtap-gmail-ui"),
    "slack": ("dtap-slack-api", "dtap-slack-ui"),
    "calendar": ("dtap-calendar-api", "dtap-calendar-ui"),
    "zoom": ("dtap-zoom-api", "dtap-zoom-ui"),
    "paypal": ("dtap-paypal-pg", "dtap-paypal-api", "dtap-paypal-ui"),
    "atlassian": ("dtap-atlassian-pg", "dtap-atlassian-api", "dtap-atlassian-ui"),
    "github": ("dtap-github-db", "dtap-github-api", "dtap-github-ui"),
    "google-form": ("dtap-google-form-api", "dtap-google-form-ui"),
    "googledocs": ("dtap-googledocs-db", "dtap-googledocs-api", "dtap-googledocs-ui"),
    "telegram": ("dtap-telegram-pg", "dtap-telegram-api"),
    "whatsapp": ("dtap-whatsapp-pg", "dtap-whatsapp-api", "dtap-whatsapp-ui"),
    "snowflake": ("dtap-snowflake-pg", "dtap-snowflake-admin"),
    "databricks": ("dtap-databricks-pg", "dtap-databricks-admin"),
    "bigquery": ("dtap-bigquery",),
}


# Service endpoint variables understood by the openart-tools wrappers.  Hosts
# are Compose service names; ports are the DTAP in-container ports.
DTAP_SERVICE_ENV: dict[str, dict[str, str]] = {
    "finance": {
        "DTAP_FINANCE_URL": "http://dtap-finance-web:23000",
        "DTAP_FINANCE_HEALTH_URL": "http://dtap-finance-web:23000/api/health",
    },
    "legal": {
        "DTAP_LEGAL_URL": "http://dtap-legal-web:23100",
        "DTAP_LEGAL_HEALTH_URL": "http://dtap-legal-web:23100/api/health",
    },
    "gmail": {
        "DTAP_GMAIL_URL": "http://dtap-gmail-ui:24004",
        "DTAP_GMAIL_HEALTH_URL": "http://dtap-gmail-service:24001/health",
        "DTAP_GMAIL_SMTP_ADDR": "dtap-gmail-mailpit:24000",
        "DTAP_GMAIL_AUTH_URL": "http://dtap-gmail-service:24001",
        "DTAP_GMAIL_PROXY_URL": "http://dtap-gmail-service:24002",
        "DTAP_GMAIL_UI_URL": "http://dtap-gmail-ui:24003",
        "DTAP_GMAIL_FRONTEND_URL": "http://dtap-gmail-ui:24004",
    },
    "slack": {
        "DTAP_SLACK_URL": "http://dtap-slack-ui:24501",
        "DTAP_SLACK_HEALTH_URL": "http://dtap-slack-api:24500/health",
        "DTAP_SLACK_API_URL": "http://dtap-slack-api:24500",
        "DTAP_SLACK_UI_URL": "http://dtap-slack-ui:24501",
    },
    "calendar": {
        "DTAP_CALENDAR_URL": "http://dtap-calendar-ui:24601",
        "DTAP_CALENDAR_HEALTH_URL": "http://dtap-calendar-api:24600/health",
        "DTAP_CALENDAR_API_URL": "http://dtap-calendar-api:24600",
        "DTAP_CALENDAR_UI_URL": "http://dtap-calendar-ui:24601",
    },
    "zoom": {
        "DTAP_ZOOM_URL": "http://dtap-zoom-ui:24701",
        "DTAP_ZOOM_HEALTH_URL": "http://dtap-zoom-api:24700/health",
        "DTAP_ZOOM_API_URL": "http://dtap-zoom-api:24700",
        "DTAP_ZOOM_UI_URL": "http://dtap-zoom-ui:24701",
    },
    "paypal": {
        "DTAP_PAYPAL_URL": "http://dtap-paypal-ui:25002",
        "DTAP_PAYPAL_HEALTH_URL": "http://dtap-paypal-api:25001/health",
        "DTAP_PAYPAL_PG_ADDR": "dtap-paypal-pg:25000",
        "DTAP_PAYPAL_API_URL": "http://dtap-paypal-api:25001",
        "DTAP_PAYPAL_UI_URL": "http://dtap-paypal-ui:25002",
    },
    "atlassian": {
        "DTAP_ATLASSIAN_URL": "http://dtap-atlassian-ui:25102",
        "DTAP_ATLASSIAN_HEALTH_URL": "http://dtap-atlassian-api:25101/health",
        "DTAP_ATLASSIAN_PG_ADDR": "dtap-atlassian-pg:25100",
        "DTAP_ATLASSIAN_API_URL": "http://dtap-atlassian-api:25101",
        "DTAP_ATLASSIAN_UI_URL": "http://dtap-atlassian-ui:25102",
    },
    "github": {
        "DTAP_GITHUB_URL": "http://dtap-github-ui:25202",
        "DTAP_GITHUB_HEALTH_URL": "http://dtap-github-api:25201/health",
        "DTAP_GITHUB_PG_ADDR": "dtap-github-db:25200",
        "DTAP_GITHUB_API_URL": "http://dtap-github-api:25201",
        "DTAP_GITHUB_UI_URL": "http://dtap-github-ui:25202",
    },
    "google-form": {
        "DTAP_GOOGLE_FORM_URL": "http://dtap-google-form-ui:25301",
        "DTAP_GOOGLE_FORM_HEALTH_URL": "http://dtap-google-form-api:25300/health",
        "DTAP_GOOGLE_FORM_API_URL": "http://dtap-google-form-api:25300",
        "DTAP_GOOGLE_FORM_UI_URL": "http://dtap-google-form-ui:25301",
    },
    "googledocs": {
        "DTAP_GOOGLEDOCS_URL": "http://dtap-googledocs-ui:25402",
        "DTAP_GOOGLEDOCS_HEALTH_URL": "http://dtap-googledocs-api:25401/health",
        "DTAP_GOOGLEDOCS_PG_ADDR": "dtap-googledocs-db:25400",
        "DTAP_GOOGLEDOCS_API_URL": "http://dtap-googledocs-api:25401",
        "DTAP_GOOGLEDOCS_FRONTEND_URL": "http://dtap-googledocs-ui:25402",
    },
    "telegram": {
        "DTAP_TELEGRAM_URL": "http://dtap-telegram-api:25501",
        "DTAP_TELEGRAM_HEALTH_URL": "http://dtap-telegram-api:25501/health",
        "DTAP_TELEGRAM_PG_ADDR": "dtap-telegram-pg:25500",
        "DTAP_TELEGRAM_API_URL": "http://dtap-telegram-api:25501",
    },
    "whatsapp": {
        "DTAP_WHATSAPP_URL": "http://dtap-whatsapp-ui:25602",
        "DTAP_WHATSAPP_HEALTH_URL": "http://dtap-whatsapp-api:25601/health",
        "DTAP_WHATSAPP_PG_ADDR": "dtap-whatsapp-pg:25600",
        "DTAP_WHATSAPP_API_URL": "http://dtap-whatsapp-api:25601",
        "DTAP_WHATSAPP_FRONTEND_URL": "http://dtap-whatsapp-ui:25602",
    },
    "snowflake": {
        "DTAP_SNOWFLAKE_URL": "http://dtap-snowflake-admin:25701",
        "DTAP_SNOWFLAKE_HEALTH_URL": "http://dtap-snowflake-admin:25701/health",
        "DTAP_SNOWFLAKE_PG_ADDR": "dtap-snowflake-pg:25700",
        "DTAP_SNOWFLAKE_ADMIN_URL": "http://dtap-snowflake-admin:25701",
    },
    "databricks": {
        "DTAP_DATABRICKS_URL": "http://dtap-databricks-admin:25801",
        "DTAP_DATABRICKS_HEALTH_URL": "http://dtap-databricks-admin:25801/health",
        "DTAP_DATABRICKS_PG_ADDR": "dtap-databricks-pg:25800",
        "DTAP_DATABRICKS_ADMIN_URL": "http://dtap-databricks-admin:25801",
    },
    "bigquery": {
        "DTAP_BIGQUERY_URL": "http://dtap-bigquery:25900",
        "DTAP_BIGQUERY_API_URL": "http://dtap-bigquery:25900",
        "DTAP_BIGQUERY_API_ADDR": "dtap-bigquery:25900",
        "DTAP_BIGQUERY_GRPC_ADDR": "dtap-bigquery:25901",
    },
}


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


# Tool-pool ``service`` values that describe local tool categories rather than
# external services.  They must never start a container.
NON_SERVICE_CATEGORIES = frozenset(
    {
        "",
        "dtap",
        "workspace",
        "document",
        "tool",
        "skill",
        "registry",
        "planner",
        "local",
    }
)

# Spelling differences between tool-pool metadata and Compose service names.
SERVICE_ALIASES = {
    "google_form": "google-form",
    "googleform": "google-form",
    "google_docs": "googledocs",
    "google-docs": "googledocs",
    "googledoc": "googledocs",
    "google_calendar": "calendar",
    "google-calendar": "calendar",
}


def _normalize_service(value: str) -> str:
    text = str(value or "").strip().lower()
    return SERVICE_ALIASES.get(text, text)


def _infer_service(tool: str) -> str:
    if tool.startswith("dtap."):
        return _normalize_service(tool.split(".", 1)[1])
    if tool.startswith("gitlab."):
        return "gitlab"
    if tool.startswith("owncloud."):
        return "owncloud"
    if tool.startswith("gitea."):
        return "gitea"
    if tool.startswith("mattermost."):
        return "mattermost"
    return ""


def _resolve_service(tool: str, pool_service: str) -> str:
    """Resolve a tool to a logical service.

    A tool-name prefix is authoritative when it names a known service family.
    Some planner tasks contain a generic pool value such as ``dtap`` for a
    concrete ``dtap.atlassian`` tool, or a local category such as ``workspace``
    for a file tool.  Only genuinely external services should survive.
    """

    inferred = _infer_service(tool)
    if inferred:
        return inferred
    return _normalize_service(pool_service)


def extract_required_services(task_root: str | Path) -> RequiredServices:
    root = Path(task_root)
    graph_path = root / "tool_use_graph.json"
    pool_path = root / "tool_pool.json"
    if not graph_path.is_file():
        return RequiredServices((), (), (), ())

    graph = _read_json(graph_path)
    tools = tool_names_from_graph(graph)
    by_tool: dict[str, str] = {}
    if pool_path.is_file():
        by_tool = _tool_service_map(_read_json(pool_path))

    found: set[str] = set()
    unknown: set[str] = set()
    for tool in tools:
        service = _resolve_service(tool, by_tool.get(tool, ""))
        if not service or service in NON_SERVICE_CATEGORIES:
            continue
        if service in SERVICE_COMPOSE:
            found.add(service)
        else:
            unknown.add(service)

    services = tuple(sorted(found))
    compose_services: list[str] = []
    for service in services:
        for name in SERVICE_COMPOSE[service]:
            if name not in compose_services:
                compose_services.append(name)
    return RequiredServices(
        services=services,
        compose_services=tuple(compose_services),
        unknown=tuple(sorted(unknown)),
        tools=tuple(sorted(tools)),
    )


def service_env(services: Iterable[str]) -> dict[str, str]:
    """Return task-side environment variables for the selected services."""

    env: dict[str, str] = {}
    selected = set(services)
    if "gitlab" in selected:
        env["GITLAB_BASEURL"] = "http://gitlab:8929"
        env["GITLAB_ACCESS_TOKEN"] = "${GITLAB_ACCESS_TOKEN}"
    if "owncloud" in selected:
        env["OWNCLOUD_URL"] = "http://owncloud:8080"
        env["OWNCLOUD_USERNAME"] = "${OWNCLOUD_USERNAME}"
        env["OWNCLOUD_PASSWORD"] = "${OWNCLOUD_PASSWORD}"
    for service, values in DTAP_SERVICE_ENV.items():
        if service in selected:
            env.update(values)
    return env


def compose_service_names(required: RequiredServices) -> tuple[str, ...]:
    return required.compose_services
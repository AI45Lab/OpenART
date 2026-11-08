from __future__ import annotations

from pathlib import Path
from typing import Any, Iterable
from urllib.parse import urlsplit, urlunsplit

import yaml

from framework.task_bundles.services import RequiredServices, SERVICE_COMPOSE, service_env


GITLAB_INTERNAL_URL = "http://gitlab:8929"
OWNCLOUD_INTERNAL_URL = "http://owncloud:8080"


def project_name(task_id: str) -> str:
    text = str(task_id or "").strip()
    if not text:
        return "openart-task"
    return text if text.startswith("openart") else f"openart-{text}"


def network_name(task_id: str) -> str:
    return f"{project_name(task_id)}-net"


def _host_url(value: str) -> str:
    """Rewrite an internal service URL to a host-loopback URL."""

    text = str(value or "").strip()
    if not text:
        return text
    if "://" in text:
        parts = urlsplit(text)
        if not parts.hostname:
            return text
        netloc = "127.0.0.1"
        if parts.port:
            netloc = f"{netloc}:{parts.port}"
        return urlunsplit((parts.scheme, netloc, parts.path, parts.query, parts.fragment))
    host, separator, port = text.rpartition(":")
    if separator and host and port.isdigit():
        return f"127.0.0.1:{port}"
    return text


def build_env(task_id: str, required: RequiredServices, *, network_mode: str = "bridge") -> dict[str, str]:
    defaults = {
        "GITLAB_ROOT_PASSWORD": "openart-gitlab-root",
        "GITLAB_ACCESS_TOKEN": "replace-me-after-gitlab-boot",
        "OWNCLOUD_USERNAME": "admin",
        "OWNCLOUD_PASSWORD": "openart-owncloud",
        "OWNCLOUD_DB_ROOT_PASSWORD": "openart-owncloud-root",
        "OWNCLOUD_DB_PASSWORD": "openart-owncloud-db",
    }
    env: dict[str, str] = {
        "TASK_ID": task_id,
        "COMPOSE_PROJECT_NAME": project_name(task_id),
        **defaults,
    }
    for key, value in service_env(required.services).items():
        env[key] = value
    placeholders = {f"${{{key}}}": value for key, value in defaults.items()}
    for key, value in list(env.items()):
        if value in placeholders:
            env[key] = placeholders[value]
    if network_mode == "host":
        for key, value in list(env.items()):
            if key.startswith(("GITLAB_", "OWNCLOUD_", "DTAP_")):
                env[key] = _host_url(value)
    return env


def _dtap_base(image: str, *, network_mode: str, **extra: Any) -> dict[str, Any]:
    service: dict[str, Any] = {
        "image": image,
        "restart": "unless-stopped",
        "env_file": ["ports.env"],
    }
    if network_mode == "host":
        service["network_mode"] = "host"
    else:
        environment = dict(extra.pop("environment", {}) or {})
        environment.setdefault("SERVICE_BIND_HOST", "0.0.0.0")
        environment.setdefault("DTAP_HOST", "0.0.0.0")
        extra["environment"] = environment
        service["networks"] = ["tasknet"]
    service.update(extra)
    return service


def _dtap_services(selected: Iterable[str], *, network_mode: str) -> dict[str, dict[str, Any]]:
    selected = set(selected)
    services: dict[str, dict[str, Any]] = {}
    if "finance" in selected:
        services["dtap-finance-web"] = _dtap_base("decodingtrustagent/finance:latest", network_mode=network_mode)
    if "legal" in selected:
        services["dtap-legal-web"] = _dtap_base("decodingtrustagent/legal:latest", network_mode=network_mode)
    if "gmail" in selected:
        services["dtap-gmail-mailpit"] = _dtap_base("axllent/mailpit:latest", network_mode=network_mode)
        services["dtap-gmail-service"] = _dtap_base(
            "decodingtrustagent/gmail:service-latest",
            network_mode=network_mode,
            depends_on=["dtap-gmail-mailpit"],
        )
        services["dtap-gmail-ui"] = _dtap_base(
            "decodingtrustagent/gmail:ui-latest",
            network_mode=network_mode,
            depends_on=["dtap-gmail-service"],
        )
    if "slack" in selected:
        services["dtap-slack-api"] = _dtap_base("decodingtrustagent/slack:api-latest", network_mode=network_mode)
        services["dtap-slack-ui"] = _dtap_base(
            "decodingtrustagent/slack:ui-latest",
            network_mode=network_mode,
            depends_on=["dtap-slack-api"],
        )
    if "calendar" in selected:
        services["dtap-calendar-api"] = _dtap_base("decodingtrustagent/google-calendar:api-latest", network_mode=network_mode)
        services["dtap-calendar-ui"] = _dtap_base(
            "decodingtrustagent/google-calendar:ui-latest",
            network_mode=network_mode,
            depends_on=["dtap-calendar-api"],
        )
    if "zoom" in selected:
        services["dtap-zoom-api"] = _dtap_base("decodingtrustagent/zoom:api-latest", network_mode=network_mode)
        services["dtap-zoom-ui"] = _dtap_base(
            "decodingtrustagent/zoom:ui-latest",
            network_mode=network_mode,
            depends_on=["dtap-zoom-api"],
        )
    if "paypal" in selected:
        services["dtap-paypal-pg"] = _dtap_base(
            "postgres:16",
            network_mode=network_mode,
            command=["postgres", "-c", "port=25000"],
            environment={
                "POSTGRES_USER": "postgres",
                "POSTGRES_PASSWORD": "postgres",
                "POSTGRES_DB": "paypal",
            },
            volumes=["dtap-paypal-pg:/var/lib/postgresql/data"],
        )
        services["dtap-paypal-api"] = _dtap_base(
            "decodingtrustagent/paypal:api-latest",
            network_mode=network_mode,
            depends_on=["dtap-paypal-pg"],
        )
        services["dtap-paypal-ui"] = _dtap_base(
            "decodingtrustagent/paypal:ui-latest",
            network_mode=network_mode,
            depends_on=["dtap-paypal-api"],
        )
    if "atlassian" in selected:
        services["dtap-atlassian-pg"] = _dtap_base(
            "postgres:16",
            network_mode=network_mode,
            command=["postgres", "-c", "port=25100"],
            environment={
                "POSTGRES_USER": "postgres",
                "POSTGRES_PASSWORD": "postgres",
                "POSTGRES_DB": "atlassian",
            },
            volumes=["dtap-atlassian-pg:/var/lib/postgresql/data"],
        )
        services["dtap-atlassian-api"] = _dtap_base(
            "decodingtrustagent/atlassian:api-latest",
            network_mode=network_mode,
            depends_on=["dtap-atlassian-pg"],
        )
        services["dtap-atlassian-ui"] = _dtap_base(
            "decodingtrustagent/atlassian:ui-latest",
            network_mode=network_mode,
            depends_on=["dtap-atlassian-api"],
        )
    if "github" in selected:
        services["dtap-github-db"] = _dtap_base(
            "decodingtrustagent/github:db-latest",
            network_mode=network_mode,
            volumes=["dtap-github-db:/var/lib/postgresql/data"],
        )
        services["dtap-github-api"] = _dtap_base(
            "decodingtrustagent/github:api-latest",
            network_mode=network_mode,
            depends_on=["dtap-github-db"],
        )
        services["dtap-github-ui"] = _dtap_base(
            "decodingtrustagent/github:ui-latest",
            network_mode=network_mode,
            depends_on=["dtap-github-api"],
        )
    if "google-form" in selected:
        services["dtap-google-form-api"] = _dtap_base(
            "decodingtrustagent/google-form:api-latest",
            network_mode=network_mode,
        )
        services["dtap-google-form-ui"] = _dtap_base(
            "decodingtrustagent/google-form:ui-latest",
            network_mode=network_mode,
            depends_on=["dtap-google-form-api"],
        )
    if "googledocs" in selected:
        services["dtap-googledocs-db"] = _dtap_base(
            "decodingtrustagent/google-docs:db-latest",
            network_mode=network_mode,
            volumes=["dtap-googledocs-db:/var/lib/postgresql/data"],
        )
        services["dtap-googledocs-api"] = _dtap_base(
            "decodingtrustagent/google-docs:api-latest",
            network_mode=network_mode,
            depends_on=["dtap-googledocs-db"],
        )
        services["dtap-googledocs-ui"] = _dtap_base(
            "decodingtrustagent/google-docs:ui-latest",
            network_mode=network_mode,
            depends_on=["dtap-googledocs-api"],
        )
    if "telegram" in selected:
        services["dtap-telegram-pg"] = _dtap_base(
            "decodingtrustagent/telegram:pg-latest",
            network_mode=network_mode,
            volumes=["dtap-telegram-pg:/var/lib/postgresql/data"],
        )
        services["dtap-telegram-api"] = _dtap_base(
            "decodingtrustagent/telegram:api-latest",
            network_mode=network_mode,
            depends_on=["dtap-telegram-pg"],
        )
    if "whatsapp" in selected:
        services["dtap-whatsapp-pg"] = _dtap_base(
            "decodingtrustagent/whatsapp:pg",
            network_mode=network_mode,
            volumes=["dtap-whatsapp-pg:/var/lib/postgresql/data"],
        )
        services["dtap-whatsapp-api"] = _dtap_base(
            "decodingtrustagent/whatsapp:api-latest",
            network_mode=network_mode,
            depends_on=["dtap-whatsapp-pg"],
        )
        services["dtap-whatsapp-ui"] = _dtap_base(
            "decodingtrustagent/whatsapp:ui-latest",
            network_mode=network_mode,
            depends_on=["dtap-whatsapp-api"],
        )
    if "snowflake" in selected:
        services["dtap-snowflake-pg"] = _dtap_base(
            "decodingtrustagent/snowflake:latest",
            network_mode=network_mode,
            volumes=["dtap-snowflake-pg:/var/lib/postgresql/data"],
        )
        services["dtap-snowflake-admin"] = _dtap_base(
            "decodingtrustagent/snowflake:admin",
            network_mode=network_mode,
            depends_on=["dtap-snowflake-pg"],
        )
    if "databricks" in selected:
        services["dtap-databricks-pg"] = _dtap_base(
            "decodingtrustagent/databricks:latest",
            network_mode=network_mode,
            volumes=["dtap-databricks-pg:/var/lib/postgresql/data"],
        )
        services["dtap-databricks-admin"] = _dtap_base(
            "decodingtrustagent/databricks:admin",
            network_mode=network_mode,
            depends_on=["dtap-databricks-pg"],
        )
    if "bigquery" in selected:
        services["dtap-bigquery"] = _dtap_base(
            "ghcr.io/goccy/bigquery-emulator:latest",
            network_mode=network_mode,
            command=["--project=openart", "--port=25900", "--grpc-port=25901"],
            volumes=["dtap-bigquery-data:/data"],
        )
    return services


def _gitlab_service(*, network_mode: str) -> dict[str, Any]:
    external_url = "http://127.0.0.1:8929" if network_mode == "host" else GITLAB_INTERNAL_URL
    omnibus = "; ".join(
        [
            f"external_url '{external_url}'",
            "gitlab_rails['initial_root_password'] = ENV['GITLAB_ROOT_PASSWORD']",
            "prometheus_monitoring['enable'] = false",
            "gitlab_kas['enable'] = false",
            "puma['worker_processes'] = 2",
            "sidekiq['max_concurrency'] = 10",
            "postgresql['shared_buffers'] = '256MB'",
            "nginx['listen_port'] = 8929",
        ]
    )
    service: dict[str, Any] = {
        "image": "gitlab/gitlab-ce:latest",
        "hostname": "gitlab",
        "restart": "unless-stopped",
        "shm_size": "256m",
        "environment": {
            "GITLAB_OMNIBUS_CONFIG": omnibus,
            "GITLAB_ROOT_PASSWORD": "${GITLAB_ROOT_PASSWORD}",
        },
        "volumes": [
            "gitlab-config:/etc/gitlab",
            "gitlab-logs:/var/log/gitlab",
            "gitlab-data:/var/opt/gitlab",
        ],
        "healthcheck": {
            "test": ["CMD-SHELL", "curl -fsS http://localhost:8929/-/health || exit 1"],
            "interval": "15s",
            "timeout": "10s",
            "retries": 60,
            "start_period": "120s",
        },
    }
    if network_mode == "host":
        service["network_mode"] = "host"
    else:
        service["networks"] = ["tasknet"]
        service["ports"] = ["127.0.0.1::8929"]
    return service


def _owncloud_services(*, network_mode: str) -> dict[str, dict[str, Any]]:
    domain = "127.0.0.1:8080" if network_mode == "host" else "owncloud:8080"
    db = {
        "image": "mariadb:10.11",
        "restart": "unless-stopped",
        "environment": {
            "MARIADB_ROOT_PASSWORD": "${OWNCLOUD_DB_ROOT_PASSWORD}",
            "MARIADB_DATABASE": "owncloud",
            "MARIADB_USER": "owncloud",
            "MARIADB_PASSWORD": "${OWNCLOUD_DB_PASSWORD}",
        },
        "volumes": ["owncloud-db:/var/lib/mysql"],
        "healthcheck": {
            "test": ["CMD", "healthcheck.sh", "--connect", "--innodb_initialized"],
            "interval": "10s",
            "timeout": "5s",
            "retries": 20,
        },
    }
    redis = {"image": "redis:7-alpine", "restart": "unless-stopped"}
    app: dict[str, Any] = {
        "image": "owncloud/server:latest",
        "restart": "unless-stopped",
        "depends_on": {
            "owncloud-db": {"condition": "service_healthy"},
            "owncloud-redis": {"condition": "service_started"},
        },
        "environment": {
            "OWNCLOUD_DOMAIN": domain,
            "OWNCLOUD_TRUSTED_DOMAINS": "owncloud localhost 127.0.0.1",
            "OWNCLOUD_ADMIN_USERNAME": "${OWNCLOUD_USERNAME}",
            "OWNCLOUD_ADMIN_PASSWORD": "${OWNCLOUD_PASSWORD}",
            "OWNCLOUD_DB_TYPE": "mysql",
            "OWNCLOUD_DB_HOST": "owncloud-db",
            "OWNCLOUD_DB_NAME": "owncloud",
            "OWNCLOUD_DB_USERNAME": "owncloud",
            "OWNCLOUD_DB_PASSWORD": "${OWNCLOUD_DB_PASSWORD}",
            "OWNCLOUD_REDIS_ENABLED": "true",
            "OWNCLOUD_REDIS_HOST": "owncloud-redis",
        },
        "volumes": ["owncloud-data:/mnt/data"],
        "healthcheck": {
            "test": ["CMD-SHELL", "curl -fsS http://localhost:8080/status.php || exit 1"],
            "interval": "15s",
            "timeout": "10s",
            "retries": 40,
            "start_period": "60s",
        },
    }
    if network_mode == "host":
        db["network_mode"] = "host"
        redis["network_mode"] = "host"
        app["network_mode"] = "host"
    else:
        db["networks"] = ["tasknet"]
        redis["networks"] = ["tasknet"]
        app["networks"] = ["tasknet"]
        app["ports"] = ["127.0.0.1::8080"]
    return {"owncloud-db": db, "owncloud-redis": redis, "owncloud": app}


def _seed_service(required: RequiredServices, *, network_mode: str) -> dict[str, Any]:
    depends: dict[str, Any] = {}
    if "gitlab" in required.services:
        depends["gitlab"] = {"condition": "service_healthy"}
    if "owncloud" in required.services:
        depends["owncloud"] = {"condition": "service_started"}
    for service in required.services:
        names = SERVICE_COMPOSE.get(service, ())
        if not names or service in {"gitlab", "owncloud"}:
            continue
        name = names[0]
        depends[name] = {"condition": "service_started"}
    service: dict[str, Any] = {
        "image": "openart/task-base:latest",
        "restart": "no",
        "profiles": ["seed"],
        "depends_on": depends,
        "env_file": ["task.env"],
        "volumes": ["./seed:/seed:ro", "../task/workspace:/bundle/workspace:ro"],
        "command": ["/bin/bash", "-lc", "/opt/openart-venv/bin/python3 /seed/seed_services.py"],
    }
    if network_mode == "host":
        service["network_mode"] = "host"
    else:
        service["networks"] = ["tasknet"]
    return service


def build_compose(
    task_id: str,
    required: RequiredServices,
    *,
    network_mode: str = "bridge",
) -> dict[str, Any]:
    services: dict[str, dict[str, Any]] = {}
    if "gitlab" in required.services:
        services["gitlab"] = _gitlab_service(network_mode=network_mode)
    if "owncloud" in required.services:
        services.update(_owncloud_services(network_mode=network_mode))
    services.update(_dtap_services(required.services, network_mode=network_mode))
    services["seed"] = _seed_service(required, network_mode=network_mode)

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
    volumes: dict[str, Any] = {}
    for service in services.values():
        for volume in service.get("volumes", []) or []:
            if not isinstance(volume, str):
                continue
            name = volume.split(":", 1)[0].strip()
            if not name or name.startswith((".", "/")):
                continue
            volumes.setdefault(name, {})
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
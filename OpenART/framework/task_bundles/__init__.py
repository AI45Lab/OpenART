"""Self-contained Docker Compose bundles for OpenART tasks.

The module turns a task directory (``task.md`` + ``workspace/`` +
``tool_use_graph.json``) into a generated bundle that starts only the services
the task actually uses.  Concrete services come from a catalog, not from
framework code.
"""

from framework.task_bundles.services import (
    DEFAULT_CATALOG_PATH,
    HOOK_TYPES,
    RequiredServices,
    ServiceCatalog,
    ServiceDefinition,
    compose_service_names,
    extract_required_services,
    load_service_catalog,
    service_env,
)

__all__ = [
    "DEFAULT_CATALOG_PATH",
    "HOOK_TYPES",
    "RequiredServices",
    "ServiceCatalog",
    "ServiceDefinition",
    "compose_service_names",
    "extract_required_services",
    "load_service_catalog",
    "service_env",
]
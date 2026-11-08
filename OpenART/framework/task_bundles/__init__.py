"""Self-contained Docker Compose bundles for OpenART tasks.

The module turns a task directory (``task.md`` + ``workspace/`` +
``tool_use_graph.json``) into a generated bundle that starts only the services
the task actually uses.
"""

from framework.task_bundles.services import (
    RequiredServices,
    compose_service_names,
    extract_required_services,
    service_env,
)

__all__ = [
    "RequiredServices",
    "compose_service_names",
    "extract_required_services",
    "service_env",
]
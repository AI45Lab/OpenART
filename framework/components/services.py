"""External service descriptors for OpenART framework."""

from __future__ import annotations

import subprocess
import time
import urllib.parse
import urllib.request
from abc import ABC, abstractmethod
from typing import Any, Optional

from framework.models.common import CredentialBundle, Endpoint
from framework.models.specs import TraceEvent
from framework.components.trace import TraceSinkBase


class ServiceBase(ABC):
    """Base class for externally managed service definitions."""

    def __init__(
        self,
        name: str,
        credentials: CredentialBundle,
        trace_sink: Optional[TraceSinkBase] = None,
    ) -> None:
        self.name = name
        self.credentials = credentials
        self.trace_sink = trace_sink
        self.endpoints: dict[str, Endpoint] = {}
        self.endpoint_overrides: dict[str, str] = {}

    def start(self) -> None:
        return

    def stop(self) -> None:
        return

    def reset(self) -> None:
        return

    def seed(self) -> None:
        return

    @abstractmethod
    def is_healthy(self) -> bool:
        ...

    @abstractmethod
    def snapshot(self) -> dict[str, Any]:
        ...

    def get_endpoint(self, name: str) -> Endpoint:
        return self.endpoints[name]

    def register_endpoints(self) -> None:
        return

    def apply_endpoint_overrides(self) -> None:
        for endpoint_name, endpoint_url in self.endpoint_overrides.items():
            existing = self.endpoints.get(endpoint_name)
            metadata = dict(existing.metadata) if existing else {}
            self.endpoints[endpoint_name] = Endpoint(endpoint_name, endpoint_url, metadata=metadata)

    def _trace(self, run_id: str, action: str, status: str, payload: Optional[dict] = None) -> None:
        if not self.trace_sink:
            return

        self.trace_sink.write(
            TraceEvent(
                run_id=run_id,
                source_role="service",
                event_type="service_event",
                timestamp=time.time(),
                message=f"{self.name}:{action}:{status}",
                payload=payload or {},
            )
        )


class ServiceManager:
    """Manager for externally managed services."""

    def __init__(self, services: list[ServiceBase]) -> None:
        self.services = {service.name: service for service in services}
        for service in self.services.values():
            service.apply_endpoint_overrides()

    def start_all(self) -> None:
        for service in self.services.values():
            service.start()
            service.apply_endpoint_overrides()

    def stop_all(self) -> None:
        for service in reversed(list(self.services.values())):
            service.stop()

    def seed_all(self) -> None:
        for service in self.services.values():
            service.seed()

    def reset_all(self) -> None:
        for service in self.services.values():
            service.reset()

    def health_report(self) -> dict[str, bool]:
        return {name: service.is_healthy() for name, service in self.services.items()}

    def endpoint_map(self) -> dict[str, str]:
        result: dict[str, str] = {}
        for service in self.services.values():
            for endpoint_name, endpoint in service.endpoints.items():
                result[f"{service.name}.{endpoint_name}"] = endpoint.url
        return result

    def snapshot_all(self) -> dict[str, dict]:
        snapshots: dict[str, dict] = {}
        for name, service in self.services.items():
            try:
                snapshots[name] = service.snapshot()
            except Exception as exc:
                snapshots[name] = {
                    "mode": "external",
                    "error": str(exc),
                    "endpoints": {endpoint_name: endpoint.url for endpoint_name, endpoint in service.endpoints.items()},
                }
        return snapshots


class ExternalService(ServiceBase):
    """Service implementation for pre-initialized external services."""

    def is_healthy(self) -> bool:
        if not self.endpoints:
            return True

        report = self._health_details()
        return all(item.get("ok") is True for item in report.values())

    def snapshot(self) -> dict[str, Any]:
        report = self._health_details()
        return {
            "mode": "external",
            "endpoints": {name: endpoint.url for name, endpoint in self.endpoints.items()},
            "healthy": all(item.get("ok") is True for item in report.values()) if report else True,
            "health": report,
            "snapshot_time": int(time.time()),
        }

    def _health_details(self) -> dict[str, dict[str, Any]]:
        report: dict[str, dict[str, Any]] = {}
        for endpoint_name, endpoint in self.endpoints.items():
            report[endpoint_name] = self._probe_endpoint(endpoint.url)
        return report

    def _probe_endpoint(self, url: str) -> dict[str, Any]:
        started = time.time()
        try:
            proc = subprocess.run(
                [
                    "curl",
                    "-sS",
                    "-L",
                    "-o",
                    "/dev/null",
                    "-w",
                    "%{http_code}",
                    "--max-time",
                    "5",
                    url,
                ],
                capture_output=True,
                text=True,
                check=False,
            )
            elapsed_ms = int((time.time() - started) * 1000)
            status_text = proc.stdout.strip()
            http_code = int(status_text) if status_text.isdigit() else 0
            ok = proc.returncode == 0 and ((200 <= http_code < 500) or http_code in {0, 401, 403})
            error = ""
            if not ok:
                error = proc.stderr.strip() or f"unexpected http code: {http_code}"
            return {
                "ok": ok,
                "http_code": http_code,
                "latency_ms": elapsed_ms,
                "error": error,
            }
        except FileNotFoundError:
            return self._probe_endpoint_with_urllib(url, started)
        except Exception as exc:
            return {
                "ok": False,
                "http_code": 0,
                "latency_ms": int((time.time() - started) * 1000),
                "error": str(exc),
            }

    def _probe_endpoint_with_urllib(self, url: str, started: float) -> dict[str, Any]:
        parsed = urllib.parse.urlparse(url)
        if parsed.scheme not in {"http", "https"}:
            return {
                "ok": False,
                "http_code": 0,
                "latency_ms": int((time.time() - started) * 1000),
                "error": f"unsupported scheme: {parsed.scheme or 'unknown'}",
            }

        req = urllib.request.Request(url=url, method="GET")
        try:
            with urllib.request.urlopen(req, timeout=5) as response:
                code = int(getattr(response, "status", 200))
            elapsed_ms = int((time.time() - started) * 1000)
            return {
                "ok": 200 <= code < 500,
                "http_code": code,
                "latency_ms": elapsed_ms,
                "error": "",
            }
        except Exception as exc:
            elapsed_ms = int((time.time() - started) * 1000)
            error_code = 0
            if hasattr(exc, "code"):
                try:
                    error_code = int(getattr(exc, "code"))
                except Exception:
                    error_code = 0
            is_reachable_error = error_code in {401, 403, 404}
            return {
                "ok": bool(is_reachable_error),
                "http_code": error_code,
                "latency_ms": elapsed_ms,
                "error": "" if is_reachable_error else str(exc),
            }

__all__ = [
    "ExternalService",
    "ServiceBase",
    "ServiceManager",
]

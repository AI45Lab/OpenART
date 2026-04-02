from __future__ import annotations

from typing import Any

from framework.components.services import ExternalService, ServiceBase, ServiceManager
from framework.models.common import CredentialBundle, Endpoint


class _CounterService(ServiceBase):
    def __init__(self, name: str) -> None:
        super().__init__(name=name, credentials=CredentialBundle(values={}))
        self.start_calls = 0
        self.stop_calls = 0
        self.seed_calls = 0
        self.reset_calls = 0

    def start(self) -> None:
        self.start_calls += 1
        self.endpoints["web"] = Endpoint("web", "http://internal.example")

    def stop(self) -> None:
        self.stop_calls += 1

    def reset(self) -> None:
        self.reset_calls += 1

    def seed(self) -> None:
        self.seed_calls += 1

    def is_healthy(self) -> bool:
        return True

    def snapshot(self) -> dict[str, Any]:
        return {"start_calls": self.start_calls}


class _BrokenSnapshotService(_CounterService):
    def snapshot(self) -> dict[str, Any]:
        raise RuntimeError("snapshot failed")


def test_service_manager_invokes_service_lifecycle_hooks() -> None:
    service = _CounterService("gitlab")
    manager = ServiceManager([service])

    manager.start_all()
    manager.seed_all()
    manager.reset_all()
    manager.stop_all()

    assert service.start_calls == 1
    assert service.seed_calls == 1
    assert service.reset_calls == 1
    assert service.stop_calls == 1


def test_service_manager_applies_endpoint_overrides_after_start() -> None:
    service = _CounterService("gitlab")
    service.endpoint_overrides = {"web": "http://external.example:8929"}
    manager = ServiceManager([service])

    manager.start_all()

    assert service.get_endpoint("web").url == "http://external.example:8929"


def test_service_manager_snapshot_all_handles_snapshot_errors() -> None:
    service = _BrokenSnapshotService("gitlab")
    service.endpoints["web"] = Endpoint("web", "http://external.example:8929")
    manager = ServiceManager([service])

    snapshots = manager.snapshot_all()

    assert snapshots["gitlab"]["mode"] == "external"
    assert "snapshot failed" in snapshots["gitlab"]["error"]
    assert snapshots["gitlab"]["endpoints"]["web"] == "http://external.example:8929"


def test_external_service_snapshot_contains_endpoints(monkeypatch) -> None:
    service = ExternalService("plane", CredentialBundle(values={}))
    service.endpoints["web"] = Endpoint("web", "http://external.example:8091")

    monkeypatch.setattr(
        service,
        "_probe_endpoint",
        lambda _: {"ok": True, "http_code": 200, "latency_ms": 5, "error": ""},
    )

    snapshot = service.snapshot()

    assert service.is_healthy() is True
    assert snapshot["mode"] == "external"
    assert snapshot["endpoints"]["web"] == "http://external.example:8091"
    assert snapshot["health"]["web"]["ok"] is True

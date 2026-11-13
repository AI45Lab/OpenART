from __future__ import annotations

import pytest

from framework.components.runners import RunnerBase
from framework.core.factory import resolve_runner_mode
from framework.models.common import CommandSpec, CredentialBundle


class _FakeContainer:
    class _Spec:
        name = "fake-container"

    spec = _Spec()

    def __init__(self) -> None:
        self.calls: list[str] = []

    def build(self) -> None:
        self.calls.append("build")

    def create(self) -> None:
        self.calls.append("create")

    def start(self) -> None:
        self.calls.append("start")

    def stop(self) -> None:
        self.calls.append("stop")

    def remove(self, force: bool = False) -> None:
        self.calls.append("remove")


class _Runner(RunnerBase):
    def framework_name(self) -> str:
        return "test"

    def make_framework_config(self) -> dict:
        return {}

    def write_framework_config(self, config: dict) -> None:
        return None

    def render_command(self, task_instruction_file: str) -> str:
        return "true"

    def parse_output(self, *args, **kwargs):
        return None


def _make_runner(container: _FakeContainer, *, owns_container: bool) -> _Runner:
    return _Runner(
        name="test",
        role="target",
        container=container,
        command=CommandSpec(template="true"),
        credentials=CredentialBundle(values={}),
        owns_container=owns_container,
    )


def test_runner_mode_defaults_to_sidecar(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("OPENART_RUNNER_MODE", raising=False)
    assert resolve_runner_mode(None, {}) == "sidecar"


def test_runner_mode_target_config(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("OPENART_RUNNER_MODE", raising=False)
    assert resolve_runner_mode(None, {"runner_mode": "in_container"}) == "in_container"


def test_runner_mode_explicit_wins(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("OPENART_RUNNER_MODE", "sidecar")
    assert resolve_runner_mode("in-container", {"runner_mode": "sidecar"}) == "in_container"


def test_runner_mode_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("OPENART_RUNNER_MODE", "IN-CONTAINER")
    assert resolve_runner_mode(None, {}) == "in_container"


def test_runner_mode_rejects_unknown(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("OPENART_RUNNER_MODE", raising=False)
    with pytest.raises(ValueError, match="Unsupported runner_mode"):
        resolve_runner_mode("inside", {})


def test_non_owner_runner_does_not_stop_task_container() -> None:
    container = _FakeContainer()
    runner = _make_runner(container, owns_container=False)
    runner.stop()
    runner.remove()
    assert container.calls == []


def test_owner_runner_stops_and_removes_container() -> None:
    container = _FakeContainer()
    runner = _make_runner(container, owns_container=True)
    runner.stop()
    runner.remove()
    assert container.calls == ["stop", "remove"]
from __future__ import annotations

import json
from pathlib import Path

import framework.components.containers as containers_module
from framework.components.containers import DockerContainer, RunnerContainer
from framework.models.container import ContainerSpec


def _env_file_from_cmd(cmd: list[str]) -> Path:
    assert "--env-file" in cmd
    path = Path(cmd[cmd.index("--env-file") + 1])
    assert path.parent == Path("/tmp")
    assert path.exists()
    return path


def test_create_large_env_uses_env_file_and_does_not_inline_huge_value(monkeypatch) -> None:
    huge_value = "x" * (containers_module._DOCKER_ENV_INLINE_MAX_BYTES + 1)
    container = DockerContainer(
        ContainerSpec(
            name="openart-env-create-test",
            image="alpine:latest",
            env={"OPENART_RUNTIME_ENV": huge_value, "PLAIN": "value=with=equals"},
        )
    )
    calls: list[list[str]] = []
    captured: dict[str, str] = {}

    def fake_run(cmd: list[str]) -> tuple[int, str, str]:
        calls.append(list(cmd))
        if cmd == ["docker", "inspect", "openart-env-create-test"]:
            return 1, "", ""
        if cmd[:2] == ["docker", "create"]:
            env_file = _env_file_from_cmd(cmd)
            captured["path"] = str(env_file)
            captured["content"] = env_file.read_text(encoding="utf-8")
            return 0, "created-container-id\n", ""
        raise AssertionError(f"unexpected docker command: {cmd}")

    monkeypatch.setattr(container, "_run", fake_run)

    container.create()

    create_cmd = calls[-1]
    assert create_cmd[:4] == ["docker", "create", "--name", "openart-env-create-test"]
    assert "-e" not in create_cmd
    assert all(huge_value not in arg for arg in create_cmd)
    assert captured["content"] == f"OPENART_RUNTIME_ENV={huge_value}\nPLAIN=value=with=equals\n"
    assert not Path(captured["path"]).exists()


def test_exec_large_env_uses_env_file_and_preserves_command_order(monkeypatch) -> None:
    huge_value = "y" * (containers_module._DOCKER_ENV_INLINE_MAX_BYTES + 1)
    container = DockerContainer(ContainerSpec(name="openart-env-exec-test", image="alpine:latest"))
    container.container_id = "container-id"
    captured: dict[str, str] = {}

    def fake_run(cmd: list[str]) -> tuple[int, str, str]:
        env_file = _env_file_from_cmd(cmd)
        captured["path"] = str(env_file)
        captured["content"] = env_file.read_text(encoding="utf-8")
        env_file_idx = cmd.index("--env-file")
        assert cmd[:2] == ["docker", "exec"]
        assert cmd[env_file_idx + 2 :] == [
            "container-id",
            "/usr/bin/timeout",
            "--signal=TERM",
            "--kill-after=10s",
            "7s",
            "python3",
            "-c",
            "print('ok')",
        ]
        return 0, "ok\n", ""

    monkeypatch.setattr(container, "_run", fake_run)

    result = container.exec(
        ["python3", "-c", "print('ok')"],
        env={"OPENART_RUNTIME_ENV": huge_value},
        timeout_seconds=7,
    )

    assert result == (0, "ok\n", "")
    assert captured["content"] == f"OPENART_RUNTIME_ENV={huge_value}\n"
    assert not Path(captured["path"]).exists()


def test_exec_medium_single_env_value_uses_env_file(monkeypatch) -> None:
    medium_value = "m" * (containers_module._DOCKER_ENV_INLINE_MAX_ITEM_BYTES + 1)
    container = DockerContainer(ContainerSpec(name="openart-env-medium-test", image="alpine:latest"))
    container.container_id = "container-id"
    captured: dict[str, str] = {}

    def fake_run(cmd: list[str]) -> tuple[int, str, str]:
        env_file = _env_file_from_cmd(cmd)
        captured["path"] = str(env_file)
        captured["content"] = env_file.read_text(encoding="utf-8")
        assert "-e" not in cmd
        assert all(medium_value not in arg for arg in cmd)
        assert cmd[-1] == "true"
        return 0, "", ""

    monkeypatch.setattr(container, "_run", fake_run)

    container.exec(["true"], env={"OPENART_RUNTIME_ENV": medium_value})

    assert captured["content"] == f"OPENART_RUNTIME_ENV={medium_value}\n"
    assert not Path(captured["path"]).exists()


def test_exec_small_env_still_uses_inline_env_args(monkeypatch) -> None:
    container = DockerContainer(ContainerSpec(name="openart-env-small-test", image="alpine:latest"))
    container.container_id = "container-id"
    calls: list[list[str]] = []

    def fake_run(cmd: list[str]) -> tuple[int, str, str]:
        calls.append(list(cmd))
        return 0, "", ""

    monkeypatch.setattr(container, "_run", fake_run)

    container.exec(["env"], env={"FOO": "bar", "BAZ": "qux"})

    assert calls == [["docker", "exec", "-e", "FOO=bar", "-e", "BAZ=qux", "container-id", "env"]]


def test_env_file_content_round_trips_plain_openart_runtime_values(monkeypatch) -> None:
    monkeypatch.setattr(containers_module, "_DOCKER_ENV_INLINE_MAX_BYTES", 1)
    env = {
        "OPENART_RUN_ID": "run-123",
        "OPENART_CONTROL_PLANE_PROBE_PATHS": json.dumps(["/workspace/CLAUDE.md", "/workspace/.codex/skills"]),
        "NO_PROXY": "localhost,127.0.0.1,.svc",
        "OPENAI_BASE_URL": "http://llm.internal/v1",
        "VALUE_WITH_EQUALS": "left=right=tail",
    }
    container = DockerContainer(ContainerSpec(name="openart-env-roundtrip-test", image="alpine:latest"))
    container.container_id = "container-id"
    captured: dict[str, str] = {}

    def fake_run(cmd: list[str]) -> tuple[int, str, str]:
        env_file = _env_file_from_cmd(cmd)
        captured["path"] = str(env_file)
        captured["content"] = env_file.read_text(encoding="utf-8")
        return 0, "", ""

    monkeypatch.setattr(container, "_run", fake_run)

    container.exec(["true"], env=env)

    parsed = {
        line.split("=", 1)[0]: line.split("=", 1)[1]
        for line in captured["content"].splitlines()
    }
    assert parsed == env
    assert not Path(captured["path"]).exists()


def test_write_text_file_streams_content_over_stdin_not_argv(monkeypatch) -> None:
    content = "payload-" + ("z" * (containers_module._DOCKER_ENV_INLINE_MAX_BYTES + 1))
    container = RunnerContainer(ContainerSpec(name="openart-write-stdin-test", image="alpine:latest"))
    container.container_id = "container-id"
    captured: dict[str, object] = {}

    def fake_run_with_input(cmd: list[str], input_data: bytes) -> tuple[int, str, str]:
        captured["cmd"] = list(cmd)
        captured["input_data"] = input_data
        return 0, "", ""

    monkeypatch.setattr(container, "_run_with_input", fake_run_with_input)

    container.write_text_file("/workspace/large.txt", content, env={"FOO": "bar"})

    cmd = captured["cmd"]
    assert isinstance(cmd, list)
    assert cmd[:5] == ["docker", "exec", "-i", "-e", "FOO=bar"]
    assert cmd[5] == "container-id"
    assert cmd[-1] == "/workspace/large.txt"
    assert all(content not in arg for arg in cmd)
    assert captured["input_data"] == content.encode("utf-8")

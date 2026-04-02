from __future__ import annotations

from pathlib import Path

from framework.components.runners import ClaudeCodeRunner, GenericCLIRunner, OpenCodeRunner
from framework.models.common import CommandSpec, CredentialBundle, MCPServerSpec, ToolSpec
from framework.models.container import ContainerSpec


class _FakeRunnerContainer:
    def __init__(self, name: str) -> None:
        self.spec = ContainerSpec(name=name)
        self.files: dict[str, str] = {}
        self.exec_calls: list[list[str]] = []

    def write_text_file(self, path: str, content: str, env=None) -> None:
        self.files[path] = content

    def ensure_dir(self, path: str, env=None) -> None:
        self.files.setdefault(path.rstrip("/") + "/", "")

    def exec(self, cmd: list[str], env=None):
        self.exec_calls.append(list(cmd))
        return 0, "", ""


def test_runner_logs_stdout_stderr_to_runtime_log(tmp_path: Path, capsys) -> None:
    runner = GenericCLIRunner(
        name="runner",
        role="target",
        container=_FakeRunnerContainer("openart-target-test"),
        command=CommandSpec(template="python agent.py"),
        credentials=CredentialBundle(values={}),
        artifact_dir=str(tmp_path),
    )

    runner._handle_run_output("run-1", "hello\nworld\n", "warn\n", 0)

    captured = capsys.readouterr()
    assert captured.err == ""

    runtime_log = (tmp_path / "runtime.log").read_text(encoding="utf-8")
    assert "[openart][target] runner exit_code=0 framework=generic_cli container=openart-target-test" in runtime_log
    assert "[openart][target][stdout] hello" in runtime_log
    assert "[openart][target][stderr] warn" in runtime_log


def test_runner_can_emit_live_stderr_when_enabled(tmp_path: Path, capsys, monkeypatch) -> None:
    monkeypatch.setenv("OPENART_LIVE_STDERR", "1")
    runner = GenericCLIRunner(
        name="runner",
        role="target",
        container=_FakeRunnerContainer("openart-target-test"),
        command=CommandSpec(template="python agent.py"),
        credentials=CredentialBundle(values={}),
        artifact_dir=str(tmp_path),
    )

    runner._handle_run_output("run-1", "hello\n", "warn\n", 0)

    captured = capsys.readouterr()
    assert "[openart][target] runner exit_code=0 framework=generic_cli container=openart-target-test" in captured.err
    assert "[openart][target][stdout] hello" in captured.err
    assert "[openart][target][stderr] warn" in captured.err


def test_opencode_runner_reads_prompt_text_not_file_path() -> None:
    runner = OpenCodeRunner(
        name="runner",
        role="target",
        container=_FakeRunnerContainer("openart-target-test"),
        command=CommandSpec(template='opencode run "{{task_instruction_file}}"'),
        credentials=CredentialBundle(values={}),
    )

    command = runner.render_command("/task/instructions/target.md")

    assert "opencode" in command
    assert "run" in command
    assert "--task" not in command
    assert "/task/instructions/target.md" in command


def test_claude_runner_uses_print_mode_and_reads_prompt_text() -> None:
    runner = ClaudeCodeRunner(
        name="runner",
        role="attack",
        container=_FakeRunnerContainer("openart-attack-test"),
        command=CommandSpec(template='claude --task {{task_instruction_file}}'),
        credentials=CredentialBundle(values={}),
    )

    command = runner.render_command("/task/instructions/attacker.md")

    assert "claude" in command
    assert "-p" in command or "--print" in command
    assert "--task" not in command
    assert "/task/instructions/attacker.md" in command


def test_opencode_runner_builds_custom_openai_compatible_provider_config() -> None:
    runner = OpenCodeRunner(
        name="runner",
        role="target",
        container=_FakeRunnerContainer("openart-target-test"),
        command=CommandSpec(template="opencode run"),
        credentials=CredentialBundle(values={}),
        base_url="http://llm.internal/v1",
        model="glm-5",
    )

    config = runner.make_framework_config()

    assert config["model"] == "openart/glm-5"
    assert config["provider"]["openart"]["npm"] == "@ai-sdk/openai-compatible"
    assert config["provider"]["openart"]["options"]["baseURL"] == "http://llm.internal/v1"
    assert config["provider"]["openart"]["options"]["apiKey"] == "{env:OPENAI_API_KEY}"
    assert config["provider"]["openart"]["models"]["glm-5"]["limit"]["output"] == 8192


def test_opencode_runner_serializes_mcp_servers_in_supported_format() -> None:
    runner = OpenCodeRunner(
        name="runner",
        role="target",
        container=_FakeRunnerContainer("openart-target-test"),
        command=CommandSpec(template="opencode run"),
        credentials=CredentialBundle(values={}),
        mcp_servers=[
            MCPServerSpec(name="filesystem", transport="stdio", command="filesystem", args=["--root", "/workspace"], env={"A": "1"}, enabled=True),
            MCPServerSpec(name="docs", transport="http", url="https://example.com/mcp", enabled=True),
        ],
    )

    config = runner.make_framework_config()

    assert config["mcp"]["filesystem"]["type"] == "local"
    assert config["mcp"]["filesystem"]["command"] == ["filesystem", "--root", "/workspace"]
    assert config["mcp"]["filesystem"]["environment"]["A"] == "1"
    assert config["mcp"]["docs"]["type"] == "remote"
    assert config["mcp"]["docs"]["url"] == "https://example.com/mcp"


def test_runner_installs_user_tool_wrappers_and_guide() -> None:
    container = _FakeRunnerContainer("openart-target-test")
    runner = GenericCLIRunner(
        name="runner",
        role="target",
        container=container,
        command=CommandSpec(template="python agent.py"),
        credentials=CredentialBundle(values={}),
        runtime_env={"OPENAI_API_KEY": "secret"},
        tools=[
            ToolSpec(
                name="gitlab.create_project",
                description="Create a project",
                command="python3",
                args=["script.py"],
                env_from={"TOKEN": "OPENAI_API_KEY"},
                usage="gitlab.create_project demo-project",
            )
        ],
        tool_guide_markdown="# Custom Tool Guide",
    )

    runner._install_tools()

    assert runner.runtime_env["OPENART_TOOLS_FILE"].endswith("tools.json")
    assert runner.runtime_env["OPENART_TOOL_GUIDE_FILE"].endswith("guide.md")
    assert runner.runtime_env["PATH"].startswith("/workspace/.openart/runners/target/state/tools/bin:")
    wrapper_path = "/workspace/.openart/runners/target/state/tools/bin/gitlab.create_project"
    assert "exec python3 script.py \"$@\"" in container.files[wrapper_path]
    assert "export TOKEN=\"${OPENAI_API_KEY:-}\"" in container.files[wrapper_path]
    assert container.files[runner.runtime_env["OPENART_TOOL_GUIDE_FILE"]] == "# Custom Tool Guide\n"

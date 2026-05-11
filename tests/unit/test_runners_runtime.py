from __future__ import annotations

import json
from pathlib import Path

from framework.components.runners import ClaudeCodeRunner, GenericCLIRunner, IFlowRunner, OpenCodeRunner, PromptCLIRunner
from framework.models.common import CommandSpec, CredentialBundle, MCPServerSpec, ToolSpec
from framework.models.container import ContainerSpec


class _FakeRunnerContainer:
    def __init__(self, name: str, default_path: str = "/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin") -> None:
        self.spec = ContainerSpec(name=name)
        self.files: dict[str, str] = {}
        self.exec_calls: list[list[str]] = []
        self.default_path = default_path

    def build(self) -> None:
        return

    def create(self) -> None:
        return

    def start(self) -> None:
        return

    def write_text_file(self, path: str, content: str, env=None) -> None:
        self.files[path] = content

    def ensure_dir(self, path: str, env=None) -> None:
        self.files.setdefault(path.rstrip("/") + "/", "")

    def read_text_file(self, path: str, env=None) -> str:
        if path not in self.files:
            raise FileNotFoundError(path)
        return self.files[path]

    def exec(self, cmd: list[str], env=None):
        self.exec_calls.append(list(cmd))
        if cmd == ["bash", "-lc", 'printf %s "$PATH"']:
            return 0, self.default_path, ""
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
    assert "/workspace/.opencode/skills/" in command
    assert "/workspace/.claude/skills/" in command
    assert "Before carrying out the task, quickly inspect the workspace" in command
    assert "/workspace/.openart/service_preflight.json" in command


def test_opencode_runner_mentions_extra_control_plane_probe_paths() -> None:
    runner = OpenCodeRunner(
        name="runner",
        role="target",
        container=_FakeRunnerContainer("openart-target-test"),
        command=CommandSpec(template="opencode run"),
        credentials=CredentialBundle(values={}),
        runtime_env={"OPENART_CONTROL_PLANE_PROBE_PATHS": json.dumps(["/workspace/GEMINI.md", "/workspace/.gemini/skills/"])},
    )

    command = runner.render_command("/task/instructions/target.md")

    assert "/workspace/GEMINI.md" in command
    assert "/workspace/.gemini/skills/" in command


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


def test_iflow_runner_uses_prompt_mode_and_writes_openai_compatible_settings() -> None:
    runner = IFlowRunner(
        name="runner",
        role="target",
        container=_FakeRunnerContainer("openart-target-test"),
        command=CommandSpec(template="iflow run --task {{task_instruction_file}}"),
        credentials=CredentialBundle(values={"api_key": "dummy"}),
        base_url="http://llm.internal/v1",
        model="glm-5",
    )

    config = runner.make_framework_config()
    command = runner.render_command("/task/instructions/target.md")

    assert config["selectedAuthType"] == "openai-compatible"
    assert config["apiKey"] == "dummy"
    assert config["baseUrl"] == "http://llm.internal/v1"
    assert config["modelName"] == "glm-5"
    assert "exec iflow -p \"$prompt\"" in command
    assert "run --task" not in command


def test_runner_installs_user_model_config_json_and_skips_managed_framework_config() -> None:
    container = _FakeRunnerContainer("openart-target-test")
    source_path = "/workspace/.openart_model_integration_target.json"
    destination_path = "/workspace/.openart/runners/target/home/.iflow/settings.json"
    container.files[source_path] = '{"selectedAuthType": "openai-compatible"}\n'
    runner = IFlowRunner(
        name="runner",
        role="target",
        container=container,
        command=CommandSpec(template="iflow -p"),
        credentials=CredentialBundle(values={}),
        runtime_env={
            "OPENART_MODEL_CONFIG_JSON_SOURCE_FILE": source_path,
            "OPENART_MODEL_CONFIG_JSON_DESTINATION": destination_path,
        },
    )

    runner._install_user_model_config_json()
    runner._install_framework_config()

    assert container.files[destination_path] == '{"selectedAuthType": "openai-compatible"}\n'
    assert container.files[destination_path] != json.dumps(runner.make_framework_config(), indent=2)


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


def test_runner_preserves_container_path_when_installing_tools() -> None:
    container = _FakeRunnerContainer("openart-target-test", default_path="/opt/openart-venv/bin:/usr/local/bin:/usr/bin")
    runner = GenericCLIRunner(
        name="runner",
        role="target",
        container=container,
        command=CommandSpec(template="python agent.py"),
        credentials=CredentialBundle(values={}),
        tools=[
            ToolSpec(
                name="document.extract_pdf_text",
                description="Extract PDF text",
                command="python3",
                args=["extract.py"],
            )
        ],
    )

    runner._install_tools()

    assert runner.runtime_env["PATH"] == "/workspace/.openart/runners/target/state/tools/bin:/opt/openart-venv/bin:/usr/local/bin:/usr/bin"


def test_runner_omits_empty_source_root_from_tools_json() -> None:
    container = _FakeRunnerContainer("openart-target-test")
    runner = GenericCLIRunner(
        name="runner",
        role="target",
        container=container,
        command=CommandSpec(template="python agent.py"),
        credentials=CredentialBundle(values={}),
        tools=[
            ToolSpec(
                name="document.extract_pdf_text",
                description="Extract PDF text",
                command="/opt/openart-venv/bin/python3",
                args=["/opt/openart-tools/scripts/document_extract_pdf_text.py"],
            )
        ],
    )

    runner._install_tools()

    payload = json.loads(container.files[runner.runtime_env["OPENART_TOOLS_FILE"]])
    assert "source_root" not in payload[0]


def test_prompt_cli_runner_argv_transport_uses_prompt_flag() -> None:
    runner = PromptCLIRunner(
        name="runner",
        role="target",
        container=_FakeRunnerContainer("openart-target-test"),
        command=CommandSpec(template="gemini"),
        credentials=CredentialBundle(values={}),
        extra_config={"prompt_transport": "argv", "prompt_flag": "-p"},
    )

    command = runner.render_command("/task/instructions/target.md")

    assert "exec gemini -p \"$prompt\"" in command
    assert "/task/instructions/target.md" in command


def test_prompt_cli_runner_stdin_transport_pipes_prompt() -> None:
    runner = PromptCLIRunner(
        name="runner",
        role="target",
        container=_FakeRunnerContainer("openart-target-test"),
        command=CommandSpec(template="gemini --sandbox"),
        credentials=CredentialBundle(values={}),
        extra_config={"prompt_transport": "stdin"},
    )

    command = runner.render_command("/task/instructions/target.md")

    assert "printf '%s' \"$prompt\" | exec gemini --sandbox" in command
    assert "/task/instructions/target.md" in command

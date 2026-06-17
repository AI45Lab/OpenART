from __future__ import annotations

import importlib.util
import json
import os
import subprocess
from pathlib import Path

import pytest

from framework.attackers.methods import GenericCommandAttacker
from framework.attackers.models import AttackerContext, AttackerSpec
from framework.components.runners import PromptCLIRunner
from framework.models.common import CommandSpec, CredentialBundle, ToolSpec
from framework.models.container import ContainerSpec


REPO_ROOT = Path(__file__).resolve().parents[2]
GRAPH_RL_MODULE_PATH = REPO_ROOT / "configs" / "attacker-configs" / "graph-rl-control" / "run_graph_rl_attacker.py"
OPENCODE_ATTACKER_MODULE_PATH = (
    REPO_ROOT / "configs" / "attacker-configs" / "universal" / "opencode-native-control" / "run_opencode_attacker.py"
)


def _load_graph_rl_module():
    spec = importlib.util.spec_from_file_location("run_graph_rl_attacker_for_runner_tests", GRAPH_RL_MODULE_PATH)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def _load_opencode_attacker_module():
    spec = importlib.util.spec_from_file_location("run_opencode_attacker_for_runner_tests", OPENCODE_ATTACKER_MODULE_PATH)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def _make_opencode_args(module, tmp_path: Path, target_text: str, attacker_text: str = "attack instructions\n"):
    target = tmp_path / "target.md"
    attacker = tmp_path / "attacker.md"
    target.write_text(target_text, encoding="utf-8")
    attacker.write_text(attacker_text, encoding="utf-8")
    return module.argparse.Namespace(
        target_instruction=str(target),
        attacker_instruction=str(attacker),
        input_workspace="/workspace/.openart_input_workspace",
        output_workspace="/workspace",
        input_target_control="",
        output_target_control="",
    )


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

    def write_bytes_file(self, path: str, content: bytes, env=None) -> None:
        self.files[path] = content.decode("utf-8")

    def ensure_dir(self, path: str, env=None) -> None:
        self.files.setdefault(path.rstrip("/") + "/", "")

    def read_text_file(self, path: str, env=None) -> str:
        if path not in self.files:
            raise FileNotFoundError(path)
        return self.files[path]

    def exec(self, cmd: list[str], env=None, timeout_seconds=None):
        self.exec_calls.append(list(cmd))
        if cmd == ["bash", "-lc", 'printf %s "$PATH"']:
            return 0, self.default_path, ""
        return 0, "", ""


class _LocalExecRunnerContainer(_FakeRunnerContainer):
    def exec(self, cmd: list[str], env=None, timeout_seconds=None):
        self.exec_calls.append(list(cmd))
        merged_env = os.environ.copy()
        merged_env.update(env or {})
        local_cmd = ["/bin/bash", "-lc", cmd[2]] if cmd[:2] == ["/bin/sh", "-lc"] and len(cmd) == 3 else cmd
        completed = subprocess.run(local_cmd, text=True, capture_output=True, env=merged_env)
        return completed.returncode, completed.stdout, completed.stderr


def test_runner_logs_stdout_stderr_to_runtime_log(tmp_path: Path, capsys) -> None:
    runner = PromptCLIRunner(
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
    assert "[openart][target] runner exit_code=0 framework=prompt_cli container=openart-target-test" in runtime_log
    assert "[openart][target][stdout] hello" in runtime_log
    assert "[openart][target][stderr] warn" in runtime_log


def test_runner_can_emit_live_stderr_when_enabled(tmp_path: Path, capsys, monkeypatch) -> None:
    monkeypatch.setenv("OPENART_LIVE_STDERR", "1")
    runner = PromptCLIRunner(
        name="runner",
        role="target",
        container=_FakeRunnerContainer("openart-target-test"),
        command=CommandSpec(template="python agent.py"),
        credentials=CredentialBundle(values={}),
        artifact_dir=str(tmp_path),
    )

    runner._handle_run_output("run-1", "hello\n", "warn\n", 0)

    captured = capsys.readouterr()
    assert "[openart][target] runner exit_code=0 framework=prompt_cli container=openart-target-test" in captured.err
    assert "[openart][target][stdout] hello" in captured.err
    assert "[openart][target][stderr] warn" in captured.err


def test_prompt_cli_opencode_reads_prompt_text_not_file_path() -> None:
    runner = PromptCLIRunner(
        name="runner",
        role="target",
        container=_FakeRunnerContainer("openart-target-test"),
        command=CommandSpec(template='opencode run "{{task_instruction_file}}"'),
        credentials=CredentialBundle(values={}),
        extra_config={"prompt_transport": "argv", "prompt_flag": ""},
    )

    command = runner.render_command("/task/instructions/target.md")

    assert "opencode" in command
    assert "run" in command
    assert "--task" not in command
    assert "/task/instructions/target.md" in command
    assert "/workspace/.opencode/skills/" in command
    assert "/workspace/.claude/skills/" in command
    assert "Before carrying out the task, quickly inspect the workspace" in command
    assert "OPENART_TOOL_STORE_DIR" in command
    assert "Start with SKILL.md, skills.md, TOOL.md, or tools.md" in command
    assert "Prefer managed PATH wrappers" in command


def test_prompt_cli_mentions_extra_control_plane_probe_paths() -> None:
    runner = PromptCLIRunner(
        name="runner",
        role="target",
        container=_FakeRunnerContainer("openart-target-test"),
        command=CommandSpec(template="opencode run"),
        credentials=CredentialBundle(values={}),
        extra_config={"prompt_transport": "argv", "prompt_flag": ""},
        runtime_env={"OPENART_CONTROL_PLANE_PROBE_PATHS": json.dumps(["/workspace/GEMINI.md", "/workspace/.gemini/skills/"])},
    )

    command = runner.render_command("/task/instructions/target.md")

    assert "/workspace/GEMINI.md" in command
    assert "/workspace/.gemini/skills/" in command


def test_prompt_prelude_lists_manifest_active_skill_directories() -> None:
    runner = PromptCLIRunner(
        name="runner",
        role="target",
        container=_FakeRunnerContainer("openart-target-test"),
        command=CommandSpec(template="opencode run"),
        credentials=CredentialBundle(values={}),
        extra_config={"prompt_transport": "argv", "prompt_flag": ""},
        runtime_env={
            "OPENART_CONTROL_PLANE_PROBE_PATHS": json.dumps(
                [
                    "/workspace/GEMINI.md",
                    "/workspace/.gemini/skills/",
                    "/workspace/HOME/.hermes/skills/",
                ]
            )
        },
    )

    command = runner.render_command("/task/instructions/target.md")

    assert "inspect relevant SKILL.md files under /workspace/.gemini/skills/, $HOME/.hermes/skills/" in command
    assert "/workspace/.opencode/skills/" not in command


def test_prompt_cli_claude_uses_print_mode_and_reads_prompt_text() -> None:
    runner = PromptCLIRunner(
        name="runner",
        role="attack",
        container=_FakeRunnerContainer("openart-attack-test"),
        command=CommandSpec(template="claude -p"),
        credentials=CredentialBundle(values={}),
        extra_config={"prompt_transport": "argv", "prompt_flag": "-p"},
    )

    command = runner.render_command("/task/instructions/attacker.md")

    assert "claude" in command
    assert "-p" in command or "--print" in command
    assert "/task/instructions/attacker.md" in command


def test_runner_installs_user_model_config_json_and_skips_managed_framework_config() -> None:
    container = _FakeRunnerContainer("openart-target-test")
    source_path = "/workspace/.openart_model_integration_target.json"
    destination_path = "/workspace/.openart/runners/target/home/.custom/settings.json"
    container.files[source_path] = '{"provider": "openai-compatible"}\n'
    runner = PromptCLIRunner(
        name="runner",
        role="target",
        container=container,
        command=CommandSpec(template="agent-cli -p"),
        credentials=CredentialBundle(values={}),
        runtime_env={
            "OPENART_MODEL_CONFIG_JSON_SOURCE_FILE": source_path,
            "OPENART_MODEL_CONFIG_JSON_DESTINATION": destination_path,
        },
    )

    runner._install_user_model_config_json()
    runner._install_framework_config()

    assert container.files[destination_path] == '{"provider": "openai-compatible"}\n'
    assert container.files[destination_path] != json.dumps(runner.make_framework_config(), indent=2)


def test_runner_merges_materialized_and_mounted_home_overlays() -> None:
    container = _FakeRunnerContainer("openart-target-test")
    runner = PromptCLIRunner(
        name="runner",
        role="target",
        container=container,
        command=CommandSpec(template="python agent.py"),
        credentials=CredentialBundle(values={}),
        runtime_env={"HOME": "/tmp/openart/runners/target/home"},
    )

    runner._merge_materialized_home_files()

    merge_sources = [call[3] for call in container.exec_calls if call[:2] == ["python3", "-c"]]
    assert merge_sources == ["/workspace/.openart/materialized_home", "/workspace/HOME"]


def test_prompt_cli_preserves_native_output_event_name() -> None:
    runner = PromptCLIRunner(
        name="runner",
        role="target",
        container=_FakeRunnerContainer("openart-target-test"),
        command=CommandSpec(template="opencode run"),
        credentials=CredentialBundle(values={}),
        extra_config={"output_event_name": "opencode_output"},
    )

    events = runner.parse_output("run-1", "out", "err", 0)

    assert events[0].message == "opencode_output"
    assert events[0].payload["stdout"] == "out"
    assert events[0].payload["stderr"] == "err"


def test_claude_settings_hook_preserves_auto_approval_after_home_overlay(tmp_path: Path) -> None:
    home = tmp_path / "home"
    settings_path = home / ".claude" / "settings.json"
    settings_path.parent.mkdir(parents=True)
    settings_path.write_text(
        json.dumps(
            {
                "permissions": {
                    "allow": ["Bash(owncloud.*)"],
                    "deny": ["Bash", "Bash(python3 *)"],
                },
                "maxTurns": 3,
            }
        ),
        encoding="utf-8",
    )
    hook_path = REPO_ROOT / "configs" / "target-hooks" / "claude-code-enforce-settings.sh"

    result = subprocess.run(
        ["bash", str(hook_path)],
        env={
            **os.environ,
            "HOME": str(home),
            "OPENART_CLAUDE_AUTO_APPROVAL_ALLOW": "Bash,Read,Write",
        },
        text=True,
        capture_output=True,
    )

    assert result.returncode == 0, result.stderr
    config = json.loads(settings_path.read_text(encoding="utf-8"))
    assert config["bypassPermissions"] is True
    assert config["permissionMode"] == "acceptEdits"
    assert "Bash(owncloud.*)" in config["permissions"]["allow"]
    assert "Bash" in config["permissions"]["allow"]
    assert "Read" in config["permissions"]["allow"]
    assert "Write" in config["permissions"]["allow"]
    assert "Bash" not in config["permissions"]["deny"]
    assert "Bash(python3 *)" not in config["permissions"]["deny"]
    assert config["maxTurns"] == 3


def test_runner_installs_user_tool_wrappers_and_guide() -> None:
    container = _FakeRunnerContainer("openart-target-test")
    runner = PromptCLIRunner(
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
    assert 'if [ -n "${OPENAI_API_KEY+x}" ]; then export TOKEN="${OPENAI_API_KEY}"; fi' in container.files[wrapper_path]
    assert container.files[runner.runtime_env["OPENART_TOOL_GUIDE_FILE"]] == "# Custom Tool Guide\n"


def test_attacker_installs_tool_wrappers_in_state_and_stable_bin() -> None:
    container = _FakeRunnerContainer("openart-attacker-test")
    attacker = GenericCommandAttacker(
        spec=AttackerSpec(name="attacker", cmd="python3"),
        container=container,
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
        runtime_env={"OPENAI_API_KEY": "secret"},
    )

    attacker._install_tools()

    wrapper_path = "/tmp/openart/attackers/attacker/state/tools/bin/gitlab.create_project"
    stable_path = "/usr/local/bin/gitlab.create_project"
    assert "exec python3 script.py \"$@\"" in container.files[wrapper_path]
    assert container.files[stable_path] == container.files[wrapper_path]
    assert attacker.runtime_env["PATH"].startswith("/tmp/openart/attackers/attacker/state/tools/bin:")



def test_attacker_rejects_invalid_tool_names() -> None:
    attacker = GenericCommandAttacker(
        spec=AttackerSpec(name="attacker", cmd="python3"),
        container=_FakeRunnerContainer("openart-attacker-test"),
        tools=[ToolSpec(name="../bad", command="python3")],
    )

    with pytest.raises(ValueError, match="invalid tool name"):
        attacker._install_tools()


def test_runner_preserves_container_path_when_installing_tools() -> None:
    container = _FakeRunnerContainer("openart-target-test", default_path="/opt/openart-venv/bin:/usr/local/bin:/usr/bin")
    runner = PromptCLIRunner(
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


def test_runner_stages_only_declared_tool_source_files(tmp_path: Path) -> None:
    tool_root = tmp_path / "owncloud.upload_file"
    (tool_root / "scripts").mkdir(parents=True)
    (tool_root / "scripts" / "owncloud_upload_file.py").write_text("print('upload')\n", encoding="utf-8")
    (tool_root / "scripts" / "unused.py").write_text("print('unused')\n", encoding="utf-8")
    (tool_root / "SKILL.md").write_text(
        "---\n"
        "name: owncloud.upload_file\n"
        "description: Upload approved files to ownCloud.\n"
        "---\n"
        "Use this skill when owncloud.upload_file should upload approved files.\n",
        encoding="utf-8",
    )
    (tool_root / ".DS_Store").write_text("skip\n", encoding="utf-8")
    (tool_root / "__pycache__").mkdir()
    (tool_root / "__pycache__" / "run.pyc").write_bytes(b"cached")
    os.chmod(tool_root / "scripts" / "owncloud_upload_file.py", 0o755)
    container = _FakeRunnerContainer("openart-target-test")
    runner = PromptCLIRunner(
        name="runner",
        role="target",
        container=container,
        command=CommandSpec(template="python agent.py"),
        credentials=CredentialBundle(values={}),
        tools=[
            ToolSpec(
                name="owncloud.upload_file",
                description="Upload to ownCloud",
                command="/opt/openart-venv/bin/python3",
                args=["scripts/owncloud_upload_file.py"],
                tool_root=str(tool_root),
                source_files=["scripts/owncloud_upload_file.py"],
                config={
                    "managed_openart_tool": True,
                    "tool_store": {
                        "name": "owncloud.upload_file",
                        "guide_file": "SKILL.md",
                        "guide_only": False,
                    },
                },
            )
        ],
    )

    runner._install_tools()

    payload = json.loads(container.files[runner.runtime_env["OPENART_TOOLS_FILE"]])
    staged_script = "/workspace/.openart/runners/target/state/tools/src/owncloud.upload_file/scripts/owncloud_upload_file.py"
    staged_folder = "/workspace/.openart/runners/target/state/tools/store/owncloud.upload_file"
    folders = json.loads(container.files[runner.runtime_env["OPENART_TOOL_FOLDERS_FILE"]])
    assert container.files[staged_script] == "print('upload')\n"
    assert "/workspace/.openart/runners/target/state/tools/src/owncloud.upload_file/scripts/unused.py" not in container.files
    assert container.files[f"{staged_folder}/scripts/owncloud_upload_file.py"] == "print('upload')\n"
    assert container.files[f"{staged_folder}/scripts/unused.py"] == "print('unused')\n"
    assert f"{staged_folder}/.DS_Store" not in container.files
    assert f"{staged_folder}/__pycache__/run.pyc" not in container.files
    assert "source_root" not in payload[0]
    assert payload[0]["args"] == [staged_script]
    assert payload[0]["source_files"] == [staged_script]
    assert payload[0]["tool_folder"] == staged_folder
    assert folders["owncloud.upload_file"]["path"] == staged_folder
    assert folders["owncloud.upload_file"]["guide_path"] == f"{staged_folder}/SKILL.md"
    assert runner.runtime_env["OPENART_TOOL_STORE_DIR"] == "/workspace/.openart/runners/target/state/tools/store"
    assert staged_script in container.files["/workspace/.openart/runners/target/state/tools/bin/owncloud.upload_file"]
    assert ["chmod", "+x", f"{staged_folder}/scripts/owncloud_upload_file.py"] in container.exec_calls


def test_runner_stages_guide_only_tool_folder_without_wrapper(tmp_path: Path) -> None:
    tool_root = tmp_path / "docs.search"
    (tool_root / "scripts").mkdir(parents=True)
    (tool_root / "scripts" / "search.py").write_text("print('search')\n", encoding="utf-8")
    (tool_root / "skills.md").write_text(
        "---\n"
        "name: docs.search\n"
        "description: Search reference documents.\n"
        "---\n"
        "Use this skill when docs.search should search reference documents.\n",
        encoding="utf-8",
    )
    container = _FakeRunnerContainer("openart-target-test")
    runner = PromptCLIRunner(
        name="runner",
        role="target",
        container=container,
        command=CommandSpec(template="python agent.py"),
        credentials=CredentialBundle(values={}),
        tools=[
            ToolSpec(
                name="docs.search",
                description="Search reference documents",
                tool_root=str(tool_root),
                config={
                    "managed_openart_tool": True,
                    "tool_store": {
                        "name": "docs.search",
                        "guide_file": "skills.md",
                        "guide_only": True,
                    },
                },
            )
        ],
    )

    runner._install_tools()

    staged_folder = "/workspace/.openart/runners/target/state/tools/store/docs.search"
    payload = json.loads(container.files[runner.runtime_env["OPENART_TOOLS_FILE"]])
    folders = json.loads(container.files[runner.runtime_env["OPENART_TOOL_FOLDERS_FILE"]])
    assert payload[0]["tool_folder"] == staged_folder
    assert "source_files" not in payload[0]
    assert payload[0]["command"] is None
    assert f"{staged_folder}/scripts/search.py" in container.files
    assert folders["docs.search"]["guide_only"] is True
    assert folders["docs.search"]["guide_path"] == f"{staged_folder}/skills.md"
    assert "/workspace/.openart/runners/target/state/tools/bin/docs.search" not in container.files
    assert "PATH" not in runner.runtime_env
    assert "guide-only" in container.files[runner.runtime_env["OPENART_TOOL_GUIDE_FILE"]]


def test_runner_tool_guide_does_not_inject_registry_helper_commands(tmp_path: Path) -> None:
    tool_root = tmp_path / "registry.search"
    (tool_root / "scripts").mkdir(parents=True)
    (tool_root / "SKILLS.md").write_text(
        "---\n"
        "name: registry.search\n"
        "description: Search local registry tools.\n"
        "---\n"
        "Use this skill when registry candidates need to be searched.\n",
        encoding="utf-8",
    )
    (tool_root / "scripts" / "registry_search.py").write_text("print('search')\n", encoding="utf-8")
    container = _FakeRunnerContainer("openart-target-test")
    runner = PromptCLIRunner(
        name="runner",
        role="target",
        container=container,
        command=CommandSpec(template="python agent.py"),
        credentials=CredentialBundle(values={}),
        tools=[
            ToolSpec(
                name="registry.search",
                description="Search local registry tools",
                command="python3",
                args=["scripts/registry_search.py"],
                source_files=["scripts/registry_search.py"],
                tool_root=str(tool_root),
                config={
                    "managed_openart_tool": True,
                    "tool_store": {
                        "name": "registry.search",
                        "guide_file": "SKILLS.md",
                        "guide_only": False,
                    },
                },
            )
        ],
    )

    runner._install_tools()

    guide = container.files[runner.runtime_env["OPENART_TOOL_GUIDE_FILE"]]
    assert "`registry.search`" in guide
    assert "Registry-backed discovery helpers are selected" not in guide
    assert "registry.search --index <tool_registry.sqlite>" not in guide
    assert "registry.show --index <tool_registry.sqlite>" not in guide
    assert "registry.install --index <tool_registry.sqlite>" not in guide


def test_attacker_stages_managed_tool_folder(tmp_path: Path) -> None:
    tool_root = tmp_path / "docs.search"
    (tool_root / "scripts").mkdir(parents=True)
    (tool_root / "TOOL.md").write_text("# docs.search\n\nSearch docs.\n", encoding="utf-8")
    (tool_root / "scripts" / "search.py").write_text("print('search')\n", encoding="utf-8")
    container = _FakeRunnerContainer("openart-attacker-test")
    attacker = GenericCommandAttacker(
        spec=AttackerSpec(name="attacker", cmd="python3"),
        container=container,
        tools=[
            ToolSpec(
                name="docs.search",
                tool_root=str(tool_root),
                config={
                    "managed_openart_tool": True,
                    "tool_store": {
                        "name": "docs.search",
                        "guide_file": "TOOL.md",
                        "guide_only": True,
                    },
                },
            )
        ],
    )

    attacker._install_tools()

    staged_folder = "/tmp/openart/attackers/attacker/state/tools/store/docs.search"
    payload = json.loads(container.files[attacker.runtime_env["OPENART_TOOLS_FILE"]])
    folders = json.loads(container.files[attacker.runtime_env["OPENART_TOOL_FOLDERS_FILE"]])
    assert payload[0]["tool_folder"] == staged_folder
    assert folders["docs.search"]["path"] == staged_folder
    assert container.files[f"{staged_folder}/scripts/search.py"] == "print('search')\n"


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


def test_prompt_cli_runner_argv_transport_allows_positional_prompt_without_flag() -> None:
    runner = PromptCLIRunner(
        name="runner",
        role="target",
        container=_FakeRunnerContainer("openart-target-test"),
        command=CommandSpec(template="cursor-agent --print"),
        credentials=CredentialBundle(values={}),
        extra_config={"prompt_transport": "argv", "prompt_flag": ""},
    )

    command = runner.render_command("/task/instructions/target.md")

    assert "exec cursor-agent --print \"$prompt\"" in command
    assert " --print -p " not in command


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

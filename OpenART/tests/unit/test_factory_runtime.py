from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

from framework.attackers.models import AttackerSpec
from framework.components.evaluators import DeterministicEvaluator, LLMJudgeEvaluator
from framework.core.orchestrator import Orchestrator
from framework.core.factory import DEFAULT_COMMAND_TEMPLATES, DEFAULT_RUNNER_IMAGES, MIN_TARGET_TIMEOUT_SECONDS, OrchestratorFactory
from framework.core.workspace import WorkspaceManager
from framework.models.task import TaskBundleSpec


def _make_bundle(
    tmp_path: Path,
    required_services: list[str] | None = None,
    attacker: AttackerSpec | None = None,
) -> TaskBundleSpec:
    task_root = tmp_path / "task"
    task_root.mkdir(parents=True, exist_ok=True)
    (task_root / "task.md").write_text("task\n", encoding="utf-8")
    (task_root / "attacker.md").write_text("attack\n", encoding="utf-8")
    utils_dir = task_root / "utils"
    utils_dir.mkdir(parents=True, exist_ok=True)
    (utils_dir / "evaluator.py").write_text(
        "def evaluate(**kwargs):\n    return {'decision': 'pass', 'score': 1.0}\n",
        encoding="utf-8",
    )

    return TaskBundleSpec(
        task_id="task-001",
        name="Task",
        root_dir=str(task_root),
        target_instruction="task.md",
        attacker=attacker,
        required_services=required_services or [],
        deterministic_eval="utils/evaluator.py",
    )


def _surface_target_config(surface_family: str = "opencode") -> dict:
    return {
        "framework": "prompt_cli",
        "surface_family": surface_family,
        "attack_surfaces": [
            {
                "vector": "claude_md",
                "kind": "instruction",
                "path_template": "CLAUDE.md",
                "description": "Target-native instruction file.",
            }
        ],
    }


def test_factory_passes_harness_and_env_to_deterministic_evaluator(tmp_path: Path) -> None:
    bundle = _make_bundle(tmp_path)
    factory = OrchestratorFactory(
        bundle=bundle,
        output_dir=str(tmp_path / "out"),
        run_id="run-1",
        evaluator_harness="/tmp/oas_harness",
        evaluator_env={"TAC_TEST_MODE": "1"},
        managed_tool_env={"GITLAB_ACCESS_TOKEN": "gitlab-secret"},
    )

    task_container = factory._create_task_container()
    evaluator = factory._create_evaluator(task_container)

    assert isinstance(evaluator, DeterministicEvaluator)
    assert evaluator.harness_path == "/tmp/oas_harness"
    assert evaluator.runtime_env["TAC_TEST_MODE"] == "1"
    assert evaluator.runtime_env["GITLAB_ACCESS_TOKEN"] == "gitlab-secret"


def test_factory_runtime_env_uses_managed_tool_env_and_proxy(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setenv("NO_PROXY", "example.internal")
    bundle = _make_bundle(tmp_path)
    factory = OrchestratorFactory(
        bundle=bundle,
        output_dir=str(tmp_path / "out"),
        run_id="run-1",
        managed_tool_env={"OWNCLOUD_URL": "http://owncloud.example:8092"},
    )

    runtime_env = factory._runtime_env()

    assert runtime_env["OWNCLOUD_URL"] == "http://owncloud.example:8092"
    assert runtime_env["NO_PROXY"] == "example.internal"


def test_factory_defaults_judge_model_to_deepseek_v4_pro(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setenv("OPENAI_MODEL", "glm-5.2")
    monkeypatch.setenv("DEFAULT_MODEL", "glm-5.2")
    monkeypatch.setenv("JUDGE_API_KEY", "judge-secret")
    monkeypatch.setenv("JUDGE_BASE_URL", "http://judge.local/v1")
    monkeypatch.delenv("JUDGE_MODEL", raising=False)

    bundle = _make_bundle(tmp_path)
    judge_rubric = Path(bundle.root_dir) / "checkpoints.md"
    judge_rubric.write_text("judge rubric\n", encoding="utf-8")
    bundle.judge_rubric = "checkpoints.md"

    factory = OrchestratorFactory(
        bundle=bundle,
        output_dir=str(tmp_path / "out"),
        run_id="run-1",
        eval_strategy="llm",
    )

    evaluator = factory._create_evaluator(factory._create_task_container())

    assert isinstance(evaluator, LLMJudgeEvaluator)
    assert evaluator.judge_model == "deepseek-v4-pro"


def test_factory_applies_default_docker_network_to_all_containers(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setenv("OPENART_DOCKER_NETWORK", "host")
    bundle = _make_bundle(
        tmp_path,
        attacker=AttackerSpec(
            name="setup-attacker",
            instruction="attacker.md",
            image="python:3.11-slim",
            cmd="python3",
            args=["{{attacker_instruction_file}}"],
        ),
    )
    factory = OrchestratorFactory(
        bundle=bundle,
        output_dir=str(tmp_path / "out"),
        run_id="run-1",
        target_config={"framework": "prompt_cli"},
    )
    factory._workspace_manager.ensure_run_layout("run-1")
    factory._workspace_path = str(factory._workspace_manager.shared_dir("run-1"))

    task_container = factory._create_task_container()
    runner = factory._create_runner("target")
    attacker, _context = factory._create_attacker()

    assert task_container.spec.network == "host"
    assert runner.container.spec.network == "host"
    assert attacker is not None
    assert attacker.container.spec.network == "host"


def test_factory_container_network_overrides_default_by_role(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setenv("OPENART_DOCKER_NETWORK", "host")
    monkeypatch.setenv("OPENART_TASK_DOCKER_NETWORK", "task-net")
    monkeypatch.setenv("OPENART_RUNNER_DOCKER_NETWORK", "runner-net")
    monkeypatch.setenv("OPENART_ATTACKER_DOCKER_NETWORK", "attacker-net")
    bundle = _make_bundle(
        tmp_path,
        attacker=AttackerSpec(
            name="setup-attacker",
            instruction="attacker.md",
            image="python:3.11-slim",
            cmd="python3",
            args=["{{attacker_instruction_file}}"],
        ),
    )
    factory = OrchestratorFactory(
        bundle=bundle,
        output_dir=str(tmp_path / "out"),
        run_id="run-1",
        target_config={"framework": "prompt_cli", "network": "target-config-net"},
    )
    factory._workspace_manager.ensure_run_layout("run-1")
    factory._workspace_path = str(factory._workspace_manager.shared_dir("run-1"))

    task_container = factory._create_task_container()
    runner = factory._create_runner("target")
    attacker, _context = factory._create_attacker()

    assert task_container.spec.network == "task-net"
    assert runner.container.spec.network == "target-config-net"
    assert attacker is not None
    assert attacker.container.spec.network == "attacker-net"


def test_factory_runner_framework_override_uses_matching_defaults(tmp_path: Path) -> None:
    bundle = _make_bundle(tmp_path)
    factory = OrchestratorFactory(
        bundle=bundle,
        output_dir=str(tmp_path / "out"),
        run_id="run-1",
        runner_framework="prompt_cli",
        target_config={
            "framework": "nanobot",
            "runner_image": "openart/nanobot:latest",
            "launch_cmd": "nanobot agent {{task_instruction_file}}",
        },
    )
    factory._workspace_path = str(tmp_path / "out" / "workspace")

    runner = factory._create_runner("target")

    assert runner.framework_name() == "prompt_cli"
    assert runner.container.spec.image == DEFAULT_RUNNER_IMAGES["prompt_cli"]
    assert runner.command.template == DEFAULT_COMMAND_TEMPLATES["prompt_cli"]


def test_factory_creates_attacker_with_separate_workspace(monkeypatch, tmp_path: Path) -> None:
    bundle = _make_bundle(
        tmp_path,
        attacker=AttackerSpec(
            name="setup-attacker",
            instruction="/attacker_config/attacker.md",
            image="python:3.11-slim",
            cmd="python3",
            args=["{{attacker_instruction_file}}", "{{input_workspace_dir}}", "{{output_workspace_dir}}"],
            target_control_plane=True,
            feedback_loop=True,
            vector_permissions=["workspace_files", "claude_md"],
            env_from={"OPENAI_BASE_URL": "OPENAI_BASE_URL"},
        ),
    )
    attacker_config_dir = tmp_path / "attacker-config"
    attacker_config_dir.mkdir(parents=True, exist_ok=True)
    (attacker_config_dir / "attacker.md").write_text("attack\n", encoding="utf-8")
    bundle.metadata["attacker_config"] = str(attacker_config_dir / "config.yaml")
    monkeypatch.setenv("OPENAI_BASE_URL", "http://attack-llm.internal/v1")
    factory = OrchestratorFactory(
        bundle=bundle,
        output_dir=str(tmp_path / "out"),
        run_id="run-1",
        target_config=_surface_target_config("claude_code"),
    )
    factory._workspace_manager.ensure_run_layout("run-1")
    factory._workspace_path = str(factory._workspace_manager.shared_dir("run-1"))

    attacker, context = factory._create_attacker()

    assert attacker is not None
    assert context is not None
    assert attacker.runtime_env["OPENAI_BASE_URL"] == "http://attack-llm.internal/v1"
    assert context.target_instruction_file == "/task/task.md"
    assert context.attacker_instruction_file == "/attacker_config/attacker.md"
    mounts = {mount.container_path: mount.host_path for mount in attacker.container.spec.mounts}
    assert mounts["/workspace/.openart_input_workspace"].endswith("workspace/attackers/setup-attacker/_live/before_target/.openart_input_workspace")
    assert "/workspace/attackers/setup-attacker/_live/before_target" in mounts["/workspace"]
    assert mounts["/workspace/.openart_feedback"].endswith("workspace/attackers/setup-attacker/_live/before_target/.openart_feedback")
    assert mounts["/attacker_config"].endswith("attacker-config")
    assert mounts["/workspace/.openart_target_control_input"].endswith("workspace/attackers/setup-attacker/_live/before_target/.openart_target_control_input")
    assert mounts["/workspace/.openart_target_control_output"].endswith("workspace/attackers/setup-attacker/_live/before_target/.openart_target_control_output")
    assert context.input_workspace_dir == "/workspace/.openart_input_workspace"
    assert context.input_target_control_dir == "/workspace/.openart_target_control_input"
    assert context.output_target_control_dir == "/workspace/.openart_target_control_output"
    assert context.feedback_dir == "/workspace/.openart_feedback"
    assert context.trace_file == "/workspace/.openart_feedback/trace.jsonl"
    assert context.evaluator_inputs_dir == "/workspace/.openart_feedback/evaluator_inputs"
    assert context.evaluator_outputs_dir == "/workspace/.openart_feedback/evaluator_outputs"
    assert context.target_runner_outputs_dir == "/workspace/.openart_feedback/runner_outputs/target"
    assert context.attacker_history_dir == "/workspace/.openart_feedback/attacker_outputs/setup-attacker"
    assert context.vector_permissions == ("workspace_files", "claude_md")
    assert json.loads(attacker.runtime_env["OPENART_ATTACKER_VECTOR_PERMISSIONS"]) == ["workspace_files", "claude_md"]
    assert attacker.runtime_env["OPENART_FEEDBACK_DIR"] == "/workspace/.openart_feedback"
    assert attacker.runtime_env["OPENART_ATTACKER_HISTORY_DIR"] == "/workspace/.openart_feedback/attacker_outputs/setup-attacker"
    assert attacker.runtime_env["OPENART_ATTACKER_GUIDANCE_FILE"] == "/workspace/.openart_feedback/attacker_feedback_guidance.json"
    assert attacker.runtime_env["OPENART_TARGET_CONTROL_MANIFEST_FILE"] == "/workspace/.openart_feedback/control/target/base/.openart-target-control-manifest.json"


def test_task_rewrite_is_staged_under_run_dir_for_dind_mounts(tmp_path: Path) -> None:
    run_dir = tmp_path / "out" / "run-1"
    run_dir.mkdir(parents=True)
    workspace_manager = WorkspaceManager(str(run_dir / "workspace"))
    workspace_manager.ensure_run_layout("run-1")
    rewrite = workspace_manager.shared_dir("run-1") / ".openart_task_rewrite.md"
    rewrite.write_text("rewritten task\n", encoding="utf-8")
    target_container = SimpleNamespace(spec=SimpleNamespace(mounts=[]))
    target_runner = SimpleNamespace(container=target_container, timing=None)

    orchestrator = Orchestrator(
        target_runner=target_runner,
        attacker=None,
        attacker_context=None,
        evaluator=SimpleNamespace(),
        task_container=SimpleNamespace(),
        workspace_manager=workspace_manager,
        control_manager=SimpleNamespace(),
        max_iterations=1,
        adaptive_iterations=False,
        trace_sink=SimpleNamespace(),
        trace_file=str(run_dir / "trace.jsonl"),
    )

    orchestrator._stage_task_rewrite("run-1")

    staged = run_dir / "task_rewrites" / "run-1_task.md"
    assert staged.read_text(encoding="utf-8") == "rewritten task\n"
    assert not rewrite.exists()
    assert target_container.spec.mounts[-1].host_path == str(staged)
    assert target_container.spec.mounts[-1].container_path == "/task/task.md"


def test_factory_increases_target_timeout_floor(tmp_path: Path) -> None:
    bundle = _make_bundle(tmp_path)
    factory = OrchestratorFactory(
        bundle=bundle,
        output_dir=str(tmp_path / "out"),
        run_id="run-1",
    )
    factory._workspace_path = str(tmp_path / "out" / "workspace")

    runner = factory._create_runner("target")

    assert runner.command.timeout_seconds == MIN_TARGET_TIMEOUT_SECONDS


def test_factory_unknown_runner_framework_raises(tmp_path: Path) -> None:
    bundle = _make_bundle(tmp_path)
    factory = OrchestratorFactory(
        bundle=bundle,
        output_dir=str(tmp_path / "out"),
        run_id="run-1",
        runner_framework="nonexistent_framework",
    )
    factory._workspace_path = str(tmp_path / "out" / "workspace")

    try:
        factory._create_runner("target")
    except ValueError as exc:
        assert "Unsupported runner framework" in str(exc)
        assert "nonexistent_framework" in str(exc)
    else:
        raise AssertionError("expected ValueError for unknown runner framework")


def test_factory_prompt_cli_uses_defaults(tmp_path: Path) -> None:
    bundle = _make_bundle(tmp_path)
    factory = OrchestratorFactory(
        bundle=bundle,
        output_dir=str(tmp_path / "out"),
        run_id="run-1",
        runner_framework="prompt_cli",
    )
    factory._workspace_path = str(tmp_path / "out" / "workspace")

    runner = factory._create_runner("target")

    assert runner.framework_name() == "prompt_cli"
    assert runner.container.spec.image == DEFAULT_RUNNER_IMAGES["prompt_cli"]
    assert runner.command.template == DEFAULT_COMMAND_TEMPLATES["prompt_cli"]


def test_factory_runner_override_does_not_change_target_surface_family(tmp_path: Path) -> None:
    bundle = _make_bundle(tmp_path)
    factory = OrchestratorFactory(
        bundle=bundle,
        output_dir=str(tmp_path / "out"),
        run_id="run-1",
        runner_framework="prompt_cli",
        target_config=_surface_target_config("opencode") | {
            "runner_image": "openart/opencode:latest",
            "launch_cmd": "opencode run",
        },
    )

    assert factory._target_framework == "prompt_cli"
    assert factory._control_manager.provider is not None
    assert factory._control_manager.provider.framework == "opencode"


def test_factory_rejects_legacy_control_plane_key(tmp_path: Path) -> None:
    bundle = _make_bundle(tmp_path)

    try:
        OrchestratorFactory(
            bundle=bundle,
            output_dir=str(tmp_path / "out"),
            run_id="run-1",
            target_config={"framework": "prompt_cli", "control_plane": "opencode"},
        )
    except ValueError as exc:
        assert "legacy target surface config keys" in str(exc)
        assert "control_plane" in str(exc)
        assert "target.attack_surfaces" in str(exc)
    else:
        raise AssertionError("expected ValueError for legacy target.control_plane")


def test_factory_rejects_legacy_control_plane_mount_mode_key(tmp_path: Path) -> None:
    bundle = _make_bundle(tmp_path)

    try:
        OrchestratorFactory(
            bundle=bundle,
            output_dir=str(tmp_path / "out"),
            run_id="run-1",
            target_config={"framework": "prompt_cli", "control_plane_mount_mode": "mounted"},
        )
    except ValueError as exc:
        assert "legacy target surface config keys" in str(exc)
        assert "control_plane_mount_mode" in str(exc)
        assert "target_surface_mount_mode" not in str(exc)
        assert "workspace materialization" in str(exc)
    else:
        raise AssertionError("expected ValueError for legacy target.control_plane_mount_mode")


def test_factory_rejects_target_surface_mount_mode(tmp_path: Path) -> None:
    bundle = _make_bundle(tmp_path)

    try:
        OrchestratorFactory(
            bundle=bundle,
            output_dir=str(tmp_path / "out"),
            run_id="run-1",
            target_config={"framework": "prompt_cli", "target_surface_mount_mode": "mounted"},
        )
    except ValueError as exc:
        assert "target_surface_mount_mode" in str(exc)
        assert "Mounted target-control delivery was removed" in str(exc)
        assert "always materialized to the workspace" in str(exc)
    else:
        raise AssertionError("expected ValueError for obsolete target.target_surface_mount_mode")


def test_factory_rejects_legacy_target_model_fields(tmp_path: Path) -> None:
    bundle = _make_bundle(tmp_path)
    factory = OrchestratorFactory(
        bundle=bundle,
        output_dir=str(tmp_path / "out"),
        run_id="run-1",
        target_config={
            "framework": "prompt_cli",
            "model": "glm-5",
            "base_url": "http://llm.internal/v1",
            "api_key": "dummy",
        },
    )
    factory._workspace_path = str(tmp_path / "out" / "workspace")

    try:
        factory._create_runner("target")
    except ValueError as exc:
        assert "legacy target model fields" in str(exc)
        assert "model" in str(exc)
        assert "base_url" in str(exc)
        assert "api_key" in str(exc)
    else:
        raise AssertionError("expected ValueError for legacy target model fields")


def test_factory_resolves_env_placeholders_in_launch_command(monkeypatch, tmp_path: Path) -> None:
    bundle = _make_bundle(tmp_path)
    monkeypatch.setenv("TARGET_MODEL", "glm-5")
    factory = OrchestratorFactory(
        bundle=bundle,
        output_dir=str(tmp_path / "out"),
        run_id="run-1",
        target_config={
            "framework": "prompt_cli",
            "runner_image": "openart/claude-code:latest",
            "launch_cmd": "claude -p --model ${TARGET_MODEL}",
        },
    )
    factory._workspace_path = str(tmp_path / "out" / "workspace")

    runner = factory._create_runner("target")

    assert runner.command.template == "claude -p --model glm-5"


def test_factory_keeps_prompt_cli_home_outside_shared_workspace(tmp_path: Path) -> None:
    bundle = _make_bundle(tmp_path)
    factory = OrchestratorFactory(
        bundle=bundle,
        output_dir=str(tmp_path / "out"),
        run_id="run-1",
        target_config={"framework": "prompt_cli"},
    )
    factory._workspace_path = str(tmp_path / "out" / "workspace")

    runner = factory._create_runner("target")

    assert runner.runtime_env["HOME"] == "/tmp/openart/runners/target/home"
    assert runner.runtime_env["OPENART_RUNNER_STATE_DIR"] == "/workspace/.openart/runners/target/state"


def test_factory_stages_repo_pre_run_hook_for_prompt_cli_target(tmp_path: Path) -> None:
    bundle = _make_bundle(tmp_path)
    factory = OrchestratorFactory(
        bundle=bundle,
        output_dir=str(tmp_path / "out"),
        run_id="run-1",
        target_config={
            "framework": "prompt_cli",
            "runner_image": "openart/claude-code:latest",
            "launch_cmd": "claude -p",
            "pre_run_hook": "repo:configs/target-hooks/claude-code-enforce-settings.sh",
        },
    )
    factory._workspace_manager.ensure_run_layout("run-1")
    factory._workspace_path = str(factory._workspace_manager.shared_dir("run-1"))

    runner = factory._create_runner("target")

    assert runner.runtime_env["OPENART_PRE_RUN_HOOK"] == (
        "bash /workspace/.openart/runners/target/hooks/claude-code-enforce-settings.sh"
    )
    staged_hook = (
        Path(factory._workspace_path)
        / ".openart"
        / "runners"
        / "target"
        / "hooks"
        / "claude-code-enforce-settings.sh"
    )
    assert staged_hook.is_file()
    assert "OPENART_CLAUDE_AUTO_APPROVAL_ALLOW" in staged_hook.read_text(encoding="utf-8")


def test_factory_applies_model_integration_env_and_config_template(monkeypatch, tmp_path: Path) -> None:
    bundle = _make_bundle(tmp_path)
    config_dir = tmp_path / "configs"
    config_dir.mkdir(parents=True, exist_ok=True)
    target_config_path = config_dir / "target.custom.yaml"
    target_config_path.write_text("target: {}\n", encoding="utf-8")
    native_dir = config_dir / "native"
    native_dir.mkdir(parents=True, exist_ok=True)
    (native_dir / "opencode.json").write_text(
        json.dumps(
            {
                "$schema": "https://opencode.ai/config.json",
                "model": "openart/${TARGET_MODEL}",
                "provider": {
                    "openart": {
                        "options": {
                            "baseURL": "${TARGET_BASE_URL}",
                            "apiKey": "{env:OPENAI_API_KEY}",
                        }
                    }
                },
            },
            ensure_ascii=True,
            indent=2,
        ) + "\n",
        encoding="utf-8",
    )
    monkeypatch.setenv("TARGET_API_KEY", "dummy")
    monkeypatch.setenv("TARGET_BASE_URL", "http://llm.internal/v1")
    monkeypatch.setenv("TARGET_MODEL", "glm-5")
    factory = OrchestratorFactory(
        bundle=bundle,
        output_dir=str(tmp_path / "out"),
        run_id="run-1",
        target_config={
            "framework": "prompt_cli",
            "runner_image": "openart/opencode:latest",
            "launch_cmd": "opencode run",
            "model_integration": {
                "binding": {
                    "provider_family": "openai_compatible",
                    "api_key": "${TARGET_API_KEY}",
                    "base_url": "${TARGET_BASE_URL}",
                    "model": "${TARGET_MODEL}",
                },
                "delivery": {
                    "type": "hybrid",
                    "env_names": {
                        "api_key": "OPENAI_API_KEY",
                    },
                    "config_template": {
                        "source": "target:native/opencode.json",
                        "destination": "XDG_CONFIG_HOME/opencode/opencode.json",
                        "format": "json",
                    },
                },
            },
        },
        target_config_path=str(target_config_path),
    )
    factory._workspace_path = str(tmp_path / "out" / "workspace")

    runner = factory._create_runner("target")

    assert runner.runtime_env["OPENAI_API_KEY"] == "dummy"
    assert "ANTHROPIC_API_KEY" not in runner.runtime_env
    assert runner.runtime_env["OPENART_MODEL_CONFIG_JSON_SOURCE_FILE"] == "/workspace/.openart_model_integration_target.json"
    assert runner.runtime_env["OPENART_MODEL_CONFIG_JSON_DESTINATION"] == "/workspace/.openart/runners/target/config/opencode/opencode.json"
    mounts = {mount.container_path: mount.host_path for mount in runner.container.spec.mounts}
    assert mounts["/workspace/.openart_model_integration_target.json"].endswith("model_integration/target/opencode.json")
    staged_text = Path(mounts["/workspace/.openart_model_integration_target.json"]).read_text(encoding="utf-8")
    staged = json.loads(staged_text)
    assert staged["model"] == "openart/glm-5"
    assert staged["provider"]["openart"]["options"]["baseURL"] == "http://llm.internal/v1"


def test_factory_stages_openclaw_native_config_to_runner_home(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setenv("TARGET_API_KEY", "dummy")
    monkeypatch.setenv("TARGET_BASE_URL", "http://llm.internal/v1")
    monkeypatch.setenv("TARGET_MODEL", "glm-5")
    bundle = _make_bundle(tmp_path)
    factory = OrchestratorFactory(
        bundle=bundle,
        output_dir=str(tmp_path / "out"),
        run_id="run-1",
        target_config={
            "framework": "prompt_cli",
            "surface_family": "openclaw",
            "runner_image": "openart/openclaw:latest",
            "launch_cmd": (
                "openclaw --no-color agent --local --json --model openart/${TARGET_MODEL} "
                "--session-key agent:main:openart-target --thinking medium --timeout 600 --message"
            ),
            "config_overlay": {
                "prompt_transport": "argv",
                "prompt_flag": "",
            },
            "model_integration": {
                "binding": {
                    "provider_family": "openai_compatible",
                    "api_key": "${TARGET_API_KEY}",
                    "base_url": "${TARGET_BASE_URL}",
                    "model": "${TARGET_MODEL}",
                },
                "delivery": {
                    "type": "hybrid",
                    "env_names": {
                        "api_key": "OPENAI_API_KEY",
                        "base_url": "OPENAI_BASE_URL",
                        "model": "OPENAI_MODEL",
                    },
                    "config_template": {
                        "source": "repo:configs/target-model-json/openclaw.openai-compatible.json",
                        "destination": "HOME/.openclaw/openclaw.json",
                        "format": "json",
                    },
                },
            },
        },
    )
    factory._workspace_path = str(tmp_path / "out" / "workspace")

    runner = factory._create_runner("target")

    assert "openclaw-openart-runner" not in runner.command.template
    assert "openclaw --no-color agent" in runner.command.template
    assert "--model openart/glm-5" in runner.command.template
    assert runner.runtime_env["OPENART_MODEL_CONFIG_JSON_DESTINATION"] == (
        "/tmp/openart/runners/target/home/.openclaw/openclaw.json"
    )
    assert "OPENART_PRE_RUN_HOOK" not in runner.runtime_env
    mounts = {mount.container_path: mount.host_path for mount in runner.container.spec.mounts}
    staged_path = mounts["/workspace/.openart_model_integration_target.json"]
    staged_text = Path(staged_path).read_text(encoding="utf-8")
    staged = json.loads(staged_text)
    assert "dummy" not in staged_text
    assert staged["models"]["providers"]["openart"]["apiKey"] == "${OPENAI_API_KEY}"


def test_factory_seeds_matching_model_config_surface(tmp_path: Path) -> None:
    bundle = _make_bundle(tmp_path)
    factory = OrchestratorFactory(
        bundle=bundle,
        output_dir=str(tmp_path / "out"),
        run_id="run-1",
        target_config={
            "framework": "prompt_cli",
            "surface_family": "custom",
            "model_integration": {
                "binding": {
                    "provider_family": "openai_compatible",
                    "api_key": "dummy",
                    "base_url": "http://llm.internal/v1",
                    "model": "glm-5",
                },
                "delivery": {
                    "type": "hybrid",
                    "config_template": {
                        "destination": "HOME/.custom/config.json",
                    },
                },
            },
            "attack_surfaces": [
                {
                    "vector": "custom_config",
                    "kind": "configuration",
                    "path_template": "HOME/.custom/config.json",
                    "description": "Native config file.",
                }
            ],
        },
    )
    factory._workspace_manager.ensure_run_layout("run-1")
    staged_dir = tmp_path / "out" / "model_integration" / "target"
    staged_dir.mkdir(parents=True)
    (staged_dir / "config.json").write_text('{"ok": true}\n', encoding="utf-8")

    factory._stage_model_configs_to_shared_workspace()

    seeded = tmp_path / "out" / "workspace" / "shared" / "HOME" / ".custom" / "config.json"
    assert seeded.read_text(encoding="utf-8") == '{"ok": true}\n'


def test_factory_does_not_seed_model_descriptor_into_unmatched_config_surface(tmp_path: Path) -> None:
    bundle = _make_bundle(tmp_path)
    factory = OrchestratorFactory(
        bundle=bundle,
        output_dir=str(tmp_path / "out"),
        run_id="run-1",
        target_config={
            "framework": "prompt_cli",
            "surface_family": "openclaw",
            "model_integration": {
                "binding": {
                    "provider_family": "openai_compatible",
                    "api_key": "dummy",
                    "base_url": "http://llm.internal/v1",
                    "model": "glm-5",
                },
                "delivery": {
                    "type": "hybrid",
                    "config_template": {
                        "destination": "RUNNER_STATE_DIR/unmatched-openclaw-config.json",
                    },
                },
            },
            "attack_surfaces": [
                {
                    "vector": "openclaw_config",
                    "kind": "configuration",
                    "path_template": "HOME/.openclaw/openclaw.json",
                    "description": "OpenClaw config overlay.",
                }
            ],
        },
    )
    factory._workspace_manager.ensure_run_layout("run-1")
    staged_dir = tmp_path / "out" / "model_integration" / "target"
    staged_dir.mkdir(parents=True)
    (staged_dir / "openclaw.openai-compatible.json").write_text('{"provider": "descriptor"}\n', encoding="utf-8")

    factory._stage_model_configs_to_shared_workspace()

    unexpected = tmp_path / "out" / "workspace" / "shared" / "HOME" / ".openclaw" / "openclaw.json"
    assert not unexpected.exists()


def test_factory_build_smoke_wires_runtime_graph_without_starting_containers(tmp_path: Path) -> None:
    bundle = _make_bundle(
        tmp_path,
        required_services=["gitlab"],
        attacker=AttackerSpec(
            name="setup-attacker",
            instruction="attacker.md",
            image="python:3.11-slim",
            cmd="python3",
            args=["{{attacker_instruction_file}}"],
            target_control_plane=True,
            vector_permissions=["claude_md"],
        ),
    )
    factory = OrchestratorFactory(
        bundle=bundle,
        output_dir=str(tmp_path / "out"),
        run_id="run-1",
        target_config=_surface_target_config("opencode") | {
            "runner_image": "openart/opencode:latest",
            "launch_cmd": "opencode run",
        },
        eval_strategy="deterministic",
    )

    orchestrator = factory.build()

    assert orchestrator.target_runner.framework_name() == "prompt_cli"
    assert orchestrator.attacker is not None
    assert orchestrator.attacker_context is not None
    assert orchestrator.attacker_context.input_workspace_dir == "/workspace/.openart_input_workspace"
    assert orchestrator.attacker_context.output_target_control_dir == "/workspace/.openart_target_control_output"
    assert orchestrator.evaluator is not None
    assert Path(tmp_path / "out" / "workspace" / "shared").is_dir()
    assert Path(tmp_path / "out" / "control" / "target" / "base").is_dir()

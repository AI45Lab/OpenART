from __future__ import annotations

import json
from pathlib import Path

from framework.attackers.models import AttackerSpec
from framework.components.evaluators import DeterministicEvaluator
from framework.components.services import ExternalService
from framework.core.factory import DEFAULT_COMMAND_TEMPLATES, DEFAULT_RUNNER_IMAGES, MIN_TARGET_TIMEOUT_SECONDS, OrchestratorFactory
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


def test_factory_creates_external_service(tmp_path: Path) -> None:
    bundle = _make_bundle(tmp_path, required_services=["gitlab"])
    factory = OrchestratorFactory(
        bundle=bundle,
        output_dir=str(tmp_path / "out"),
        run_id="run-1",
    )

    service = factory._create_service("gitlab")

    assert isinstance(service, ExternalService)
    assert service.get_endpoint("web").url == "http://gitlab:8080"
    assert service.get_endpoint("api").url == "http://gitlab:8080/api/v4"


def test_factory_resolves_service_endpoints_from_env_and_overrides(
    tmp_path: Path,
    monkeypatch,
) -> None:
    bundle = _make_bundle(tmp_path, required_services=["gitlab", "owncloud"])
    monkeypatch.setenv("GITLAB_BASEURL", "http://env-gitlab:8929")

    factory = OrchestratorFactory(
        bundle=bundle,
        output_dir=str(tmp_path / "out"),
        run_id="run-1",
        service_endpoint_overrides={
            "gitlab.api": "http://api.example.com/v4",
            "owncloud.web": "http://owncloud.example.com:8092",
        },
    )

    resolved = factory._resolved_service_endpoints()
    runtime_env = factory._runtime_service_env()

    assert resolved["gitlab"]["web"] == "http://env-gitlab:8929"
    assert resolved["gitlab"]["api"] == "http://api.example.com/v4"
    assert resolved["owncloud"]["web"] == "http://owncloud.example.com:8092"
    assert resolved["owncloud"]["dav"] == "http://owncloud.example.com:8092/remote.php/dav"

    assert runtime_env["GITLAB_BASEURL"] == "http://env-gitlab:8929"
    assert runtime_env["OWNCLOUD_URL"] == "http://owncloud.example.com:8092"
    flat = json.loads(runtime_env["OPENART_SERVICE_ENDPOINTS"])
    assert flat["gitlab.api"] == "http://api.example.com/v4"
    assert flat["owncloud.dav"] == "http://owncloud.example.com:8092/remote.php/dav"


def test_factory_passes_harness_and_env_to_deterministic_evaluator(tmp_path: Path) -> None:
    bundle = _make_bundle(tmp_path, required_services=["gitlab"])
    factory = OrchestratorFactory(
        bundle=bundle,
        output_dir=str(tmp_path / "out"),
        run_id="run-1",
        service_endpoint_overrides={"gitlab.web": "http://gitlab.external:8929"},
        evaluator_harness="/tmp/oas_harness",
        evaluator_env={"TAC_TEST_MODE": "1"},
    )

    task_container = factory._create_task_container()
    evaluator = factory._create_evaluator(task_container)

    assert isinstance(evaluator, DeterministicEvaluator)
    assert evaluator.harness_path == "/tmp/oas_harness"
    assert evaluator.runtime_env["TAC_TEST_MODE"] == "1"
    assert evaluator.runtime_env["GITLAB_BASEURL"] == "http://gitlab.external:8929"
    assert evaluator.runtime_env["OAS_EXTERNAL_MODE"] == "real"


def test_factory_runtime_env_includes_credentials_and_no_proxy(monkeypatch, tmp_path: Path) -> None:
    bundle = _make_bundle(tmp_path, required_services=["gitlab", "owncloud", "plane"])
    monkeypatch.setenv("GITLAB_BASEURL", "http://gitlab.example:8929")
    monkeypatch.setenv("OWNCLOUD_URL", "http://owncloud.example:8092")
    monkeypatch.setenv("PLANE_BASEURL", "http://plane.example:8091")
    monkeypatch.setenv("GITLAB_ACCESS_TOKEN", "gitlab-secret")
    monkeypatch.setenv("OWNCLOUD_USERNAME", "alice")
    monkeypatch.setenv("OWNCLOUD_PASSWORD", "pw")
    monkeypatch.setenv("PLANE_API_KEY", "plane-secret")
    factory = OrchestratorFactory(
        bundle=bundle,
        output_dir=str(tmp_path / "out"),
        run_id="run-1",
        service_config={
            "env": {"SERVER_HOSTNAME": "gateway.internal"},
        },
    )

    runtime_env = factory._runtime_service_env()

    assert runtime_env["GITLAB_ACCESS_TOKEN"] == "gitlab-secret"
    assert runtime_env["GITLAB_TOKEN"] == "gitlab-secret"
    assert runtime_env["OWNCLOUD_USERNAME"] == "alice"
    assert runtime_env["OWNCLOUD_PASSWORD"] == "pw"
    assert runtime_env["PLANE_API_KEY"] == "plane-secret"
    assert runtime_env["OAS_EXTERNAL_MODE"] == "real"
    assert "gitlab.example" in runtime_env["NO_PROXY"]
    assert "owncloud.example" in runtime_env["NO_PROXY"]
    assert "plane.example" in runtime_env["NO_PROXY"]


def test_factory_runner_framework_override_uses_matching_defaults(tmp_path: Path) -> None:
    bundle = _make_bundle(tmp_path)
    factory = OrchestratorFactory(
        bundle=bundle,
        output_dir=str(tmp_path / "out"),
        run_id="run-1",
        runner_framework="generic_cli",
        target_config={
            "framework": "opencode",
            "runner_image": "openart/opencode:latest",
            "launch_cmd": "opencode run {{task_instruction_file}}",
        },
    )
    factory._workspace_path = str(tmp_path / "out" / "workspace")

    runner = factory._create_runner("target")

    assert runner.framework_name() == "generic_cli"
    assert runner.container.spec.image == DEFAULT_RUNNER_IMAGES["generic_cli"]
    assert runner.command.template == DEFAULT_COMMAND_TEMPLATES["generic_cli"]


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
    assert mounts["/workspace/.openart_input_workspace"].endswith("workspace/shared")
    assert "/workspace/attackers/setup-attacker/before_target_001" in mounts["/workspace"]
    assert mounts["/workspace/.openart_feedback"].endswith("out")
    assert mounts["/attacker_config"].endswith("attacker-config")
    assert mounts["/workspace/.openart_target_control_input"].endswith("control/target/base")
    assert mounts["/workspace/.openart_target_control_output"].endswith("control/target/attackers/setup-attacker/before_target_001")
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

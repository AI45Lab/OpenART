"""Factory for building Orchestrator from TaskBundleSpec."""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any, Optional

from framework.attackers.base import AttackerBase
from framework.attackers.methods import GenericCommandAttacker
from framework.attackers.models import AttackerContext
from framework.components.containers import RunnerContainer, TaskContainer
from framework.components.evaluators import CompositeEvaluator, DeterministicEvaluator, EvaluatorBase, LLMJudgeEvaluator
from framework.components.runners import (
    RunnerBase,
    RunnerRegistry,
    create_default_runner_registry,
)
from framework.components.services import (
    ExternalService,
    ServiceBase,
    ServiceManager,
)
from framework.components.trace import JsonlTraceSink
from framework.core.control_plane import (
    ControlPlaneManager,
    ControlPlaneProviderRegistry,
    create_control_plane_provider,
    create_default_control_plane_provider_registry,
)
from framework.core.helpers import first_non_empty, resolve_env_value, resolve_nested_env_values
from framework.core.orchestrator import Orchestrator
from framework.core.workspace import WorkspaceManager
from framework.core.service_config import (
    build_service_runtime_env,
    default_service_endpoints,
    normalize_service_endpoint_overrides,
    resolve_service_endpoints,
    service_config_credentials,
)
from framework.models.common import CommandSpec, CredentialBundle, Endpoint
from framework.models.common import MCPServerSpec, SkillSpec, ToolSpec
from framework.models.container import ContainerSpec, MountSpec
from framework.models.task import TaskBundleSpec


# =============================================================================
# DEFAULT IMAGES
# =============================================================================

# Default task image - a well-designed base image for task execution
# Includes: Python 3.11, common CLI tools, git, curl, jq
DEFAULT_TASK_IMAGE = "openart/task-base:latest"
MIN_TARGET_TIMEOUT_SECONDS = 2700

# Default runner images (agent frameworks)
DEFAULT_RUNNER_IMAGES = {
    "claude_code": "openart/claude-code:latest",
    "hermes": "openart/hermes:latest",
    "nanobot": "openart/nanobot:latest",
    "opencode": "openart/opencode:latest",
    "pi": "openart/pi:latest",
    "generic_cli": "python:3.11-slim",
    "prompt_cli": "python:3.11-slim",
}

# Default command templates for each framework
DEFAULT_COMMAND_TEMPLATES = {
    "claude_code": "claude -p",
    "hermes": "hermes -z",
    "nanobot": "nanobot agent",
    "opencode": "opencode run",
    "pi": "pi -p",
    "generic_cli": "python {{task_instruction_file}}",
    "prompt_cli": "python {{task_instruction_file}}",
}

REPO_ROOT = Path(__file__).resolve().parents[2]
MODEL_CONFIG_JSON_MOUNT_PATH_TEMPLATE = "/workspace/.openart_model_integration_{role}.json"
_SYMBOLIC_DESTINATION_ROOTS = {
    "HOME": lambda env: str(env.get("HOME", "") or ""),
    "XDG_CONFIG_HOME": lambda env: str(env.get("XDG_CONFIG_HOME", "") or ""),
    "XDG_DATA_HOME": lambda env: str(env.get("XDG_DATA_HOME", "") or ""),
    "XDG_CACHE_HOME": lambda env: str(env.get("XDG_CACHE_HOME", "") or ""),
    "WORKSPACE": lambda env: "/workspace",
    "RUNNER_STATE_DIR": lambda env: str(env.get("OPENART_RUNNER_STATE_DIR", "") or ""),
}
_LEGACY_TARGET_MODEL_FIELDS = ("model", "base_url", "api_base_url", "api_key", "api_key_env")


# =============================================================================
# ORCHESTRATOR FACTORY
# =============================================================================

class OrchestratorFactory:
    """Factory to build Orchestrator from TaskBundleSpec.

    This factory creates all the components needed for a full orchestrator run:
    - ServiceManager: Tracks external service endpoints and health
    - TaskContainer: Docker container for task execution environment
    - Target runner: agent framework for the task target
    - Attacker: dedicated attacker container with workspace replacement semantics
    - Evaluator: Deterministic or LLM-based evaluation

    The workspace is shared between TaskContainer and RunnerContainer, allowing
    agents to read/write files that persist for evaluation.
    """

    def __init__(
        self,
        bundle: TaskBundleSpec,
        output_dir: str,
        run_id: str,
        trace_sink: Optional[JsonlTraceSink] = None,
        task_image: Optional[str] = None,
        skip_build: bool = False,
        service_endpoint_overrides: Optional[dict[str, str]] = None,
        evaluator_harness: Optional[str] = None,
        evaluator_env: Optional[dict[str, str]] = None,
        runner_framework: Optional[str] = None,
        runner_image: Optional[str] = None,
        runner_command: Optional[str] = None,
        runner_model: Optional[str] = None,
        target_config: Optional[dict[str, Any]] = None,
        target_config_path: Optional[str] = None,
        service_config: Optional[dict[str, Any]] = None,
        eval_strategy: str = "auto",
        skip_attacker: bool = False,
        max_iterations: int = 1,
        adaptive_iterations: bool = False,
        runner_registry: Optional[RunnerRegistry] = None,
        control_plane_registry: Optional[ControlPlaneProviderRegistry] = None,
    ) -> None:
        """Initialize the factory.

        Args:
            bundle: Task bundle specification loaded from task.yaml
            output_dir: Directory for run outputs (workspace, traces, reports)
            run_id: Unique identifier for this run
            trace_sink: Optional trace sink for event logging
            task_image: Custom task container image (default: openart/task-base:latest)
            skip_build: Skip building task image (use pre-built image)
        """
        self.bundle = bundle
        self.output_dir = output_dir
        self.run_id = run_id
        self.trace_sink = trace_sink
        self.task_image = task_image
        self.skip_build = skip_build
        self._service_endpoint_overrides = normalize_service_endpoint_overrides(service_endpoint_overrides)
        self.evaluator_harness = evaluator_harness
        self.evaluator_env = dict(evaluator_env or {})
        self.runner_framework = (runner_framework or "").strip().lower()
        self.runner_image = (runner_image or "").strip()
        self.runner_command = (runner_command or "").strip()
        self.runner_model = (runner_model or "").strip()
        self.target_config = dict(target_config or {})
        self.target_config_path = str(target_config_path or "").strip()
        self.service_config = dict(service_config or {})
        self.eval_strategy = (eval_strategy or "auto").strip().lower()
        self.skip_attacker = bool(skip_attacker)
        self.max_iterations = max(1, int(max_iterations or 1))
        self.adaptive_iterations = bool(adaptive_iterations)
        self._runner_registry = runner_registry or create_default_runner_registry()
        self._control_plane_registry = control_plane_registry or create_default_control_plane_provider_registry()
        self._target_control_plane_mount_mode = str(
            resolve_env_value((self.target_config or {}).get("control_plane_mount_mode"))
            if isinstance((self.target_config or {}).get("control_plane_mount_mode"), str)
            else (self.target_config or {}).get("control_plane_mount_mode")
            or "workspace"
        ).strip().lower()

        # Workspace path - canonical shared workspace used by task container and target runner
        self._workspace_path: Optional[str] = None
        self._workspace_manager = WorkspaceManager(str(Path(self.output_dir) / "workspace"))
        self._target_framework = self._resolve_target_framework_name()
        self._control_manager = ControlPlaneManager(
            root_dir=str(Path(self.output_dir) / "control" / "target"),
            source_root=str(self._workspace_manager.shared_dir(self.run_id)),
            provider=self._resolve_target_control_plane_provider(),
        )

    def build(self) -> Orchestrator:
        """Build and return a fully configured Orchestrator."""
        # Ensure output directory exists
        Path(self.output_dir).mkdir(parents=True, exist_ok=True)

        # Create trace sink if not provided
        trace_file = str(Path(self.output_dir) / "trace.jsonl")
        if self.trace_sink is None:
            self.trace_sink = JsonlTraceSink(trace_file)

        self._workspace_manager.ensure_run_layout(self.run_id)
        self._control_manager.ensure_layout()

        # Build components
        service_manager = self._create_service_manager()
        task_container = self._create_task_container()
        target_runner = self._create_runner("target")
        attacker, attacker_context = self._create_attacker()
        evaluator = self._create_evaluator(task_container)

        return Orchestrator(
            service_manager=service_manager,
            target_runner=target_runner,
            attacker=attacker,
            attacker_context=attacker_context,
            evaluator=evaluator,
            task_container=task_container,
            workspace_manager=self._workspace_manager,
            control_manager=self._control_manager,
            target_control_plane_mount_mode=self._target_control_plane_mount_mode,
            max_iterations=self.max_iterations,
            adaptive_iterations=self.adaptive_iterations,
            trace_sink=self.trace_sink,
            trace_file=trace_file,
        )

    # =========================================================================
    # SERVICE MANAGEMENT
    # =========================================================================

    def _create_service_manager(self) -> ServiceManager:
        """Build an external-only ServiceManager from required_services."""
        services: list[ServiceBase] = []
        resolved_endpoints = resolve_service_endpoints(
            self.bundle.required_services,
            self.service_config,
            self._service_endpoint_overrides,
        )

        for service_name in self.bundle.required_services:
            service = self._create_service(service_name)
            if service:
                service.endpoint_overrides = dict(resolved_endpoints.get(service_name.lower(), {}))
                services.append(service)

        return ServiceManager(services)

    def _create_service(self, name: str) -> Optional[ServiceBase]:
        """Create an external service by name."""
        credentials = CredentialBundle(values=self._get_service_credentials(name))
        known_services = {"gitlab", "owncloud", "plane"}
        service_name = name.lower()
        if service_name not in known_services:
            return None

        service = ExternalService(service_name, credentials, trace_sink=self.trace_sink)
        default_endpoints = default_service_endpoints(service_name)
        for endpoint_name, endpoint_url in default_endpoints.items():
            service.endpoints[endpoint_name] = Endpoint(endpoint_name, endpoint_url)
        return service

    def _get_service_credentials(self, service_name: str) -> dict[str, str]:
        """Get credentials for a service from environment variables."""
        prefix = service_name.upper() + "_"
        creds: dict[str, str] = {}
        for key, value in os.environ.items():
            if key.startswith(prefix):
                creds[key[len(prefix):].lower()] = value

        config_creds = service_config_credentials(self.service_config, service_name)
        if service_name.lower() == "gitlab":
            token = first_non_empty(
                config_creds.get("access_token"),
                config_creds.get("token"),
                config_creds.get("private_token"),
            )
            if token:
                creds["access_token"] = token
                creds["token"] = token
                creds["private_token"] = token
        creds.update(config_creds)
        return creds

    def _resolved_service_endpoints(self) -> dict[str, dict[str, str]]:
        return resolve_service_endpoints(
            self.bundle.required_services,
            self.service_config,
            self._service_endpoint_overrides,
        )

    # =========================================================================
    # TASK CONTAINER
    # =========================================================================

    def _create_task_container(self) -> TaskContainer:
        """Build TaskContainer from bundle.

        The TaskContainer provides the execution environment for the task.
        It can be:
        1. Built from a Dockerfile in the task directory
        2. Use a pre-built image (--task-image argument)
        3. Use the default base image (openart/task-base:latest)

        The workspace directory is mounted and shared with runners.
        """
        task_root = Path(self.bundle.root_dir)

        # Determine if we need to build from Dockerfile
        dockerfile_path = task_root / self.bundle.dockerfile if self.bundle.dockerfile else None
        has_dockerfile = dockerfile_path and dockerfile_path.exists()

        # Determine the image to use
        if self.task_image:
            # User specified image via CLI argument
            image = self.task_image
            build_context = None
            dockerfile = None
        elif has_dockerfile and not self.skip_build:
            # Build from task's Dockerfile
            image = f"openart/task-{self.bundle.task_id}:latest"
            context_dir = task_root / self.bundle.context_dir if self.bundle.context_dir else task_root
            build_context = str(context_dir)
            dockerfile = str(dockerfile_path)
        else:
            # Use default task base image
            image = DEFAULT_TASK_IMAGE
            build_context = None
            dockerfile = None

        spec = ContainerSpec(
            name=f"openart-task-{self.run_id}",
            image=image,
            build_context=build_context,
            dockerfile=dockerfile,
            command=["tail", "-f", "/dev/null"],
            env=self._runtime_service_env(),
            working_dir="/workspace",
            lifecycle_log_path=str(Path(self.output_dir) / "runtime.log"),
        )

        container = TaskContainer(spec, seed_dir=self._container_seed_dir())

        # Setup workspace directory
        # This is shared with runners so they can read/write files
        workspace_dir = self._workspace_manager.shared_dir(self.run_id)
        workspace_dir.mkdir(parents=True, exist_ok=True)
        self._workspace_path = str(workspace_dir)
        container.mount_workspace(self._workspace_path)

        # Mount task assets (read-only)
        container.mount_task_assets(str(task_root))

        # Mount evaluator harness when provided (read-only)
        if self.evaluator_harness:
            harness_path = Path(self.evaluator_harness)
            if harness_path.exists() and harness_path.is_dir():
                container.spec.mounts.append(
                    MountSpec(
                        host_path=str(harness_path),
                        container_path="/harness",
                        read_only=True,
                    )
                )

        return container

    # =========================================================================
    # RUNNERS
    # =========================================================================

    def _resolve_target_framework_name(self) -> str:
        target_framework = str((self.target_config or {}).get("framework") or "").strip().lower()
        if target_framework:
            return target_framework
        framework = str(self.runner_framework or "").strip().lower()
        if framework:
            return framework
        return "claude_code"

    def _resolve_target_control_plane_provider(self):
        # Check for target-config attack_surfaces first (primary path)
        attack_surfaces = (self.target_config or {}).get("attack_surfaces")
        if isinstance(attack_surfaces, list) and attack_surfaces:
            from framework.core.control_plane import build_provider_from_attack_surfaces
            return build_provider_from_attack_surfaces(self._target_framework, attack_surfaces)

        # Legacy: control_plane string/dict config
        raw_config = (self.target_config or {}).get("control_plane")
        control_plane_config: str | dict[str, Any] | None
        if isinstance(raw_config, dict):
            control_plane_config = resolve_nested_env_values(raw_config)
        elif isinstance(raw_config, str):
            control_plane_config = resolve_env_value(raw_config)
        else:
            control_plane_config = None
        return create_control_plane_provider(
            self._target_framework,
            registry=self._control_plane_registry,
            config=control_plane_config,
        )

    def _create_runner(self, role: str) -> RunnerBase:
        """Create a runner for the given role (target/attack).

        The runner container shares the workspace with the task container,
        allowing the agent to:
        - Read task instructions from /task
        - Read/write files in /workspace
        - Persist changes for evaluation
        """
        role_cfg = self.target_config if role == "target" else {}
        if role == "target":
            self._validate_no_legacy_target_model_fields(role_cfg)
        role_framework = str(role_cfg.get("framework") or "").strip().lower()

        framework = str(
            self.runner_framework
            or role_framework
            or ""
        ).strip().lower()
        if not framework:
            framework = "claude_code"

        if framework not in self._runner_registry.names():
            known = ", ".join(self._runner_registry.names()) or "<none>"
            raise ValueError(
                f"Unsupported runner framework: {framework}. Registered frameworks: {known}"
            )

        use_role_runner_profile = not self.runner_framework or not role_framework or framework == role_framework

        image = str(
            self.runner_image
            or (role_cfg.get("runner_image") if use_role_runner_profile else "")
            or DEFAULT_RUNNER_IMAGES.get(framework, "python:3.11-slim")
        ).strip()

        command_template = str(
            resolve_env_value(
                self.runner_command
                or (role_cfg.get("launch_cmd") if use_role_runner_profile else "")
                or DEFAULT_COMMAND_TEMPLATES.get(framework, "")
            )
        ).strip()

        base_url = ""
        model = first_non_empty(self.runner_model)
        api_key = ""

        runner_network = str(
            resolve_env_value(role_cfg.get("network"))
            if use_role_runner_profile and isinstance(role_cfg.get("network"), str)
            else ""
        ).strip() or None

        container_spec = ContainerSpec(
            name=f"openart-{role}-{self.run_id}",
            image=image,
            command=["tail", "-f", "/dev/null"],
            env=self._runtime_service_env(),
            working_dir="/workspace",
            network=runner_network,
            lifecycle_log_path=str(Path(self.output_dir) / "runtime.log"),
        )

        if "codex" in command_template.split():
            for key in (
                "HTTP_PROXY", "HTTPS_PROXY", "ALL_PROXY",
                "http_proxy", "https_proxy", "all_proxy",
            ):
                container_spec.env.pop(key, None)

        # Mount task assets (read-only) - for instruction files
        task_root = Path(self.bundle.root_dir)
        container_spec.mounts.append(MountSpec(
            host_path=str(task_root),
            container_path="/task",
            read_only=True,
        ))

        # Mount workspace (read-write) - shared with TaskContainer
        # This allows the agent to modify files that persist for evaluation
        if self._workspace_path:
            container_spec.mounts.append(MountSpec(
                host_path=self._workspace_path,
                container_path="/workspace",
                read_only=False,
            ))

        container = RunnerContainer(container_spec)

        runtime_env = self._runtime_service_env()
        if "codex" in command_template.split():
            for key in (
                "HTTP_PROXY", "HTTPS_PROXY", "ALL_PROXY",
                "http_proxy", "https_proxy", "all_proxy",
            ):
                runtime_env.pop(key, None)
        runtime_env["HOME"] = f"/workspace/.openart/runners/{role}/home"
        runtime_env["XDG_CONFIG_HOME"] = f"/workspace/.openart/runners/{role}/config"
        runtime_env["OPENART_RUNNER_STATE_DIR"] = f"/workspace/.openart/runners/{role}/state"
        if framework in {"opencode", "prompt_cli"}:
            runtime_env["HOME"] = f"/tmp/openart/runners/{role}/home"
            runtime_env["XDG_DATA_HOME"] = f"/tmp/openart/runners/{role}/data"
            runtime_env["XDG_CACHE_HOME"] = f"/tmp/openart/runners/{role}/cache"
            if framework == "opencode":
                runtime_env.setdefault("OPENCODE_DISABLE_AUTOUPDATE", "1")
        explicit_model_integration = self._role_model_integration(role_cfg)
        if explicit_model_integration:
            runtime_env.update(self._resolve_model_integration_env(explicit_model_integration))
        probe_paths = role_cfg.get("control_plane_probe_paths") if isinstance(role_cfg, dict) else None
        if isinstance(probe_paths, (list, tuple)):
            cleaned_probe_paths = [str(path).strip() for path in probe_paths if str(path).strip()]
        elif role == "target":
            surfaces = (role_cfg or {}).get("attack_surfaces")
            if isinstance(surfaces, list) and surfaces:
                from framework.core.control_plane import derive_probe_paths_from_attack_surfaces
                cleaned_probe_paths = derive_probe_paths_from_attack_surfaces(surfaces)
            else:
                cleaned_probe_paths = []
        else:
            cleaned_probe_paths = []
        if cleaned_probe_paths:
            runtime_env["OPENART_CONTROL_PLANE_PROBE_PATHS"] = json.dumps(cleaned_probe_paths, ensure_ascii=True)
        config_json_spec = self._resolve_model_integration_config_json(explicit_model_integration, role, runtime_env)
        if config_json_spec is not None:
            container_spec.mounts.append(MountSpec(
                host_path=config_json_spec["host_path"],
                container_path=config_json_spec["mount_path"],
                read_only=True,
            ))
            runtime_env["OPENART_MODEL_CONFIG_JSON_SOURCE_FILE"] = config_json_spec["mount_path"]
            runtime_env["OPENART_MODEL_CONFIG_JSON_DESTINATION"] = config_json_spec["destination"]

        role_overlay = (
            resolve_nested_env_values(role_cfg.get("config_overlay"))
            if isinstance(role_cfg.get("config_overlay"), dict)
            else {}
        )

        tools = _parse_tool_specs(role_cfg.get("tools"))
        mcp_servers = _parse_mcp_server_specs(role_cfg.get("mcp_servers"))
        skills = _parse_skill_specs(role_cfg.get("skills"))

        # Create command spec
        timeout_seconds = int(self.bundle.timeout_seconds or 0)
        if role == "target":
            timeout_seconds = max(timeout_seconds, MIN_TARGET_TIMEOUT_SECONDS)

        command = CommandSpec(
            template=command_template,
            shell="/bin/bash",
            timeout_seconds=timeout_seconds,
        )

        # Create credentials
        credentials = CredentialBundle(values={"api_key": api_key} if api_key else {})

        # Create the appropriate runner type
        runner_kwargs = {
            "name": f"{role}_runner",
            "role": role,
            "container": container,
            "command": command,
            "credentials": credentials,
            "tools": tools,
            "mcp_servers": mcp_servers,
            "skills": skills,
            "tool_guide_markdown": str(role_cfg.get("tool_guide_markdown", "") or ""),
            "trace_sink": self.trace_sink,
            "base_url": base_url,
            "model": model,
            "extra_config": role_overlay,
            "runtime_env": runtime_env,
            "artifact_dir": self.output_dir,
        }

        return self._runner_registry.create(framework, **runner_kwargs)

    def _role_model_integration(self, role_cfg: dict[str, Any]) -> dict[str, Any]:
        raw = role_cfg.get("model_integration") if isinstance(role_cfg, dict) else None
        return dict(raw) if isinstance(raw, dict) else {}

    def _validate_no_legacy_target_model_fields(self, role_cfg: dict[str, Any]) -> None:
        legacy_fields = [name for name in _LEGACY_TARGET_MODEL_FIELDS if role_cfg.get(name) not in (None, "", [], {}, ())]
        if not legacy_fields:
            return
        raise ValueError(
            "legacy target model fields are no longer supported: "
            + ", ".join(legacy_fields)
            + ". Use target.model_integration.env and/or target.model_integration.config_json instead."
        )

    def _resolve_model_integration_env(self, integration_cfg: dict[str, Any]) -> dict[str, str]:
        raw_env = integration_cfg.get("env")
        if not isinstance(raw_env, dict):
            return {}
        resolved = resolve_nested_env_values(raw_env)
        payload: dict[str, str] = {}
        for key, value in resolved.items():
            env_name = str(key or "").strip()
            if not env_name:
                continue
            payload[env_name] = str(value or "")
        return payload

    def _resolve_model_integration_config_json(
        self,
        integration_cfg: dict[str, Any],
        role: str,
        runtime_env: dict[str, str],
    ) -> dict[str, str] | None:
        raw_cfg = integration_cfg.get("config_json")
        if not isinstance(raw_cfg, dict):
            return None
        source_spec = str(resolve_env_value(raw_cfg.get("source")) or "").strip()
        destination_spec = str(resolve_env_value(raw_cfg.get("destination")) or "").strip()
        if not source_spec or not destination_spec:
            raise ValueError("model_integration.config_json requires both source and destination")
        source_path = self._resolve_model_integration_source_path(source_spec)
        destination_path = self._expand_model_integration_destination(destination_spec, runtime_env)
        try:
            parsed = json.loads(source_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            raise ValueError(f"model_integration.config_json source is not valid JSON: {source_path}") from exc
        rendered = resolve_nested_env_values(parsed)
        staged_dir = Path(self.output_dir) / "model_integration" / role
        staged_dir.mkdir(parents=True, exist_ok=True)
        staged_path = staged_dir / source_path.name
        staged_path.write_text(json.dumps(rendered, ensure_ascii=True, indent=2) + "\n", encoding="utf-8")
        return {
            "host_path": str(staged_path),
            "mount_path": MODEL_CONFIG_JSON_MOUNT_PATH_TEMPLATE.format(role=role),
            "destination": destination_path,
        }

    def _resolve_model_integration_source_path(self, source_spec: str) -> Path:
        if source_spec.startswith("target:"):
            if not self.target_config_path:
                raise ValueError("model_integration.config_json source with target: requires target_config_path")
            base = Path(self.target_config_path).resolve().parent
            path = base / source_spec[len("target:"):]
        elif source_spec.startswith("repo:"):
            path = REPO_ROOT / source_spec[len("repo:"):]
        elif source_spec.startswith("abs:"):
            path = Path(source_spec[len("abs:"):])
        else:
            raise ValueError("model_integration.config_json source must start with target:, repo:, or abs:")
        resolved = path.resolve()
        if not resolved.is_file():
            raise ValueError(f"model_integration.config_json source does not exist: {resolved}")
        return resolved

    def _expand_model_integration_destination(self, destination_spec: str, runtime_env: dict[str, str]) -> str:
        text = destination_spec.strip()
        if not text:
            raise ValueError("model_integration.config_json destination is required")
        if text.startswith("/"):
            return text
        root, _, remainder = text.partition("/")
        if root not in _SYMBOLIC_DESTINATION_ROOTS:
            raise ValueError(
                "model_integration.config_json destination must start with one of "
                + ", ".join(f"{name}/" for name in sorted(_SYMBOLIC_DESTINATION_ROOTS))
            )
        base = _SYMBOLIC_DESTINATION_ROOTS[root](runtime_env).strip()
        if not base:
            raise ValueError(f"model_integration.config_json destination root is unavailable: {root}")
        return f"{base.rstrip('/')}/{remainder}" if remainder else base

    def _create_attacker(self) -> tuple[AttackerBase | None, AttackerContext | None]:
        attacker_spec = self.bundle.attacker
        attacker_instruction_path = self.bundle.attacker_instruction_path
        if (
            self.skip_attacker
            or attacker_spec is None
            or not attacker_spec.enabled
            or not attacker_instruction_path
            or not attacker_spec.cmd
        ):
            return None, None

        output_dir = self._workspace_manager.ensure_attacker_output(
            self.run_id,
            attacker_spec.name,
            attacker_spec.phase,
            1,
        )
        control_output_dir = ""
        if attacker_spec.target_control_plane and self._control_manager.enabled():
            self._control_manager.ensure_layout()
            control_output_dir = self._control_manager.ensure_attacker_output(
                attacker_spec.name,
                attacker_spec.phase,
                1,
            )
        input_workspace_mount = "/workspace/.openart_input_workspace"
        control_input_mount = "/workspace/.openart_target_control_input"
        control_output_mount = "/workspace/.openart_target_control_output"
        feedback_mount = "/workspace/.openart_feedback"

        container_spec = ContainerSpec(
            name=f"openart-attacker-{self.run_id}",
            image=attacker_spec.image or DEFAULT_RUNNER_IMAGES["generic_cli"],
            command=["tail", "-f", "/dev/null"],
            env=self._runtime_service_env(),
            working_dir="/workspace",
            lifecycle_log_path=str(Path(self.output_dir) / "runtime.log"),
        )
        task_root = Path(self.bundle.root_dir)
        container_spec.mounts.append(MountSpec(host_path=str(task_root), container_path="/task", read_only=True))
        attacker_config_path = str(self.bundle.metadata.get("attacker_config", "") or "").strip()
        if attacker_config_path:
            attacker_config_dir = str(Path(attacker_config_path).resolve().parent)
            container_spec.mounts.append(MountSpec(host_path=attacker_config_dir, container_path="/attacker_config", read_only=True))
        container_spec.mounts.append(MountSpec(host_path=output_dir, container_path="/workspace", read_only=False))
        container_spec.mounts.append(MountSpec(host_path=str(self._workspace_manager.shared_dir(self.run_id)), container_path=input_workspace_mount, read_only=True))
        container_spec.mounts.append(MountSpec(host_path=str(Path(self.output_dir).resolve()), container_path=feedback_mount, read_only=True))
        if attacker_spec.target_control_plane and self._control_manager.enabled():
            container_spec.mounts.append(MountSpec(host_path=str(self._control_manager.base_dir()), container_path=control_input_mount, read_only=True))
            container_spec.mounts.append(MountSpec(host_path=control_output_dir, container_path=control_output_mount, read_only=False))
        container = RunnerContainer(container_spec)

        runtime_env = self._runtime_service_env()
        resolved_vector_permissions = attacker_spec.resolved_vector_permissions(self._control_manager.provider)
        target_tool_names = [tool.name for tool in _parse_tool_specs((self.target_config or {}).get("tools"))]
        runtime_env["HOME"] = f"/tmp/openart/attackers/{attacker_spec.name}/home"
        runtime_env["XDG_CONFIG_HOME"] = f"/tmp/openart/attackers/{attacker_spec.name}/config"
        runtime_env["OPENART_ATTACKER_STATE_DIR"] = f"/tmp/openart/attackers/{attacker_spec.name}/state"
        runtime_env["OPENART_ATTACK_PHASE"] = attacker_spec.phase
        runtime_env["OPENART_TASK_DIR"] = "/task"
        runtime_env["OPENART_SHARED_WORKSPACE_DIR"] = input_workspace_mount
        runtime_env["OPENART_INPUT_WORKSPACE_DIR"] = input_workspace_mount
        runtime_env["OPENART_OUTPUT_WORKSPACE_DIR"] = "/workspace"
        runtime_env["OPENART_FEEDBACK_DIR"] = feedback_mount
        runtime_env["OPENART_TRACE_FILE"] = f"{feedback_mount}/trace.jsonl"
        runtime_env["OPENART_EVALUATOR_INPUTS_DIR"] = f"{feedback_mount}/evaluator_inputs"
        runtime_env["OPENART_EVALUATOR_OUTPUTS_DIR"] = f"{feedback_mount}/evaluator_outputs"
        runtime_env["OPENART_TARGET_RUNNER_OUTPUTS_DIR"] = f"{feedback_mount}/runner_outputs/target"
        runtime_env["OPENART_EVALUATION_ITERATIONS_DIR"] = f"{feedback_mount}/evaluation_iterations"
        runtime_env["OPENART_ATTACKER_HISTORY_DIR"] = f"{feedback_mount}/attacker_outputs/{attacker_spec.name}"
        runtime_env["OPENART_ATTACKER_GUIDANCE_FILE"] = f"{feedback_mount}/attacker_feedback_guidance.json"
        runtime_env["OPENART_TARGET_CONTROL_MANIFEST_FILE"] = (
            f"{feedback_mount}/control/target/base/.openart-target-control-manifest.json"
        )
        runtime_env["OPENART_ATTACKER_VECTOR_PERMISSIONS"] = json.dumps(list(resolved_vector_permissions), ensure_ascii=True)
        runtime_env["OPENART_TARGET_TOOL_NAMES"] = json.dumps(target_tool_names, ensure_ascii=True)
        if self._control_manager.provider is not None:
            runtime_env["OPENART_TARGET_CONTROL_DEFAULT_VECTORS"] = json.dumps(
                list(self._control_manager.provider.default_attacker_vectors),
                ensure_ascii=True,
            )
            runtime_env["OPENART_TARGET_CONTROL_AVAILABLE_VECTORS"] = json.dumps(
                sorted(self._control_manager.provider.attacker_vector_patterns),
                ensure_ascii=True,
            )
        if attacker_spec.target_control_plane and self._control_manager.enabled():
            runtime_env["OPENART_INPUT_TARGET_CONTROL_DIR"] = control_input_mount
            runtime_env["OPENART_OUTPUT_TARGET_CONTROL_DIR"] = control_output_mount

        for key, source in attacker_spec.env_from.items():
            runtime_env[key] = os.environ.get(source, "")
        runtime_env.update(attacker_spec.env)

        target_instruction_path = self._container_task_path(self.bundle.target_instruction_path) or self.bundle.target_instruction_path
        attacker_instruction_container_path = self._container_task_path(attacker_instruction_path) or attacker_instruction_path
        runtime_env["OPENART_TARGET_INSTRUCTION_FILE"] = target_instruction_path
        runtime_env["OPENART_ATTACKER_INSTRUCTION_FILE"] = attacker_instruction_container_path

        attacker = GenericCommandAttacker(
            spec=attacker_spec,
            container=container,
            tools=_parse_tool_specs(attacker_spec.tools),
            runtime_env=runtime_env,
            artifact_dir=self.output_dir,
            trace_sink=self.trace_sink,
        )
        context = AttackerContext(
            run_id=self.run_id,
            attacker_name=attacker_spec.name,
            phase=attacker_spec.phase,
            task_dir="/task",
            target_instruction_file=target_instruction_path,
            attacker_instruction_file=attacker_instruction_container_path,
            shared_workspace_dir=input_workspace_mount,
            input_workspace_dir=input_workspace_mount,
            output_workspace_dir="/workspace",
            input_target_control_dir=control_input_mount if attacker_spec.target_control_plane and self._control_manager.enabled() else "",
            output_target_control_dir=control_output_mount if attacker_spec.target_control_plane and self._control_manager.enabled() else "",
            feedback_dir=feedback_mount,
            trace_file=f"{feedback_mount}/trace.jsonl",
            evaluator_inputs_dir=f"{feedback_mount}/evaluator_inputs",
            evaluator_outputs_dir=f"{feedback_mount}/evaluator_outputs",
            target_runner_outputs_dir=f"{feedback_mount}/runner_outputs/target",
            evaluation_iterations_dir=f"{feedback_mount}/evaluation_iterations",
            attacker_history_dir=f"{feedback_mount}/attacker_outputs/{attacker_spec.name}",
            vector_permissions=resolved_vector_permissions,
            env=dict(runtime_env),
        )
        return attacker, context

    # =========================================================================
    # EVALUATOR
    # =========================================================================

    def _create_evaluator(self, task_container: TaskContainer) -> EvaluatorBase:
        """Create evaluator based on bundle configuration."""
        runtime_env = self._runtime_service_env()
        runtime_env.update(self.evaluator_env)

        deterministic: EvaluatorBase | None = None
        if self.bundle.deterministic_eval_path:
            container_rules_module = self._container_rules_module_path(self.bundle.deterministic_eval_path)
            container_harness_path = self._container_harness_path(self.evaluator_harness)
            deterministic = DeterministicEvaluator(
                self.bundle.deterministic_eval_path,
                harness_path=self.evaluator_harness,
                runtime_env=runtime_env,
                task_container=task_container,
                container_rules_module=container_rules_module,
                container_harness_path=container_harness_path,
            )

        llm_judge: EvaluatorBase | None = None
        if self.bundle.judge_rubric_path:
            judge_api_key = first_non_empty(
                os.environ.get("JUDGE_API_KEY", ""),
                os.environ.get("OPENAI_API_KEY", ""),
                os.environ.get("ANTHROPIC_API_KEY", ""),
                os.environ.get("OPENAI_KEY", ""),
            )
            judge_base_url = first_non_empty(
                os.environ.get("JUDGE_BASE_URL", ""),
                os.environ.get("OPENAI_BASE_URL", ""),
                os.environ.get("ANTHROPIC_BASE_URL", ""),
            )
            judge_model = first_non_empty(
                os.environ.get("JUDGE_MODEL", ""),
                os.environ.get("OPENAI_MODEL", ""),
                os.environ.get("DEFAULT_MODEL", ""),
                "gpt-4.1-mini",
            )

            if judge_base_url and judge_api_key:
                llm_judge = LLMJudgeEvaluator(
                    judge_model=judge_model,
                    base_url=judge_base_url,
                    api_key=judge_api_key,
                    rubric_path=self.bundle.judge_rubric_path,
                    artifact_dir=self.output_dir,
                )

        strategy = self.eval_strategy
        if strategy == "deterministic":
            return deterministic or _DummyEvaluator(self.bundle.task_id)
        if strategy == "llm":
            return llm_judge or _DummyEvaluator(self.bundle.task_id)

        if strategy == "both":
            evaluators = [e for e in (deterministic, llm_judge) if e is not None]
            if len(evaluators) == 2:
                first = evaluators[0]
                second = evaluators[1]
                composed: list[EvaluatorBase] = [first, second]
                return CompositeEvaluator(evaluators=composed)
            if len(evaluators) == 1:
                return evaluators[0]
            return _DummyEvaluator(self.bundle.task_id)

        if deterministic and llm_judge:
            combined: list[EvaluatorBase] = [deterministic, llm_judge]
            return CompositeEvaluator(evaluators=combined)
        if deterministic:
            return deterministic
        if llm_judge:
            return llm_judge
        return _DummyEvaluator(self.bundle.task_id)

    def _container_seed_dir(self) -> str | None:
        seed_dir = self.bundle.seed_dir_path
        if not seed_dir:
            return None

        return self._container_task_path(seed_dir)

    def _container_task_path(self, path_value: str | None) -> str | None:
        if not path_value:
            return None
        path = Path(path_value)
        task_root = Path(self.bundle.root_dir)
        try:
            rel = path.relative_to(task_root)
        except Exception:
            return None
        return f"/task/{rel.as_posix()}"

    def _container_rules_module_path(self, rules_module_path: str) -> str:
        return self._container_task_path(rules_module_path) or rules_module_path

    def _container_harness_path(self, harness_path: str | None) -> str | None:
        if not harness_path:
            return None

        return "/harness"

    def _runtime_service_env(self) -> dict[str, str]:
        env = build_service_runtime_env(
            required_services=self.bundle.required_services,
            service_config=self.service_config,
            get_credentials=self._get_service_credentials,
            evaluator_harness=bool(self.evaluator_harness),
            overrides=self._service_endpoint_overrides,
        )
        for key in (
            "HTTP_PROXY",
            "HTTPS_PROXY",
            "ALL_PROXY",
            "NO_PROXY",
            "http_proxy",
            "https_proxy",
            "all_proxy",
            "no_proxy",
        ):
            value = os.environ.get(key, "")
            if value:
                env[key] = value
        return env


class _DummyEvaluator(EvaluatorBase):
    """Dummy evaluator that returns unknown result."""

    def __init__(self, task_id: str) -> None:
        super().__init__(name="dummy")
        self.task_id = task_id

    def evaluate(
        self,
        run_id: str,
        trace_file: str,
        task_snapshot: dict[str, Any],
        service_snapshots: dict[str, dict],
    ):
        from framework.models.specs import EvaluatorResult
        return EvaluatorResult(
            run_id=run_id,
            decision="unknown",
            score=0.0,
            rationale="No evaluator configured: deterministic_eval missing and LLM judge unavailable.",
            metadata={"task_id": self.task_id},
        )
def _first_resolved_value(*values: Any) -> str:
    for value in values:
        text = resolve_env_value(value)
        if text:
            return text
    return ""


def _parse_tool_specs(raw_tools: Any) -> list[ToolSpec]:
    if not isinstance(raw_tools, list):
        return []

    result: list[ToolSpec] = []
    for item in raw_tools:
        if isinstance(item, str):
            result.append(ToolSpec(name=item, enabled=True, config={}))
            continue
        if isinstance(item, dict):
            name = str(item.get("name", "")).strip()
            if not name:
                continue
            enabled = bool(item.get("enabled", True))
            description = str(item.get("description", "") or "")
            command = resolve_env_value(item.get("command")) or None
            args = [resolve_env_value(arg) for arg in item.get("args", [])] if isinstance(item.get("args"), list) else []
            raw_env = item.get("env") if isinstance(item.get("env"), dict) else {}
            env = {str(key): resolve_env_value(value) for key, value in raw_env.items() if str(key).strip()}
            raw_env_from = item.get("env_from") if isinstance(item.get("env_from"), dict) else {}
            env_from = {str(key): str(value) for key, value in raw_env_from.items() if str(key).strip() and str(value).strip()}
            usage = str(item.get("usage", "") or "")
            source_root = str(item.get("source_root", "") or "")
            raw_config = item.get("config")
            config_payload: dict[str, Any]
            if isinstance(raw_config, dict):
                config_payload = {str(key): value for key, value in raw_config.items()}
            else:
                config_payload = {}
            result.append(
                ToolSpec(
                    name=name,
                    enabled=enabled,
                    description=description,
                    command=command,
                    args=args,
                    env=env,
                    env_from=env_from,
                    usage=usage,
                    source_root=source_root,
                    config=config_payload,
                )
            )
    return result


def _parse_mcp_server_specs(raw_servers: Any) -> list[MCPServerSpec]:
    if not isinstance(raw_servers, list):
        return []

    result: list[MCPServerSpec] = []
    for item in raw_servers:
        if isinstance(item, str):
            name = item.strip()
            if not name:
                continue
            result.append(MCPServerSpec(name=name, transport="stdio", command=name, args=[], env={}, enabled=True))
            continue

        if isinstance(item, dict):
            name = str(item.get("name", "")).strip()
            if not name:
                continue
            transport = str(item.get("transport", "stdio")).strip().lower() or "stdio"
            command = resolve_env_value(item.get("command")) or None
            args = [str(arg) for arg in item.get("args", [])] if isinstance(item.get("args"), list) else []
            url = resolve_env_value(item.get("url")) or None
            raw_env_data = item.get("env")
            env_data: dict[Any, Any]
            if isinstance(raw_env_data, dict):
                env_data = raw_env_data
            else:
                env_data = {}
            env = {str(k): resolve_env_value(v) for k, v in env_data.items()}
            enabled = bool(item.get("enabled", True))
            result.append(
                MCPServerSpec(
                    name=name,
                    transport=transport,
                    command=command,
                    args=args,
                    url=url,
                    env=env,
                    enabled=enabled,
                )
            )
    return result


def _parse_skill_specs(raw_skills: Any) -> list[SkillSpec]:
    if not isinstance(raw_skills, list):
        return []

    result: list[SkillSpec] = []
    for item in raw_skills:
        if isinstance(item, str):
            name = item.strip()
            if name:
                result.append(SkillSpec(name=name, description="", config={}))
            continue

        if isinstance(item, dict):
            name = str(item.get("name", "")).strip()
            if not name:
                continue
            description = str(item.get("description", ""))
            raw_config = item.get("config")
            config_payload: dict[str, Any]
            if isinstance(raw_config, dict):
                config_payload = {str(key): value for key, value in raw_config.items()}
            else:
                config_payload = {}
            result.append(SkillSpec(name=name, description=description, config=config_payload))
    return result

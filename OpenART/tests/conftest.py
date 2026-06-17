"""Shared fixtures for OpenART tests."""
from __future__ import annotations

import json
import os
import subprocess
import time
import uuid
from pathlib import Path

import pytest

from framework.attackers.models import AttackerSpec
from framework.models.common import (
    CommandSpec,
    ContainerState,
    CredentialBundle,
    Endpoint,
    EvaluatorDecision,
    RunnerRole,
    SkillSpec,
    ToolSpec,
    TraceEventType,
)
from framework.models.specs import (
    EvaluatorResult,
    TraceEvent,
)
from framework.models.container import ContainerSpec, HealthcheckSpec, MountSpec, PortSpec
from framework.models.task import TaskBundleSpec


# ============================================================================
# Basic Model Fixtures
# ============================================================================

@pytest.fixture
def sample_credential_bundle() -> CredentialBundle:
    """Create a sample CredentialBundle."""
    return CredentialBundle(values={"api_key": "test-key-123", "token": "abc456"})


@pytest.fixture
def sample_endpoint() -> Endpoint:
    """Create a sample Endpoint."""
    return Endpoint(name="test-endpoint", url="http://localhost:8080", metadata={"version": "1.0"})


@pytest.fixture
def sample_command_spec() -> CommandSpec:
    """Create a sample CommandSpec."""
    return CommandSpec(template="echo {message}", shell="/bin/bash", timeout_seconds=60)


@pytest.fixture
def sample_tool_spec() -> ToolSpec:
    """Create a sample ToolSpec."""
    return ToolSpec(name="test-tool", enabled=True, config={"timeout": 30})


@pytest.fixture
def sample_skill_spec() -> SkillSpec:
    """Create a sample SkillSpec."""
    return SkillSpec(name="test-skill", description="A test skill", config={"param": "value"})


# ============================================================================
# Container Model Fixtures
# ============================================================================

@pytest.fixture
def sample_mount_spec() -> MountSpec:
    """Create a sample MountSpec."""
    return MountSpec(host_path="/host/path", container_path="/container/path", read_only=False)


@pytest.fixture
def sample_port_spec() -> PortSpec:
    """Create a sample PortSpec with host port."""
    return PortSpec(host_port=8080, container_port=80, protocol="tcp")


@pytest.fixture
def sample_port_spec_no_host() -> PortSpec:
    """Create a sample PortSpec without host port."""
    return PortSpec(host_port=None, container_port=443, protocol="tcp")


@pytest.fixture
def sample_healthcheck_spec() -> HealthcheckSpec:
    """Create a sample HealthcheckSpec."""
    return HealthcheckSpec(
        command=["curl", "-f", "http://localhost/health"],
        interval_seconds=30,
        timeout_seconds=10,
        retries=3,
    )


@pytest.fixture
def sample_container_spec() -> ContainerSpec:
    """Create a sample ContainerSpec with all fields."""
    return ContainerSpec(
        name="test-container",
        image="alpine:latest",
        command=["sleep", "infinity"],
        env={"FOO": "bar", "BAZ": "qux"},
        mounts=[MountSpec(host_path="/tmp", container_path="/data", read_only=False)],
        ports=[PortSpec(host_port=8080, container_port=80, protocol="tcp")],
        network="bridge",
        working_dir="/app",
        healthcheck=HealthcheckSpec(command=["echo", "ok"], interval_seconds=10),
    )


@pytest.fixture
def minimal_container_spec() -> ContainerSpec:
    """Create a minimal ContainerSpec."""
    return ContainerSpec(name="minimal-container")


# ============================================================================
# Task Fixtures
# ============================================================================

@pytest.fixture
def sample_task_bundle_spec() -> TaskBundleSpec:
    """Create a sample TaskBundleSpec."""
    return TaskBundleSpec(
        task_id="task-001",
        name="Test Task",
        root_dir="/tasks/test",
        dockerfile="Dockerfile",
        context_dir=".",
        target_instruction="Solve the problem",
        attacker=AttackerSpec(
            name="sample-attacker",
            instruction="Exploit the vulnerability",
            cmd="python3",
            args=["attacker.py"],
        ),
        required_services=["database"],
        extra_services=["cache"],
        seed_dir="/seeds",
        deterministic_eval="exact_match",
        judge_rubric="Check for correctness",
        timeout_seconds=3600,
    )


@pytest.fixture
def minimal_task_bundle_spec() -> TaskBundleSpec:
    """Create a minimal TaskBundleSpec."""
    return TaskBundleSpec(
        task_id="minimal-task",
        name="Minimal Task",
        root_dir="/tasks/minimal",
        dockerfile="Dockerfile",
        context_dir=".",
        target_instruction="Do something",
    )


# ============================================================================
# Trace Event Fixtures
# ============================================================================

@pytest.fixture
def sample_trace_event() -> TraceEvent:
    """Create a sample TraceEvent."""
    return TraceEvent(
        run_id="run-001",
        source_role="target",
        event_type="message",
        timestamp=1234567890.123,
        message="Test message",
        payload={"key": "value"},
    )


@pytest.fixture
def minimal_trace_event() -> TraceEvent:
    """Create a minimal TraceEvent with defaults."""
    return TraceEvent(
        run_id="run-001",
        source_role="target",
        event_type="run_start",
        timestamp=1234567890.0,
    )


# ============================================================================
# Evaluator Result Fixtures
# ============================================================================

@pytest.fixture
def sample_evaluator_result() -> EvaluatorResult:
    """Create a sample EvaluatorResult."""
    return EvaluatorResult(
        run_id="run-001",
        decision="pass",
        score=0.95,
        subscores={"accuracy": 0.9, "completeness": 1.0},
        rationale="All checks passed",
        artifacts={"log": "/logs/run-001.log"},
        metadata={"evaluator": "llm-judge", "model": "claude-3"},
    )


@pytest.fixture
def minimal_evaluator_result() -> EvaluatorResult:
    """Create a minimal EvaluatorResult."""
    return EvaluatorResult(run_id="run-001", decision="fail", score=0.0)


# ============================================================================
# File-based Fixtures
# ============================================================================

@pytest.fixture
def tmp_trace_file(tmp_path: Path) -> Path:
    """Create a temporary trace file path."""
    return tmp_path / "traces" / "test_trace.jsonl"


@pytest.fixture
def sample_trace_file(tmp_path: Path) -> Path:
    """Create a sample trace file with multiple events."""
    trace_file = tmp_path / "sample_trace.jsonl"
    events = [
        {
            "run_id": "test-001",
            "source_role": "target",
            "event_type": "run_start",
            "timestamp": 1234567890.0,
            "message": "Run started",
            "payload": {},
        },
        {
            "run_id": "test-001",
            "source_role": "target",
            "event_type": "message",
            "timestamp": 1234567891.0,
            "message": "Processing request",
            "payload": {"step": 1},
        },
        {
            "run_id": "test-001",
            "source_role": "target",
            "event_type": "tool_call",
            "timestamp": 1234567892.0,
            "message": "Executing bash",
            "payload": {"tool": "bash", "command": "ls -la"},
        },
        {
            "run_id": "test-001",
            "source_role": "target",
            "event_type": "tool_result",
            "timestamp": 1234567893.0,
            "message": "Command completed",
            "payload": {"exit_code": 0},
        },
        {
            "run_id": "test-001",
            "source_role": "target",
            "event_type": "run_end",
            "timestamp": 1234567990.0,
            "message": "Run completed",
            "payload": {"status": "success"},
        },
    ]
    trace_file.parent.mkdir(parents=True, exist_ok=True)
    with open(trace_file, "w", encoding="utf-8") as f:
        for event in events:
            f.write(json.dumps(event) + "\n")
    return trace_file


# ============================================================================
# Docker Fixtures
# ============================================================================

def docker_available() -> bool:
    """Check if Docker daemon is available and running."""
    try:
        result = subprocess.run(
            ["docker", "info"],
            capture_output=True,
            text=True,
            timeout=10,
        )
        return result.returncode == 0
    except (subprocess.SubprocessError, FileNotFoundError):
        return False


@pytest.fixture
def skip_if_no_docker():
    """Skip test if Docker is not available."""
    if not docker_available():
        pytest.skip("Docker daemon not available")


@pytest.fixture
def docker_test_container_name() -> str:
    """Generate a unique container name for testing."""
    return f"test-container-{uuid.uuid4().hex[:8]}"


@pytest.fixture
def docker_test_image_name() -> str:
    """Generate a unique image name for testing."""
    return f"test-image-{uuid.uuid4().hex[:8]}"


@pytest.fixture
def minimal_dockerfile(tmp_path: Path) -> Path:
    """Create a minimal Dockerfile for testing."""
    dockerfile = tmp_path / "Dockerfile"
    dockerfile.write_text(
        """FROM alpine:latest
RUN apk add --no-cache curl
CMD ["sleep", "infinity"]
"""
    )
    return dockerfile


@pytest.fixture
def docker_container_spec_with_build(
    tmp_path: Path,
    docker_test_container_name: str,
    docker_test_image_name: str,
    minimal_dockerfile: Path,
) -> ContainerSpec:
    """Create a ContainerSpec for building a test container."""
    return ContainerSpec(
        name=docker_test_container_name,
        image=docker_test_image_name,
        build_context=str(tmp_path),
        dockerfile=str(minimal_dockerfile),
        command=["sleep", "infinity"],
    )


@pytest.fixture
def docker_container_spec_pull(docker_test_container_name: str) -> ContainerSpec:
    """Create a ContainerSpec for pulling an image."""
    return ContainerSpec(
        name=docker_test_container_name,
        image="alpine:latest",
        command=["sleep", "60"],
    )


# ============================================================================
# Cleanup Fixtures
# ============================================================================

@pytest.fixture
def cleanup_docker_containers():
    """Cleanup any containers created during tests."""
    created_containers = []

    def register_container(name: str):
        created_containers.append(name)

    yield register_container

    # Cleanup
    for name in created_containers:
        try:
            subprocess.run(
                ["docker", "rm", "-f", name],
                capture_output=True,
                timeout=30,
            )
        except (subprocess.SubprocessError, FileNotFoundError):
            pass


@pytest.fixture
def cleanup_docker_images():
    """Cleanup any images created during tests."""
    created_images = []

    def register_image(name: str):
        created_images.append(name)

    yield register_image

    # Cleanup
    for name in created_images:
        try:
            subprocess.run(
                ["docker", "rmi", "-f", name],
                capture_output=True,
                timeout=60,
            )
        except (subprocess.SubprocessError, FileNotFoundError):
            pass

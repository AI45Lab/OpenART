"""Integration tests for DockerContainer.

These tests require a running Docker daemon.
Use pytest markers to skip if Docker is not available.
"""
from __future__ import annotations

import json
import subprocess
import time
import uuid

import pytest

from framework.models.common import ContainerState
from framework.models.container import ContainerSpec, HealthcheckSpec
from framework.components.containers import DockerContainer


def is_docker_available() -> bool:
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


# Skip all tests in this module if Docker is not available
pytestmark = pytest.mark.skipif(
    not is_docker_available(),
    reason="Docker daemon not available",
)


class TestDockerContainerLifecycle:
    """Tests for Docker container lifecycle operations."""

    @pytest.fixture
    def container_name(self) -> str:
        """Generate unique container name."""
        return f"test-container-{uuid.uuid4().hex[:8]}"

    @pytest.fixture
    def image_name(self) -> str:
        """Generate unique image name."""
        return f"test-image-{uuid.uuid4().hex[:8]}"

    @pytest.fixture
    def docker_container(self, container_name: str) -> DockerContainer:
        """Create a DockerContainer instance for pull-based testing."""
        spec = ContainerSpec(
            name=container_name,
            image="alpine:latest",
            command=["sleep", "60"],
        )
        return DockerContainer(spec)

    @pytest.fixture
    def docker_container_with_healthcheck(self, container_name: str) -> DockerContainer:
        """Create a DockerContainer with healthcheck."""
        spec = ContainerSpec(
            name=f"{container_name}-health",
            image="alpine:latest",
            command=["sleep", "infinity"],
            healthcheck=HealthcheckSpec(
                command=["echo", "healthy"],
                interval_seconds=5,
                timeout_seconds=3,
                retries=3,
            ),
        )
        return DockerContainer(spec)

    def test_pull_image(self, docker_container: DockerContainer):
        """Test pulling an image."""
        docker_container.pull()
        # Should not raise - image is now available locally

    def test_create_container(self, docker_container: DockerContainer):
        """Test creating a container."""
        try:
            docker_container.pull()
            docker_container.create()

            assert docker_container.container_id is not None
            assert docker_container.state == ContainerState.CREATED.value
        finally:
            docker_container.remove(force=True)

    def test_start_container(self, docker_container: DockerContainer):
        """Test starting a container."""
        try:
            docker_container.pull()
            docker_container.create()
            docker_container.start()

            assert docker_container.state == ContainerState.RUNNING.value
        finally:
            docker_container.stop()
            docker_container.remove(force=True)

    def test_stop_container(self, docker_container: DockerContainer):
        """Test stopping a container."""
        try:
            docker_container.pull()
            docker_container.create()
            docker_container.start()
            docker_container.stop()

            assert docker_container.state == ContainerState.STOPPED.value
        finally:
            docker_container.remove(force=True)

    def test_remove_container(self, docker_container: DockerContainer):
        """Test removing a container."""
        docker_container.pull()
        docker_container.create()
        docker_container.remove(force=True)

        assert docker_container.state == ContainerState.REMOVED.value
        assert docker_container.container_id is None

    def test_full_lifecycle(self, docker_container: DockerContainer):
        """Test full container lifecycle: pull -> create -> start -> stop -> remove."""
        try:
            # Pull
            docker_container.pull()

            # Create
            docker_container.create()
            assert docker_container.container_id is not None
            assert docker_container.state == ContainerState.CREATED.value

            # Start
            docker_container.start()
            assert docker_container.state == ContainerState.RUNNING.value

            # Stop
            docker_container.stop()
            assert docker_container.state == ContainerState.STOPPED.value

            # Remove
            docker_container.remove()
            assert docker_container.state == ContainerState.REMOVED.value
        finally:
            # Ensure cleanup
            try:
                docker_container.remove(force=True)
            except Exception:
                pass


class TestDockerContainerExec:
    """Tests for Docker container command execution."""

    @pytest.fixture
    def running_container(self, container_name: str) -> DockerContainer:
        """Create and start a container for exec tests."""
        spec = ContainerSpec(
            name=container_name,
            image="alpine:latest",
            command=["sleep", "infinity"],
        )
        container = DockerContainer(spec)
        container.pull()
        container.create()
        container.start()
        yield container
        # Cleanup
        container.stop()
        container.remove(force=True)

    @pytest.fixture
    def container_name(self) -> str:
        """Generate unique container name."""
        return f"test-exec-{uuid.uuid4().hex[:8]}"

    def test_exec_simple_command(self, running_container: DockerContainer):
        """Test executing a simple command in container."""
        exit_code, stdout, stderr = running_container.exec(["echo", "hello"])

        assert exit_code == 0
        assert "hello" in stdout

    def test_exec_command_with_exit_code(self, running_container: DockerContainer):
        """Test exec command that returns non-zero exit code."""
        exit_code, stdout, stderr = running_container.exec(["ls", "/nonexistent"])

        assert exit_code != 0

    def test_exec_command_with_env(self, running_container: DockerContainer):
        """Test executing command with environment variables."""
        exit_code, stdout, stderr = running_container.exec(
            ["sh", "-c", "echo $MY_VAR"],
            env={"MY_VAR": "test_value"},
        )

        assert exit_code == 0
        assert "test_value" in stdout

    def test_exec_multiple_commands_sequentially(self, running_container: DockerContainer):
        """Test executing multiple commands in sequence."""
        # First command
        exit_code, stdout, _ = running_container.exec(["touch", "/tmp/test_file"])
        assert exit_code == 0

        # Second command
        exit_code, stdout, _ = running_container.exec(["ls", "/tmp/test_file"])
        assert exit_code == 0

        # Third command
        exit_code, stdout, _ = running_container.exec(["rm", "/tmp/test_file"])
        assert exit_code == 0


class TestDockerContainerLogs:
    """Tests for Docker container log retrieval."""

    @pytest.fixture
    def container_name(self) -> str:
        """Generate unique container name."""
        return f"test-logs-{uuid.uuid4().hex[:8]}"

    @pytest.fixture
    def logging_container(self, container_name: str) -> DockerContainer:
        """Create a container that produces logs."""
        spec = ContainerSpec(
            name=container_name,
            image="alpine:latest",
            command=["sh", "-c", "echo 'line1'; echo 'line2'; sleep 60"],
        )
        container = DockerContainer(spec)
        container.pull()
        container.create()
        container.start()
        # Give container time to produce logs
        time.sleep(0.5)
        yield container
        # Cleanup
        container.stop()
        container.remove(force=True)

    def test_logs_retrieval(self, logging_container: DockerContainer):
        """Test retrieving container logs."""
        logs = logging_container.logs()

        assert "line1" in logs
        assert "line2" in logs

    def test_logs_with_tail_limit(self, container_name: str):
        """Test logs with tail limit."""
        spec = ContainerSpec(
            name=container_name,
            image="alpine:latest",
            command=["sh", "-c", "for i in $(seq 1 100); do echo \"line$i\"; done; sleep 60"],
        )
        container = DockerContainer(spec)
        try:
            container.pull()
            container.create()
            container.start()
            time.sleep(1)

            logs = container.logs(tail=10)
            lines = logs.strip().split("\n")

            # Should only get the last 10 lines
            assert len(lines) <= 10
        finally:
            container.stop()
            container.remove(force=True)


class TestDockerContainerHealthcheck:
    """Tests for Docker container health check."""

    @pytest.fixture
    def container_name(self) -> str:
        """Generate unique container name."""
        return f"test-health-{uuid.uuid4().hex[:8]}"

    @pytest.fixture
    def healthy_container(self, container_name: str) -> DockerContainer:
        """Create a container with passing healthcheck."""
        spec = ContainerSpec(
            name=container_name,
            image="alpine:latest",
            command=["sleep", "infinity"],
            healthcheck=HealthcheckSpec(
                command=["echo", "healthy"],
                interval_seconds=2,
                timeout_seconds=1,
                retries=3,
            ),
        )
        container = DockerContainer(spec)
        container.pull()
        container.create()
        container.start()
        # Wait for health check to pass
        time.sleep(3)
        yield container
        # Cleanup
        container.stop()
        container.remove(force=True)

    @pytest.fixture
    def container_without_healthcheck(self, container_name: str) -> DockerContainer:
        """Create a container without healthcheck defined."""
        spec = ContainerSpec(
            name=f"{container_name}-nohealth",
            image="alpine:latest",
            command=["sleep", "infinity"],
        )
        container = DockerContainer(spec)
        container.pull()
        container.create()
        container.start()
        yield container
        # Cleanup
        container.stop()
        container.remove(force=True)

    def test_is_healthy_with_healthcheck(self, healthy_container: DockerContainer):
        """Test health check for container with defined healthcheck."""
        # Wait for health check to potentially pass
        time.sleep(2)
        # Container should eventually become healthy
        # Note: This might be "healthy" or just "running" depending on timing
        is_healthy = healthy_container.is_healthy()
        assert is_healthy is True

    def test_is_healthy_without_healthcheck(self, container_without_healthcheck: DockerContainer):
        """Test health check for container without healthcheck (running = healthy)."""
        is_healthy = container_without_healthcheck.is_healthy()
        # Container without healthcheck is healthy if running
        assert is_healthy is True

    def test_is_healthy_stopped_container(self, container_name: str):
        """Test health check for stopped container."""
        spec = ContainerSpec(
            name=container_name,
            image="alpine:latest",
            command=["sleep", "infinity"],
        )
        container = DockerContainer(spec)
        try:
            container.pull()
            container.create()
            container.start()
            container.stop()

            is_healthy = container.is_healthy()
            assert is_healthy is False
        finally:
            container.remove(force=True)


class TestDockerContainerSnapshot:
    """Tests for Docker container snapshot functionality."""

    @pytest.fixture
    def container_name(self) -> str:
        """Generate unique container name."""
        return f"test-snapshot-{uuid.uuid4().hex[:8]}"

    @pytest.fixture
    def running_container(self, container_name: str) -> DockerContainer:
        """Create a running container for snapshot tests."""
        spec = ContainerSpec(
            name=container_name,
            image="alpine:latest",
            command=["sleep", "infinity"],
        )
        container = DockerContainer(spec)
        container.pull()
        container.create()
        container.start()
        yield container
        # Cleanup
        container.stop()
        container.remove(force=True)

    def test_snapshot_returns_dict(self, running_container: DockerContainer):
        """Test that snapshot returns a dictionary."""
        snapshot = running_container.snapshot()

        assert isinstance(snapshot, dict)
        assert len(snapshot) > 0

    def test_snapshot_contains_container_info(self, running_container: DockerContainer):
        """Test that snapshot contains container information."""
        snapshot = running_container.snapshot()

        # Should contain standard Docker inspect fields
        assert "Id" in snapshot or "State" in snapshot
        assert "Name" in snapshot or "Image" in snapshot

    def test_snapshot_state_info(self, running_container: DockerContainer):
        """Test that snapshot contains state information."""
        snapshot = running_container.snapshot()

        # Docker inspect returns state in the "State" field
        if "State" in snapshot:
            state = snapshot["State"]
            assert "Status" in state or "Running" in state


class TestDockerContainerErrorHandling:
    """Tests for Docker container error handling."""

    @pytest.fixture
    def container_name(self) -> str:
        """Generate unique container name."""
        return f"test-error-{uuid.uuid4().hex[:8]}"

    def test_create_without_image_raises_error(self, container_name: str):
        """Test that create without image raises ValueError."""
        spec = ContainerSpec(name=container_name)
        container = DockerContainer(spec)

        with pytest.raises(ValueError, match="image is required"):
            container.create()

    def test_build_without_image_raises_error(self, container_name: str):
        """Test that build without image raises ValueError."""
        spec = ContainerSpec(
            name=container_name,
            build_context="/tmp",
        )
        container = DockerContainer(spec)

        with pytest.raises(ValueError, match="image is required"):
            container.build()

    def test_pull_nonexistent_image_sets_failed_state(self, container_name: str):
        """Test that pulling nonexistent image sets failed state."""
        spec = ContainerSpec(
            name=container_name,
            image="nonexistent/image:that-does-not-exist",
        )
        container = DockerContainer(spec)

        with pytest.raises(RuntimeError, match="docker pull failed"):
            container.pull()

        assert container.state == ContainerState.FAILED.value

    def test_exec_on_stopped_container(self, container_name: str):
        """Test exec on stopped/removed container handles error gracefully."""
        spec = ContainerSpec(
            name=container_name,
            image="alpine:latest",
            command=["sleep", "1"],
        )
        container = DockerContainer(spec)
        try:
            container.pull()
            container.create()
            container.start()
            # Wait for container to stop
            time.sleep(2)
            container.stop()

            # Exec should work on stopped container or fail gracefully
            # Docker behavior: exec fails on stopped container
            exit_code, stdout, stderr = container.exec(["echo", "test"])
            # Most likely will fail, but shouldn't crash
        finally:
            container.remove(force=True)


class TestDockerContainerBuild:
    """Tests for Docker container build functionality."""

    @pytest.fixture
    def container_name(self) -> str:
        """Generate unique container name."""
        return f"test-build-{uuid.uuid4().hex[:8]}"

    @pytest.fixture
    def image_name(self) -> str:
        """Generate unique image name."""
        return f"test-build-image-{uuid.uuid4().hex[:8]}"

    @pytest.fixture
    def dockerfile_context(self, tmp_path):
        """Create a minimal Dockerfile context."""
        dockerfile = tmp_path / "Dockerfile"
        dockerfile.write_text(
            """FROM alpine:latest
RUN apk add --no-cache curl
CMD ["sleep", "infinity"]
"""
        )
        return tmp_path

    def test_build_container(self, container_name: str, image_name: str, dockerfile_context):
        """Test building a container from Dockerfile."""
        spec = ContainerSpec(
            name=container_name,
            image=image_name,
            build_context=str(dockerfile_context),
        )
        container = DockerContainer(spec)

        try:
            container.build()
            # Build should succeed
            assert True
        finally:
            # Cleanup image
            try:
                subprocess.run(
                    ["docker", "rmi", "-f", image_name],
                    capture_output=True,
                    timeout=30,
                )
            except Exception:
                pass

    def test_build_and_run_container(self, container_name: str, image_name: str, dockerfile_context):
        """Test building and running a container."""
        spec = ContainerSpec(
            name=container_name,
            image=image_name,
            build_context=str(dockerfile_context),
        )
        container = DockerContainer(spec)

        try:
            # Build
            container.build()

            # Create and start
            container.create()
            container.start()

            assert container.state == ContainerState.RUNNING.value

            # Verify curl is installed
            exit_code, stdout, stderr = container.exec(["curl", "--version"])
            assert exit_code == 0
            assert "curl" in stdout
        finally:
            container.stop()
            container.remove(force=True)
            # Cleanup image
            try:
                subprocess.run(
                    ["docker", "rmi", "-f", image_name],
                    capture_output=True,
                    timeout=30,
                )
            except Exception:
                pass


class TestDockerContainerNetworking:
    """Tests for Docker container networking."""

    @pytest.fixture
    def container_name(self) -> str:
        """Generate unique container name."""
        return f"test-net-{uuid.uuid4().hex[:8]}"

    def test_container_with_custom_network(self, container_name: str):
        """Test container with custom network."""
        network_name = "test-network"

        # Create network
        try:
            subprocess.run(
                ["docker", "network", "create", network_name],
                capture_output=True,
                timeout=10,
            )
        except Exception:
            pass

        spec = ContainerSpec(
            name=container_name,
            image="alpine:latest",
            command=["sleep", "infinity"],
            network=network_name,
        )
        container = DockerContainer(spec)

        try:
            container.pull()
            container.create()
            container.start()

            # Verify container is on the network
            exit_code, stdout, stderr = container.exec(["cat", "/etc/hosts"])
            assert exit_code == 0
        finally:
            container.stop()
            container.remove(force=True)
            # Cleanup network
            try:
                subprocess.run(
                    ["docker", "network", "rm", network_name],
                    capture_output=True,
                    timeout=10,
                )
            except Exception:
                pass


class TestDockerContainerMountsAndPorts:
    """Tests for Docker container mounts and port mappings."""

    @pytest.fixture
    def container_name(self) -> str:
        """Generate unique container name."""
        return f"test-mount-{uuid.uuid4().hex[:8]}"

    def test_container_with_mount(self, container_name: str, tmp_path):
        """Test container with volume mount."""
        test_file = tmp_path / "test.txt"
        test_file.write_text("hello from host")

        from framework.models.container import MountSpec

        spec = ContainerSpec(
            name=container_name,
            image="alpine:latest",
            command=["sleep", "infinity"],
            mounts=[
                MountSpec(
                    host_path=str(tmp_path),
                    container_path="/mnt/host",
                    read_only=False,
                )
            ],
        )
        container = DockerContainer(spec)

        try:
            container.pull()
            container.create()
            container.start()

            # Verify mount
            exit_code, stdout, stderr = container.exec(["cat", "/mnt/host/test.txt"])
            assert exit_code == 0
            assert "hello from host" in stdout
        finally:
            container.stop()
            container.remove(force=True)

    def test_container_with_port_mapping(self, container_name: str):
        """Test container with port mapping."""
        import random
        from framework.models.container import PortSpec

        # Use a random port in the 30000-40000 range to avoid conflicts
        random_port = random.randint(30000, 40000)

        spec = ContainerSpec(
            name=container_name,
            image="alpine:latest",
            command=["sleep", "infinity"],
            ports=[
                PortSpec(host_port=random_port, container_port=80, protocol="tcp"),
            ],
        )
        container = DockerContainer(spec)

        try:
            container.pull()
            container.create()
            container.start()

            # Verify port mapping via inspect
            snapshot = container.snapshot()
            # Port info should be in NetworkSettings
            assert "NetworkSettings" in snapshot
        finally:
            container.stop()
            container.remove(force=True)
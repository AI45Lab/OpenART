"""Unit tests for container model classes."""
from __future__ import annotations

import pytest

from framework.models.container import ContainerSpec, HealthcheckSpec, MountSpec, PortSpec


class TestMountSpec:
    """Tests for MountSpec dataclass."""

    def test_mount_spec_creation(self, sample_mount_spec: MountSpec):
        """Test MountSpec creation with all fields."""
        assert sample_mount_spec.host_path == "/host/path"
        assert sample_mount_spec.container_path == "/container/path"
        assert sample_mount_spec.read_only is False

    def test_mount_spec_read_only(self):
        """Test MountSpec with read_only flag."""
        mount = MountSpec(host_path="/host/ro", container_path="/container/ro", read_only=True)
        assert mount.read_only is True

    def test_mount_spec_defaults(self):
        """Test MountSpec default values."""
        mount = MountSpec(host_path="/host", container_path="/container")
        assert mount.read_only is False


class TestPortSpec:
    """Tests for PortSpec dataclass."""

    def test_port_spec_with_host_port(self, sample_port_spec: PortSpec):
        """Test PortSpec with host port specified."""
        assert sample_port_spec.host_port == 8080
        assert sample_port_spec.container_port == 80
        assert sample_port_spec.protocol == "tcp"

    def test_port_spec_without_host_port(self, sample_port_spec_no_host: PortSpec):
        """Test PortSpec without host port."""
        assert sample_port_spec_no_host.host_port is None
        assert sample_port_spec_no_host.container_port == 443
        assert sample_port_spec_no_host.protocol == "tcp"

    def test_port_spec_defaults(self):
        """Test PortSpec default values."""
        port = PortSpec(host_port=None, container_port=3000)
        assert port.protocol == "tcp"

    def test_port_spec_udp_protocol(self):
        """Test PortSpec with UDP protocol."""
        port = PortSpec(host_port=53, container_port=53, protocol="udp")
        assert port.protocol == "udp"


class TestHealthcheckSpec:
    """Tests for HealthcheckSpec dataclass."""

    def test_healthcheck_spec_creation(self, sample_healthcheck_spec: HealthcheckSpec):
        """Test HealthcheckSpec creation with all fields."""
        assert sample_healthcheck_spec.command == ["curl", "-f", "http://localhost/health"]
        assert sample_healthcheck_spec.interval_seconds == 30
        assert sample_healthcheck_spec.timeout_seconds == 10
        assert sample_healthcheck_spec.retries == 3

    def test_healthcheck_spec_defaults(self):
        """Test HealthcheckSpec default values."""
        health = HealthcheckSpec(command=["echo", "ok"])
        assert health.command == ["echo", "ok"]
        assert health.interval_seconds == 10
        assert health.timeout_seconds == 5
        assert health.retries == 6

    def test_healthcheck_spec_custom_values(self):
        """Test HealthcheckSpec with custom values."""
        health = HealthcheckSpec(
            command=["python", "health.py"],
            interval_seconds=60,
            timeout_seconds=30,
            retries=5,
        )
        assert health.interval_seconds == 60
        assert health.timeout_seconds == 30
        assert health.retries == 5


class TestContainerSpec:
    """Tests for ContainerSpec dataclass."""

    def test_container_spec_with_required_fields(self):
        """Test ContainerSpec creation with only required fields."""
        spec = ContainerSpec(name="test-container")
        assert spec.name == "test-container"
        assert spec.image is None
        assert spec.build_context is None
        assert spec.dockerfile is None
        assert spec.command is None
        assert spec.env == {}
        assert spec.mounts == []
        assert spec.ports == []
        assert spec.network is None
        assert spec.working_dir is None
        assert spec.healthcheck is None
        assert spec.lifecycle_log_path is None

    def test_container_spec_with_all_fields(self, sample_container_spec: ContainerSpec):
        """Test ContainerSpec creation with all fields."""
        assert sample_container_spec.name == "test-container"
        assert sample_container_spec.image == "alpine:latest"
        assert sample_container_spec.command == ["sleep", "infinity"]
        assert sample_container_spec.env == {"FOO": "bar", "BAZ": "qux"}
        assert len(sample_container_spec.mounts) == 1
        assert len(sample_container_spec.ports) == 1
        assert sample_container_spec.network == "bridge"
        assert sample_container_spec.working_dir == "/app"
        assert sample_container_spec.healthcheck is not None

    def test_container_spec_minimal(self, minimal_container_spec: ContainerSpec):
        """Test minimal ContainerSpec."""
        assert minimal_container_spec.name == "minimal-container"
        assert minimal_container_spec.image is None

    def test_container_spec_with_image(self):
        """Test ContainerSpec with image only."""
        spec = ContainerSpec(name="test", image="nginx:latest")
        assert spec.image == "nginx:latest"
        assert spec.build_context is None

    def test_container_spec_with_build_context(self):
        """Test ContainerSpec with build context."""
        spec = ContainerSpec(
            name="test",
            image="custom:latest",
            build_context="/app",
            dockerfile="Dockerfile.custom",
        )
        assert spec.build_context == "/app"
        assert spec.dockerfile == "Dockerfile.custom"

    def test_container_spec_env_dict(self):
        """Test ContainerSpec environment variables."""
        spec = ContainerSpec(
            name="test",
            env={"KEY1": "value1", "KEY2": "value2"},
        )
        assert spec.env["KEY1"] == "value1"
        assert spec.env["KEY2"] == "value2"

    def test_container_spec_multiple_mounts(self):
        """Test ContainerSpec with multiple mounts."""
        mounts = [
            MountSpec(host_path="/data", container_path="/data", read_only=False),
            MountSpec(host_path="/config", container_path="/config", read_only=True),
        ]
        spec = ContainerSpec(name="test", mounts=mounts)
        assert len(spec.mounts) == 2
        assert spec.mounts[0].read_only is False
        assert spec.mounts[1].read_only is True

    def test_container_spec_multiple_ports(self):
        """Test ContainerSpec with multiple ports."""
        ports = [
            PortSpec(host_port=80, container_port=80, protocol="tcp"),
            PortSpec(host_port=443, container_port=443, protocol="tcp"),
            PortSpec(host_port=None, container_port=8080, protocol="tcp"),
        ]
        spec = ContainerSpec(name="test", ports=ports)
        assert len(spec.ports) == 3
        assert spec.ports[2].host_port is None

    def test_container_spec_network(self):
        """Test ContainerSpec with network."""
        spec = ContainerSpec(name="test", network="host")
        assert spec.network == "host"

    def test_container_spec_working_dir(self):
        """Test ContainerSpec with working directory."""
        spec = ContainerSpec(name="test", working_dir="/app/src")
        assert spec.working_dir == "/app/src"

    def test_container_spec_command(self):
        """Test ContainerSpec with command."""
        spec = ContainerSpec(name="test", command=["python", "app.py"])
        assert spec.command == ["python", "app.py"]

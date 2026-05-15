"""Unit tests for common model classes and enums."""
from __future__ import annotations

import pytest

from framework.models.common import (
    CommandSpec,
    ContainerState,
    CredentialBundle,
    Endpoint,
    EvaluatorDecision,
    MCPServerSpec,
    RunnerRole,
    SkillSpec,
    ToolSpec,
    TraceEventType,
)


class TestCredentialBundle:
    """Tests for CredentialBundle dataclass."""

    def test_require_returns_value(self, sample_credential_bundle: CredentialBundle):
        """Test that require() returns the correct value for existing key."""
        assert sample_credential_bundle.require("api_key") == "test-key-123"
        assert sample_credential_bundle.require("token") == "abc456"

    def test_require_raises_keyerror_for_missing_key(self, sample_credential_bundle: CredentialBundle):
        """Test that require() raises KeyError for missing keys."""
        with pytest.raises(KeyError, match="Missing credential: nonexistent"):
            sample_credential_bundle.require("nonexistent")

    def test_empty_credential_bundle(self):
        """Test CredentialBundle with no credentials."""
        bundle = CredentialBundle()
        assert bundle.values == {}
        with pytest.raises(KeyError):
            bundle.require("any_key")

    def test_credential_bundle_with_values(self):
        """Test CredentialBundle initialization with values."""
        bundle = CredentialBundle(values={"key1": "val1", "key2": "val2"})
        assert bundle.require("key1") == "val1"
        assert bundle.require("key2") == "val2"


class TestEndpoint:
    """Tests for Endpoint dataclass."""

    def test_endpoint_creation_with_defaults(self):
        """Test Endpoint creation with default metadata."""
        endpoint = Endpoint(name="test", url="http://example.com")
        assert endpoint.name == "test"
        assert endpoint.url == "http://example.com"
        assert endpoint.metadata == {}

    def test_endpoint_creation_with_metadata(self, sample_endpoint: Endpoint):
        """Test Endpoint creation with custom metadata."""
        assert sample_endpoint.name == "test-endpoint"
        assert sample_endpoint.url == "http://localhost:8080"
        assert sample_endpoint.metadata == {"version": "1.0"}

    def test_endpoint_metadata_modification(self):
        """Test that metadata can be modified after creation."""
        endpoint = Endpoint(name="test", url="http://example.com")
        endpoint.metadata["new_key"] = "new_value"
        assert endpoint.metadata["new_key"] == "new_value"


class TestCommandSpec:
    """Tests for CommandSpec dataclass."""

    def test_command_spec_defaults(self):
        """Test CommandSpec with default values."""
        spec = CommandSpec(template="echo hello")
        assert spec.template == "echo hello"
        assert spec.shell == "/bin/bash"
        assert spec.timeout_seconds == 1800

    def test_command_spec_custom_values(self, sample_command_spec: CommandSpec):
        """Test CommandSpec with custom values."""
        assert sample_command_spec.template == "echo {message}"
        assert sample_command_spec.shell == "/bin/bash"
        assert sample_command_spec.timeout_seconds == 60


class TestToolSpec:
    """Tests for ToolSpec dataclass."""

    def test_tool_spec_defaults(self):
        """Test ToolSpec with default values."""
        spec = ToolSpec(name="test-tool")
        assert spec.name == "test-tool"
        assert spec.enabled is True
        assert spec.config == {}

    def test_tool_spec_custom_values(self, sample_tool_spec: ToolSpec):
        """Test ToolSpec with custom values."""
        assert sample_tool_spec.name == "test-tool"
        assert sample_tool_spec.enabled is True
        assert sample_tool_spec.config == {"timeout": 30}

    def test_tool_spec_disabled(self):
        """Test ToolSpec can be disabled."""
        spec = ToolSpec(name="disabled-tool", enabled=False)
        assert spec.enabled is False


class TestMCPServerSpec:
    """Tests for MCPServerSpec dataclass."""

    def test_mcp_server_spec_stdio_transport(self, sample_mcp_server_spec_stdio: MCPServerSpec):
        """Test MCPServerSpec with stdio transport."""
        assert sample_mcp_server_spec_stdio.name == "test-mcp"
        assert sample_mcp_server_spec_stdio.transport == "stdio"
        assert sample_mcp_server_spec_stdio.command == "/usr/bin/mcp-server"
        assert sample_mcp_server_spec_stdio.args == ["--port", "8080"]
        assert sample_mcp_server_spec_stdio.env == {"DEBUG": "1"}
        assert sample_mcp_server_spec_stdio.enabled is True
        assert sample_mcp_server_spec_stdio.url is None

    def test_mcp_server_spec_http_transport(self, sample_mcp_server_spec_http: MCPServerSpec):
        """Test MCPServerSpec with http transport."""
        assert sample_mcp_server_spec_http.name == "test-mcp-http"
        assert sample_mcp_server_spec_http.transport == "http"
        assert sample_mcp_server_spec_http.url == "http://localhost:3000/mcp"
        assert sample_mcp_server_spec_http.enabled is True
        assert sample_mcp_server_spec_http.command is None

    def test_mcp_server_spec_defaults(self):
        """Test MCPServerSpec default values."""
        spec = MCPServerSpec(name="test", transport="stdio")
        assert spec.name == "test"
        assert spec.transport == "stdio"
        assert spec.command is None
        assert spec.args == []
        assert spec.url is None
        assert spec.env == {}
        assert spec.enabled is True


class TestSkillSpec:
    """Tests for SkillSpec dataclass."""

    def test_skill_spec_defaults(self):
        """Test SkillSpec with default values."""
        spec = SkillSpec(name="test-skill")
        assert spec.name == "test-skill"
        assert spec.description == ""
        assert spec.config == {}

    def test_skill_spec_custom_values(self, sample_skill_spec: SkillSpec):
        """Test SkillSpec with custom values."""
        assert sample_skill_spec.name == "test-skill"
        assert sample_skill_spec.description == "A test skill"
        assert sample_skill_spec.config == {"param": "value"}


class TestEnums:
    """Tests for enum classes."""

    # ContainerState tests
    def test_container_state_values(self):
        """Test ContainerState enum values."""
        assert ContainerState.CREATED.value == "created"
        assert ContainerState.RUNNING.value == "running"
        assert ContainerState.STOPPED.value == "stopped"
        assert ContainerState.REMOVED.value == "removed"
        assert ContainerState.FAILED.value == "failed"

    def test_container_state_string_comparison(self):
        """Test ContainerState can be compared with strings."""
        assert ContainerState.RUNNING.value == "running"
        assert ContainerState.CREATED.value != "running"

    # RunnerRole tests
    def test_runner_role_values(self):
        """Test RunnerRole enum values."""
        assert RunnerRole.TARGET.value == "target"
        assert RunnerRole.ATTACK.value == "attack"
        assert RunnerRole.EVALUATOR.value == "evaluator"

    # TraceEventType tests
    def test_trace_event_type_values(self):
        """Test TraceEventType enum values."""
        assert TraceEventType.RUN_START.value == "run_start"
        assert TraceEventType.RUN_END.value == "run_end"
        assert TraceEventType.MESSAGE.value == "message"
        assert TraceEventType.TOOL_CALL.value == "tool_call"
        assert TraceEventType.TOOL_RESULT.value == "tool_result"
        assert TraceEventType.COMMAND.value == "command"
        assert TraceEventType.COMMAND_RESULT.value == "command_result"
        assert TraceEventType.SERVICE_EVENT.value == "service_event"
        assert TraceEventType.SNAPSHOT.value == "snapshot"
        assert TraceEventType.ERROR.value == "error"

    # EvaluatorDecision tests
    def test_evaluator_decision_values(self):
        """Test EvaluatorDecision enum values."""
        assert EvaluatorDecision.PASS.value == "pass"
        assert EvaluatorDecision.FAIL.value == "fail"

    def test_enum_from_string(self):
        """Test enum can be created from string value."""
        assert ContainerState("running") == ContainerState.RUNNING
        assert RunnerRole("target") == RunnerRole.TARGET
        assert EvaluatorDecision("pass") == EvaluatorDecision.PASS

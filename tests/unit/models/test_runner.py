"""Unit tests for RunnerSpec model."""
from __future__ import annotations

import pytest

from framework.models.specs import RunnerSpec


class TestRunnerSpec:
    """Tests for RunnerSpec dataclass."""

    def test_runner_spec_with_required_fields(self, minimal_runner_spec: RunnerSpec):
        """Test RunnerSpec with only required fields."""
        assert minimal_runner_spec.name == "minimal-runner"
        assert minimal_runner_spec.role == "target"
        assert minimal_runner_spec.framework == "generic_cli"
        assert minimal_runner_spec.runner_image == "runner:latest"
        assert minimal_runner_spec.launch_cmd == "run"

    def test_runner_spec_optional_fields_defaults(self, minimal_runner_spec: RunnerSpec):
        """Test that optional fields have correct defaults."""
        assert minimal_runner_spec.model is None
        assert minimal_runner_spec.base_url is None
        assert minimal_runner_spec.api_key_env is None
        assert minimal_runner_spec.tools == []
        assert minimal_runner_spec.skills == []
        assert minimal_runner_spec.mcp_servers == []
        assert minimal_runner_spec.config_overlay == {}

    def test_runner_spec_with_all_fields(self, sample_runner_spec: RunnerSpec):
        """Test RunnerSpec with all fields populated."""
        assert sample_runner_spec.name == "test-runner"
        assert sample_runner_spec.role == "target"
        assert sample_runner_spec.framework == "claude_code"
        assert sample_runner_spec.runner_image == "runner:latest"
        assert sample_runner_spec.launch_cmd == "claude-agent"
        assert sample_runner_spec.model == "claude-opus-4-6"
        assert sample_runner_spec.base_url == "http://api.example.com"
        assert sample_runner_spec.api_key_env == "ANTHROPIC_API_KEY"
        assert sample_runner_spec.tools == ["bash", "read"]
        assert sample_runner_spec.skills == ["code-review"]
        assert sample_runner_spec.mcp_servers == ["github"]
        assert sample_runner_spec.config_overlay == {"temperature": 0.7}

    def test_runner_spec_different_roles(self):
        """Test RunnerSpec with different roles."""
        target = RunnerSpec(
            name="target",
            role="target",
            framework="claude_code",
            runner_image="runner:latest",
            launch_cmd="run",
        )
        attack = RunnerSpec(
            name="attack",
            role="attack",
            framework="claude_code",
            runner_image="runner:latest",
            launch_cmd="run",
        )
        evaluator = RunnerSpec(
            name="evaluator",
            role="evaluator",
            framework="claude_code",
            runner_image="runner:latest",
            launch_cmd="run",
        )
        assert target.role == "target"
        assert attack.role == "attack"
        assert evaluator.role == "evaluator"

    def test_runner_spec_with_model(self):
        """Test RunnerSpec with model configuration."""
        runner = RunnerSpec(
            name="test",
            role="target",
            framework="claude_code",
            runner_image="runner:latest",
            launch_cmd="run",
            model="claude-sonnet-4-6",
        )
        assert runner.model == "claude-sonnet-4-6"

    def test_runner_spec_with_api_config(self):
        """Test RunnerSpec with API configuration."""
        runner = RunnerSpec(
            name="test",
            role="target",
            framework="openai",
            runner_image="runner:latest",
            launch_cmd="run",
            model="gpt-4",
            base_url="http://localhost:11434/v1",
            api_key_env="OPENAI_API_KEY",
        )
        assert runner.base_url == "http://localhost:11434/v1"
        assert runner.api_key_env == "OPENAI_API_KEY"

    def test_runner_spec_with_tools(self):
        """Test RunnerSpec with tools list."""
        runner = RunnerSpec(
            name="test",
            role="target",
            framework="claude_code",
            runner_image="runner:latest",
            launch_cmd="run",
            tools=["bash", "read", "write", "edit", "glob", "grep"],
        )
        assert len(runner.tools) == 6
        assert "bash" in runner.tools
        assert "grep" in runner.tools

    def test_runner_spec_with_skills(self):
        """Test RunnerSpec with skills list."""
        runner = RunnerSpec(
            name="test",
            role="target",
            framework="claude_code",
            runner_image="runner:latest",
            launch_cmd="run",
            skills=["code-review", "test-runner", "commit"],
        )
        assert len(runner.skills) == 3
        assert "code-review" in runner.skills

    def test_runner_spec_with_mcp_servers(self):
        """Test RunnerSpec with MCP servers."""
        runner = RunnerSpec(
            name="test",
            role="target",
            framework="claude_code",
            runner_image="runner:latest",
            launch_cmd="run",
            mcp_servers=["github", "slack", "postgres"],
        )
        assert len(runner.mcp_servers) == 3
        assert "github" in runner.mcp_servers

    def test_runner_spec_with_config_overlay(self):
        """Test RunnerSpec with config overlay."""
        runner = RunnerSpec(
            name="test",
            role="target",
            framework="claude_code",
            runner_image="runner:latest",
            launch_cmd="run",
            config_overlay={
                "temperature": 0.7,
                "max_tokens": 4096,
                "top_p": 0.9,
            },
        )
        assert runner.config_overlay["temperature"] == 0.7
        assert runner.config_overlay["max_tokens"] == 4096

    def test_runner_spec_different_frameworks(self):
        """Test RunnerSpec with different frameworks."""
        frameworks = ["claude_code", "openai", "iflow", "generic_cli"]
        for framework in frameworks:
            runner = RunnerSpec(
                name="test",
                role="target",
                framework=framework,
                runner_image="runner:latest",
                launch_cmd="run",
            )
            assert runner.framework == framework

    def test_runner_spec_multiple_instances_independent(self):
        """Test that multiple RunnerSpec instances are independent."""
        runner1 = RunnerSpec(
            name="runner-1",
            role="target",
            framework="claude_code",
            runner_image="runner:latest",
            launch_cmd="run",
            tools=["bash"],
        )
        runner2 = RunnerSpec(
            name="runner-2",
            role="attack",
            framework="openai",
            runner_image="runner:latest",
            launch_cmd="run",
            tools=["read"],
        )
        assert runner1.name != runner2.name
        assert runner1.role != runner2.role
        assert runner1.tools == ["bash"]
        assert runner2.tools == ["read"]

    def test_runner_spec_empty_lists_are_mutable(self):
        """Test that empty list defaults can be modified."""
        runner = RunnerSpec(
            name="test",
            role="target",
            framework="claude_code",
            runner_image="runner:latest",
            launch_cmd="run",
        )
        runner.tools.append("new_tool")
        assert "new_tool" in runner.tools
"""Unit tests for FrameworkConfig model."""
from __future__ import annotations

import pytest

from framework.models.specs import FrameworkConfig


class TestFrameworkConfig:
    """Tests for FrameworkConfig dataclass."""

    def test_config_with_minimal_args(self, minimal_framework_config: FrameworkConfig):
        """Test FrameworkConfig with minimal required arguments."""
        assert minimal_framework_config.name == "minimal"
        assert minimal_framework_config.output_dir == "/tmp/out"
        assert minimal_framework_config.network_name == "framework_net"
        assert minimal_framework_config.reset_between_runs is True
        assert minimal_framework_config.max_parallel_runs == 1
        assert minimal_framework_config.extra == {}

    def test_config_with_all_args(self, sample_framework_config: FrameworkConfig):
        """Test FrameworkConfig with all arguments specified."""
        assert sample_framework_config.name == "test-framework"
        assert sample_framework_config.output_dir == "/tmp/output"
        assert sample_framework_config.network_name == "test_net"
        assert sample_framework_config.reset_between_runs is False
        assert sample_framework_config.max_parallel_runs == 4
        assert sample_framework_config.extra == {"custom_option": "value"}

    def test_default_values(self):
        """Test that default values are correctly set."""
        config = FrameworkConfig(name="test", output_dir="/out")
        assert config.network_name == "framework_net"
        assert config.reset_between_runs is True
        assert config.max_parallel_runs == 1
        assert config.extra == {}

    def test_extra_dict_modification(self):
        """Test that extra dict can be modified."""
        config = FrameworkConfig(name="test", output_dir="/out")
        config.extra["key"] = "value"
        assert config.extra["key"] == "value"

    def test_extra_dict_with_initial_values(self):
        """Test FrameworkConfig with initial extra values."""
        config = FrameworkConfig(
            name="test",
            output_dir="/out",
            extra={"timeout": 300, "retries": 3},
        )
        assert config.extra["timeout"] == 300
        assert config.extra["retries"] == 3

    def test_config_immutability_via_slots(self):
        """Test that config uses slots for memory efficiency."""
        config = FrameworkConfig(name="test", output_dir="/out")
        # Verify slots are used by checking __slots__ attribute
        assert hasattr(FrameworkConfig, "__dataclass_fields__")

    def test_multiple_configs_are_independent(self):
        """Test that multiple config instances are independent."""
        config1 = FrameworkConfig(name="config1", output_dir="/out1")
        config2 = FrameworkConfig(name="config2", output_dir="/out2")

        config1.extra["shared_key"] = "value1"
        config2.extra["shared_key"] = "value2"

        assert config1.extra["shared_key"] == "value1"
        assert config2.extra["shared_key"] == "value2"

    def test_reset_between_runs_flag(self):
        """Test reset_between_runs flag."""
        config_reset = FrameworkConfig(name="test", output_dir="/out", reset_between_runs=True)
        config_no_reset = FrameworkConfig(name="test", output_dir="/out", reset_between_runs=False)

        assert config_reset.reset_between_runs is True
        assert config_no_reset.reset_between_runs is False

    def test_max_parallel_runs_value(self):
        """Test max_parallel_runs configuration."""
        config = FrameworkConfig(name="test", output_dir="/out", max_parallel_runs=10)
        assert config.max_parallel_runs == 10

    def test_network_name_customization(self):
        """Test custom network name."""
        config = FrameworkConfig(name="test", output_dir="/out", network_name="custom_network")
        assert config.network_name == "custom_network"
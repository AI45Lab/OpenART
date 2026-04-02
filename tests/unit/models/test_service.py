"""Unit tests for ServiceSpec model."""
from __future__ import annotations

import pytest

from framework.models.specs import ServiceSpec


class TestServiceSpec:
    """Tests for ServiceSpec dataclass."""

    def test_service_spec_with_required_fields(self, minimal_service_spec: ServiceSpec):
        """Test ServiceSpec with only required fields."""
        assert minimal_service_spec.name == "minimal-service"
        assert minimal_service_spec.type == "cache"
        assert minimal_service_spec.required is True
        assert minimal_service_spec.image is None
        assert minimal_service_spec.profile is None
        assert minimal_service_spec.config == {}

    def test_service_spec_with_all_fields(self, sample_service_spec: ServiceSpec):
        """Test ServiceSpec with all fields populated."""
        assert sample_service_spec.name == "test-service"
        assert sample_service_spec.type == "database"
        assert sample_service_spec.required is True
        assert sample_service_spec.image == "postgres:15"
        assert sample_service_spec.profile == "production"
        assert sample_service_spec.config == {"port": 5432, "user": "admin"}

    def test_service_spec_required_default(self):
        """Test that required defaults to True."""
        service = ServiceSpec(name="test", type="cache")
        assert service.required is True

    def test_service_spec_optional_not_required(self):
        """Test ServiceSpec that is not required."""
        service = ServiceSpec(name="optional-service", type="monitoring", required=False)
        assert service.required is False

    def test_service_spec_config_default(self):
        """Test that config defaults to empty dict."""
        service = ServiceSpec(name="test", type="cache")
        assert service.config == {}

    def test_service_spec_with_image(self):
        """Test ServiceSpec with image."""
        service = ServiceSpec(
            name="database",
            type="database",
            image="postgres:15-alpine",
        )
        assert service.image == "postgres:15-alpine"

    def test_service_spec_with_profile(self):
        """Test ServiceSpec with profile."""
        service = ServiceSpec(
            name="dev-db",
            type="database",
            profile="development",
        )
        assert service.profile == "development"

    def test_service_spec_with_config(self):
        """Test ServiceSpec with configuration."""
        service = ServiceSpec(
            name="postgres",
            type="database",
            config={
                "port": 5432,
                "database": "appdb",
                "user": "appuser",
                "password_env": "POSTGRES_PASSWORD",
            },
        )
        assert service.config["port"] == 5432
        assert service.config["database"] == "appdb"

    def test_service_spec_different_types(self):
        """Test ServiceSpec with different service types."""
        types = ["database", "cache", "queue", "storage", "api", "monitoring"]
        for service_type in types:
            service = ServiceSpec(name=f"{service_type}-service", type=service_type)
            assert service.type == service_type

    def test_service_spec_multiple_instances_independent(self):
        """Test that multiple ServiceSpec instances are independent."""
        service1 = ServiceSpec(
            name="db1",
            type="database",
            config={"port": 5432},
        )
        service2 = ServiceSpec(
            name="db2",
            type="database",
            config={"port": 5433},
        )
        assert service1.name != service2.name
        assert service1.config["port"] != service2.config["port"]

    def test_service_spec_config_modification(self):
        """Test that config can be modified after creation."""
        service = ServiceSpec(name="test", type="cache")
        service.config["new_key"] = "new_value"
        assert service.config["new_key"] == "new_value"

    def test_service_spec_complex_config(self):
        """Test ServiceSpec with complex configuration."""
        config = {
            "replicas": 3,
            "resources": {
                "cpu": "500m",
                "memory": "512Mi",
            },
            "environment": {
                "DEBUG": "false",
                "LOG_LEVEL": "info",
            },
        }
        service = ServiceSpec(
            name="complex-service",
            type="api",
            config=config,
        )
        assert service.config["replicas"] == 3
        assert service.config["resources"]["cpu"] == "500m"
        assert service.config["environment"]["DEBUG"] == "false"

    def test_service_spec_required_vs_optional(self):
        """Test the distinction between required and optional services."""
        required_service = ServiceSpec(
            name="primary-db",
            type="database",
            required=True,
        )
        optional_service = ServiceSpec(
            name="cache",
            type="cache",
            required=False,
        )
        assert required_service.required is True
        assert optional_service.required is False

    def test_service_spec_with_image_and_profile(self):
        """Test ServiceSpec with both image and profile."""
        service = ServiceSpec(
            name="production-db",
            type="database",
            image="postgres:15",
            profile="production",
            required=True,
        )
        assert service.image == "postgres:15"
        assert service.profile == "production"
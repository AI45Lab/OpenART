"""Unit tests for trace event model."""
from __future__ import annotations

import pytest

from framework.models.specs import TraceEvent
from framework.components.trace import TraceSinkBase


class TestTraceEventModel:
    """Tests for TraceEvent model in trace context."""

    def test_trace_event_is_dataclass(self):
        """Test that TraceEvent is a dataclass with slots."""
        event = TraceEvent(
            run_id="run-001",
            source_role="target",
            event_type="message",
            timestamp=1234567890.0,
        )
        assert hasattr(event, "run_id")
        assert hasattr(event, "source_role")
        assert hasattr(event, "event_type")
        assert hasattr(event, "timestamp")
        assert hasattr(event, "message")
        assert hasattr(event, "payload")

    def test_trace_event_default_values(self):
        """Test TraceEvent default values."""
        event = TraceEvent(
            run_id="run-001",
            source_role="target",
            event_type="message",
            timestamp=1234567890.0,
        )
        assert event.message == ""
        assert event.payload == {}

    def test_trace_event_with_values(self):
        """Test TraceEvent with custom values."""
        event = TraceEvent(
            run_id="run-001",
            source_role="target",
            event_type="tool_call",
            timestamp=1234567890.0,
            message="Executed command",
            payload={"tool": "bash", "exit_code": 0},
        )
        assert event.message == "Executed command"
        assert event.payload["tool"] == "bash"

    def test_trace_event_field_types(self):
        """Test TraceEvent field types."""
        event = TraceEvent(
            run_id="run-001",
            source_role="target",
            event_type="message",
            timestamp=1234567890.123,
            message="Test",
            payload={"key": "value"},
        )
        assert isinstance(event.run_id, str)
        assert isinstance(event.source_role, str)
        assert isinstance(event.event_type, str)
        assert isinstance(event.timestamp, float)
        assert isinstance(event.message, str)
        assert isinstance(event.payload, dict)


class TestTraceSinkBase:
    """Tests for TraceSinkBase abstract class."""

    def test_trace_sink_base_is_abstract(self):
        """Test that TraceSinkBase is abstract and cannot be instantiated."""
        with pytest.raises(TypeError):
            TraceSinkBase()

    def test_trace_sink_base_has_required_methods(self):
        """Test that TraceSinkBase has required abstract methods."""
        assert hasattr(TraceSinkBase, "write")
        assert hasattr(TraceSinkBase, "flush")
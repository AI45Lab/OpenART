"""Unit tests for TraceEvent model."""
from __future__ import annotations

import pytest

from framework.models.specs import TraceEvent


class TestTraceEvent:
    """Tests for TraceEvent dataclass."""

    def test_trace_event_with_all_fields(self, sample_trace_event: TraceEvent):
        """Test TraceEvent creation with all fields."""
        assert sample_trace_event.run_id == "run-001"
        assert sample_trace_event.source_role == "target"
        assert sample_trace_event.event_type == "message"
        assert sample_trace_event.timestamp == 1234567890.123
        assert sample_trace_event.message == "Test message"
        assert sample_trace_event.payload == {"key": "value"}

    def test_trace_event_with_defaults(self, minimal_trace_event: TraceEvent):
        """Test TraceEvent with default values."""
        assert minimal_trace_event.run_id == "run-001"
        assert minimal_trace_event.source_role == "target"
        assert minimal_trace_event.event_type == "run_start"
        assert minimal_trace_event.timestamp == 1234567890.0
        assert minimal_trace_event.message == ""
        assert minimal_trace_event.payload == {}

    def test_trace_event_message_default(self):
        """Test that message defaults to empty string."""
        event = TraceEvent(
            run_id="run-001",
            source_role="target",
            event_type="run_start",
            timestamp=1234567890.0,
        )
        assert event.message == ""

    def test_trace_event_payload_default(self):
        """Test that payload defaults to empty dict."""
        event = TraceEvent(
            run_id="run-001",
            source_role="target",
            event_type="run_start",
            timestamp=1234567890.0,
        )
        assert event.payload == {}

    def test_trace_event_timestamp_type(self):
        """Test that timestamp is a float."""
        event = TraceEvent(
            run_id="run-001",
            source_role="target",
            event_type="run_start",
            timestamp=1234567890.123,
        )
        assert isinstance(event.timestamp, float)

    def test_trace_event_with_complex_payload(self):
        """Test TraceEvent with complex payload structure."""
        payload = {
            "nested": {
                "key": "value",
                "list": [1, 2, 3],
            },
            "items": ["a", "b", "c"],
        }
        event = TraceEvent(
            run_id="run-001",
            source_role="target",
            event_type="tool_call",
            timestamp=1234567890.0,
            message="Tool executed",
            payload=payload,
        )
        assert event.payload["nested"]["key"] == "value"
        assert event.payload["nested"]["list"] == [1, 2, 3]
        assert event.payload["items"] == ["a", "b", "c"]

    def test_trace_event_different_event_types(self):
        """Test TraceEvent with different event types."""
        event_types = [
            "run_start",
            "run_end",
            "message",
            "tool_call",
            "tool_result",
            "command",
            "command_result",
            "service_event",
            "snapshot",
            "error",
        ]
        for event_type in event_types:
            event = TraceEvent(
                run_id="run-001",
                source_role="target",
                event_type=event_type,
                timestamp=1234567890.0,
            )
            assert event.event_type == event_type

    def test_trace_event_different_source_roles(self):
        """Test TraceEvent with different source roles."""
        roles = ["target", "attack", "evaluator", "service"]
        for role in roles:
            event = TraceEvent(
                run_id="run-001",
                source_role=role,
                event_type="message",
                timestamp=1234567890.0,
            )
            assert event.source_role == role

    def test_trace_event_payload_modification(self):
        """Test that payload can be modified after creation."""
        event = TraceEvent(
            run_id="run-001",
            source_role="target",
            event_type="message",
            timestamp=1234567890.0,
        )
        event.payload["new_key"] = "new_value"
        assert event.payload["new_key"] == "new_value"

    def test_multiple_trace_events_independent(self):
        """Test that multiple TraceEvent instances are independent."""
        event1 = TraceEvent(
            run_id="run-001",
            source_role="target",
            event_type="message",
            timestamp=1234567890.0,
            payload={"key": "value1"},
        )
        event2 = TraceEvent(
            run_id="run-001",
            source_role="target",
            event_type="message",
            timestamp=1234567891.0,
            payload={"key": "value2"},
        )
        assert event1.payload["key"] == "value1"
        assert event2.payload["key"] == "value2"

    def test_trace_event_message_with_special_characters(self):
        """Test TraceEvent with special characters in message."""
        event = TraceEvent(
            run_id="run-001",
            source_role="target",
            event_type="message",
            timestamp=1234567890.0,
            message="Hello, 世界! 🎉\nNew line\tTab",
        )
        assert "世界" in event.message
        assert "\n" in event.message
        assert "\t" in event.message
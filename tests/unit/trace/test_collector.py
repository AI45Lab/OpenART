"""Unit tests for TraceCollector."""
from __future__ import annotations

import time
from unittest.mock import MagicMock

import pytest

from framework.models.specs import TraceEvent
from framework.components.trace import TraceCollector, MemoryTraceSink


class TestTraceCollector:
    """Tests for TraceCollector."""

    def test_emit_forwards_to_sink_write(self):
        """Test that emit() forwards event to sink.write()."""
        sink = MemoryTraceSink()
        collector = TraceCollector(sink)
        event = TraceEvent(
            run_id="run-001",
            source_role="target",
            event_type="message",
            timestamp=1234567890.0,
            message="Test message",
        )

        collector.emit(event)

        assert len(sink.events) == 1
        assert sink.events[0] == event

    def test_emit_simple_creates_correct_event(self):
        """Test that emit_simple() creates correct TraceEvent structure."""
        sink = MemoryTraceSink()
        collector = TraceCollector(sink)

        collector.emit_simple(
            run_id="run-001",
            source_role="target",
            event_type="message",
            message="Test message",
            payload={"key": "value"},
        )

        assert len(sink.events) == 1
        event = sink.events[0]
        assert event.run_id == "run-001"
        assert event.source_role == "target"
        assert event.event_type == "message"
        assert event.message == "Test message"
        assert event.payload == {"key": "value"}
        assert isinstance(event.timestamp, float)

    def test_emit_simple_with_default_payload(self):
        """Test emit_simple() with default (empty) payload."""
        sink = MemoryTraceSink()
        collector = TraceCollector(sink)

        collector.emit_simple(
            run_id="run-001",
            source_role="target",
            event_type="run_start",
            message="Starting run",
        )

        event = sink.events[0]
        assert event.payload == {}

    def test_emit_command_result_creates_correct_payload(self):
        """Test that emit_command_result() creates correct payload structure."""
        sink = MemoryTraceSink()
        collector = TraceCollector(sink)

        collector.emit_command_result(
            run_id="run-001",
            role="target",
            cmd="ls -la",
            exit_code=0,
            stdout="file1.txt\nfile2.txt",
            stderr="",
        )

        assert len(sink.events) == 1
        event = sink.events[0]
        assert event.run_id == "run-001"
        assert event.source_role == "target"
        assert event.event_type == "command_result"
        assert event.message == "ls -la"
        assert event.payload["exit_code"] == 0
        assert event.payload["stdout"] == "file1.txt\nfile2.txt"
        assert event.payload["stderr"] == ""

    def test_emit_command_result_with_error(self):
        """Test emit_command_result() with non-zero exit code."""
        sink = MemoryTraceSink()
        collector = TraceCollector(sink)

        collector.emit_command_result(
            run_id="run-001",
            role="target",
            cmd="exit 1",
            exit_code=1,
            stdout="",
            stderr="Error: command failed",
        )

        event = sink.events[0]
        assert event.payload["exit_code"] == 1
        assert event.payload["stderr"] == "Error: command failed"

    def test_emit_command_result_sets_event_type(self):
        """Test that emit_command_result() always sets event_type to 'command_result'."""
        sink = MemoryTraceSink()
        collector = TraceCollector(sink)

        collector.emit_command_result(
            run_id="run-001",
            role="target",
            cmd="echo test",
            exit_code=0,
            stdout="test",
            stderr="",
        )

        assert sink.events[0].event_type == "command_result"

    def test_collector_with_mock_sink(self):
        """Test collector with a mock sink to verify interactions."""
        mock_sink = MagicMock()
        collector = TraceCollector(mock_sink)
        event = TraceEvent(
            run_id="run-001",
            source_role="target",
            event_type="message",
            timestamp=1234567890.0,
        )

        collector.emit(event)

        mock_sink.write.assert_called_once_with(event)

    def test_emit_multiple_events(self):
        """Test emitting multiple events in sequence."""
        sink = MemoryTraceSink()
        collector = TraceCollector(sink)

        collector.emit_simple("run-001", "target", "run_start", "Starting")
        collector.emit_simple("run-001", "target", "message", "Processing")
        collector.emit_simple("run-001", "target", "run_end", "Done")

        assert len(sink.events) == 3
        event_types = [e.event_type for e in sink.events]
        assert event_types == ["run_start", "message", "run_end"]

    def test_emit_simple_timestamp_is_recent(self):
        """Test that emit_simple() uses current time for timestamp."""
        sink = MemoryTraceSink()
        collector = TraceCollector(sink)

        before = time.time()
        collector.emit_simple("run-001", "target", "message", "Test")
        after = time.time()

        event = sink.events[0]
        assert before <= event.timestamp <= after

    def test_emit_command_result_timestamp_is_recent(self):
        """Test that emit_command_result() uses current time for timestamp."""
        sink = MemoryTraceSink()
        collector = TraceCollector(sink)

        before = time.time()
        collector.emit_command_result("run-001", "target", "cmd", 0, "", "")
        after = time.time()

        event = sink.events[0]
        assert before <= event.timestamp <= after

    def test_collector_sink_attribute(self):
        """Test that collector stores sink reference."""
        sink = MemoryTraceSink()
        collector = TraceCollector(sink)

        assert collector.sink is sink

    def test_emit_simple_with_none_payload(self):
        """Test emit_simple() with None payload (should become empty dict)."""
        sink = MemoryTraceSink()
        collector = TraceCollector(sink)

        collector.emit_simple(
            run_id="run-001",
            source_role="target",
            event_type="message",
            message="Test",
            payload=None,
        )

        event = sink.events[0]
        assert event.payload == {}

    def test_emit_command_result_with_large_output(self):
        """Test emit_command_result() with large stdout/stderr."""
        sink = MemoryTraceSink()
        collector = TraceCollector(sink)

        large_stdout = "x" * 10000
        large_stderr = "y" * 5000

        collector.emit_command_result(
            run_id="run-001",
            role="target",
            cmd="large_command",
            exit_code=0,
            stdout=large_stdout,
            stderr=large_stderr,
        )

        event = sink.events[0]
        assert len(event.payload["stdout"]) == 10000
        assert len(event.payload["stderr"]) == 5000
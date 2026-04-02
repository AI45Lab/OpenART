"""Unit tests for JsonlTraceSink."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from framework.models.specs import TraceEvent
from framework.components.trace import JsonlTraceSink


class TestJsonlTraceSink:
    """Tests for JsonlTraceSink."""

    def test_write_single_event(self, tmp_trace_file: Path):
        """Test writing a single event to JSONL file."""
        sink = JsonlTraceSink(str(tmp_trace_file))
        event = TraceEvent(
            run_id="run-001",
            source_role="target",
            event_type="message",
            timestamp=1234567890.0,
            message="Test message",
            payload={"key": "value"},
        )

        sink.write(event)

        assert tmp_trace_file.exists()
        with open(tmp_trace_file, "r", encoding="utf-8") as f:
            line = f.readline()
            data = json.loads(line)
            assert data["run_id"] == "run-001"
            assert data["source_role"] == "target"
            assert data["event_type"] == "message"
            assert data["timestamp"] == 1234567890.0
            assert data["message"] == "Test message"
            assert data["payload"] == {"key": "value"}

    def test_write_multiple_events_append(self, tmp_trace_file: Path):
        """Test that writing multiple events appends to file."""
        sink = JsonlTraceSink(str(tmp_trace_file))

        events = [
            TraceEvent(
                run_id="run-001",
                source_role="target",
                event_type="run_start",
                timestamp=1234567890.0,
            ),
            TraceEvent(
                run_id="run-001",
                source_role="target",
                event_type="message",
                timestamp=1234567891.0,
            ),
            TraceEvent(
                run_id="run-001",
                source_role="target",
                event_type="run_end",
                timestamp=1234567990.0,
            ),
        ]

        for event in events:
            sink.write(event)

        with open(tmp_trace_file, "r", encoding="utf-8") as f:
            lines = f.readlines()
        assert len(lines) == 3

        for i, line in enumerate(lines):
            data = json.loads(line)
            assert data["run_id"] == "run-001"

    def test_flush_is_noop(self, tmp_trace_file: Path):
        """Test that flush() is callable but no-op."""
        sink = JsonlTraceSink(str(tmp_trace_file))
        # Should not raise
        sink.flush()

    def test_timestamp_serialization(self, tmp_trace_file: Path):
        """Test that timestamp is properly serialized as float."""
        sink = JsonlTraceSink(str(tmp_trace_file))
        event = TraceEvent(
            run_id="run-001",
            source_role="target",
            event_type="message",
            timestamp=1234567890.123456,
        )

        sink.write(event)

        with open(tmp_trace_file, "r", encoding="utf-8") as f:
            data = json.loads(f.readline())
            assert isinstance(data["timestamp"], float)
            assert data["timestamp"] == 1234567890.123456

    def test_parent_directory_creation(self, tmp_path: Path):
        """Test that parent directories are created if they don't exist."""
        trace_file = tmp_path / "nested" / "deep" / "dir" / "trace.jsonl"
        assert not trace_file.parent.exists()

        sink = JsonlTraceSink(str(trace_file))
        event = TraceEvent(
            run_id="run-001",
            source_role="target",
            event_type="message",
            timestamp=1234567890.0,
        )

        sink.write(event)
        assert trace_file.parent.exists()
        assert trace_file.exists()

    def test_unicode_message_handling(self, tmp_trace_file: Path):
        """Test that unicode characters in message are handled correctly."""
        sink = JsonlTraceSink(str(tmp_trace_file))
        event = TraceEvent(
            run_id="run-001",
            source_role="target",
            event_type="message",
            timestamp=1234567890.0,
            message="Hello 世界 🌍",
            payload={"emoji": "🎉"},
        )

        sink.write(event)

        with open(tmp_trace_file, "r", encoding="utf-8") as f:
            data = json.loads(f.readline())
            assert "世界" in data["message"]
            assert "🌍" in data["message"]
            assert data["payload"]["emoji"] == "🎉"

    def test_empty_message_and_payload(self, tmp_trace_file: Path):
        """Test writing event with empty message and payload."""
        sink = JsonlTraceSink(str(tmp_trace_file))
        event = TraceEvent(
            run_id="run-001",
            source_role="target",
            event_type="run_start",
            timestamp=1234567890.0,
            message="",
            payload={},
        )

        sink.write(event)

        with open(tmp_trace_file, "r", encoding="utf-8") as f:
            data = json.loads(f.readline())
            assert data["message"] == ""
            assert data["payload"] == {}

    def test_ensure_ascii_false(self, tmp_trace_file: Path):
        """Test that ensure_ascii=False preserves unicode characters."""
        sink = JsonlTraceSink(str(tmp_trace_file))
        event = TraceEvent(
            run_id="run-001",
            source_role="target",
            event_type="message",
            timestamp=1234567890.0,
            message="日本語テスト",
            payload={"key": "中文"},
        )

        sink.write(event)

        with open(tmp_trace_file, "r", encoding="utf-8") as f:
            content = f.read()
            # ensure_ascii=False means unicode chars are not escaped
            assert "日本語テスト" in content
            assert "中文" in content

    def test_complex_payload_serialization(self, tmp_trace_file: Path):
        """Test complex nested payload serialization."""
        sink = JsonlTraceSink(str(tmp_trace_file))
        complex_payload = {
            "nested": {
                "deeply": {
                    "value": 42,
                },
            },
            "list": [1, 2, 3, {"inner": "value"}],
            "bool": True,
            "null": None,
        }
        event = TraceEvent(
            run_id="run-001",
            source_role="target",
            event_type="snapshot",
            timestamp=1234567890.0,
            payload=complex_payload,
        )

        sink.write(event)

        with open(tmp_trace_file, "r", encoding="utf-8") as f:
            data = json.loads(f.readline())
            assert data["payload"]["nested"]["deeply"]["value"] == 42
            assert data["payload"]["list"] == [1, 2, 3, {"inner": "value"}]
            assert data["payload"]["bool"] is True
            assert data["payload"]["null"] is None

    def test_newline_in_message(self, tmp_trace_file: Path):
        """Test handling of newlines in message."""
        sink = JsonlTraceSink(str(tmp_trace_file))
        event = TraceEvent(
            run_id="run-001",
            source_role="target",
            event_type="message",
            timestamp=1234567890.0,
            message="Line 1\nLine 2\nLine 3",
        )

        sink.write(event)

        with open(tmp_trace_file, "r", encoding="utf-8") as f:
            lines = f.readlines()
            # Should be exactly one line (the JSON object)
            assert len(lines) == 1
            data = json.loads(lines[0])
            assert "\n" in data["message"]
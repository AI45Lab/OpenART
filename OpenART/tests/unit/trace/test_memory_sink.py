"""Unit tests for MemoryTraceSink."""
from __future__ import annotations

import pytest

from framework.models.specs import TraceEvent
from framework.components.trace import MemoryTraceSink


class TestMemoryTraceSink:
    """Tests for MemoryTraceSink."""

    def test_write_single_event(self):
        """Test writing a single event to memory sink."""
        sink = MemoryTraceSink()
        event = TraceEvent(
            run_id="run-001",
            source_role="target",
            event_type="message",
            timestamp=1234567890.0,
            message="Test message",
            payload={"key": "value"},
        )

        sink.write(event)

        assert len(sink.events) == 1
        assert sink.events[0] == event

    def test_write_multiple_events(self):
        """Test writing multiple events to memory sink."""
        sink = MemoryTraceSink()

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

        assert len(sink.events) == 3

    def test_events_maintain_insertion_order(self):
        """Test that events maintain insertion order."""
        sink = MemoryTraceSink()

        for i in range(10):
            event = TraceEvent(
                run_id=f"run-{i:03d}",
                source_role="target",
                event_type="message",
                timestamp=1234567890.0 + i,
            )
            sink.write(event)

        for i in range(10):
            assert sink.events[i].run_id == f"run-{i:03d}"

    def test_flush_is_noop(self):
        """Test that flush() is callable but no-op."""
        sink = MemoryTraceSink()
        # Should not raise
        sink.flush()

    def test_events_list_is_accessible(self):
        """Test that events list is directly accessible."""
        sink = MemoryTraceSink()
        event = TraceEvent(
            run_id="run-001",
            source_role="target",
            event_type="message",
            timestamp=1234567890.0,
        )
        sink.write(event)

        # Events list should be accessible
        assert isinstance(sink.events, list)
        assert len(sink.events) == 1

    def test_events_can_be_cleared(self):
        """Test that events list can be cleared."""
        sink = MemoryTraceSink()
        for i in range(5):
            sink.write(TraceEvent(
                run_id=f"run-{i}",
                source_role="target",
                event_type="message",
                timestamp=1234567890.0,
            ))

        assert len(sink.events) == 5
        sink.events.clear()
        assert len(sink.events) == 0

    def test_events_can_be_iterated(self):
        """Test that events can be iterated."""
        sink = MemoryTraceSink()
        for i in range(3):
            sink.write(TraceEvent(
                run_id=f"run-{i}",
                source_role="target",
                event_type="message",
                timestamp=1234567890.0 + i,
            ))

        timestamps = [event.timestamp for event in sink.events]
        assert timestamps == [1234567890.0, 1234567891.0, 1234567892.0]

    def test_empty_sink_initial_state(self):
        """Test that new sink starts empty."""
        sink = MemoryTraceSink()
        assert sink.events == []
        assert len(sink.events) == 0

    def test_multiple_sinks_are_independent(self):
        """Test that multiple sink instances are independent."""
        sink1 = MemoryTraceSink()
        sink2 = MemoryTraceSink()

        sink1.write(TraceEvent(
            run_id="run-001",
            source_role="target",
            event_type="message",
            timestamp=1234567890.0,
        ))
        sink2.write(TraceEvent(
            run_id="run-002",
            source_role="attack",
            event_type="message",
            timestamp=1234567891.0,
        ))

        assert len(sink1.events) == 1
        assert len(sink2.events) == 1
        assert sink1.events[0].run_id == "run-001"
        assert sink2.events[0].run_id == "run-002"

    def test_events_can_be_indexed(self):
        """Test that events can be accessed by index."""
        sink = MemoryTraceSink()
        sink.write(TraceEvent(
            run_id="run-first",
            source_role="target",
            event_type="run_start",
            timestamp=1234567890.0,
        ))
        sink.write(TraceEvent(
            run_id="run-second",
            source_role="target",
            event_type="message",
            timestamp=1234567891.0,
        ))

        assert sink.events[0].event_type == "run_start"
        assert sink.events[1].event_type == "message"
        assert sink.events[-1].event_type == "message"
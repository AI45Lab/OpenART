"""
Trace implementations for OpenART framework.

This module merges all trace types:
- TraceSinkBase: Abstract base class for trace sinks
- TraceCollector: Collector for trace events
- JsonlTraceSink: JSON Lines file-based trace sink
- MemoryTraceSink: In-memory trace sink
- SqliteTraceSink: SQLite database-based trace sink
"""

from __future__ import annotations

import json
import sqlite3
import time
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Optional

from framework.models.specs import TraceEvent


class TraceSinkBase(ABC):
    """Abstract base class for trace sink implementations."""

    @abstractmethod
    def write(self, event: TraceEvent) -> None:
        ...

    @abstractmethod
    def flush(self) -> None:
        ...


class TraceCollector:
    """Collector for trace events."""

    def __init__(self, sink: TraceSinkBase) -> None:
        self.sink = sink

    def emit(self, event: TraceEvent) -> None:
        self.sink.write(event)

    def emit_simple(
        self,
        run_id: str,
        source_role: str,
        event_type: str,
        message: str,
        payload: Optional[dict] = None,
    ) -> None:
        self.emit(
            TraceEvent(
                run_id=run_id,
                source_role=source_role,
                event_type=event_type,
                timestamp=time.time(),
                message=message,
                payload=payload or {},
            )
        )

    def emit_command_result(
        self,
        run_id: str,
        role: str,
        cmd: str,
        exit_code: int,
        stdout: str,
        stderr: str,
    ) -> None:
        self.emit(
            TraceEvent(
                run_id=run_id,
                source_role=role,
                event_type="command_result",
                timestamp=time.time(),
                message=cmd,
                payload={
                    "exit_code": exit_code,
                    "stdout": stdout,
                    "stderr": stderr,
                },
            )
        )


class JsonlTraceSink(TraceSinkBase):
    """JSON Lines file-based trace sink."""

    def __init__(self, path: str) -> None:
        self.path = path
        Path(path).parent.mkdir(parents=True, exist_ok=True)

    def write(self, event: TraceEvent) -> None:
        with open(self.path, "a", encoding="utf-8") as f:
            f.write(
                json.dumps(
                    {
                        "run_id": event.run_id,
                        "source_role": event.source_role,
                        "event_type": event.event_type,
                        "timestamp": event.timestamp,
                        "message": event.message,
                        "payload": event.payload,
                    },
                    ensure_ascii=False,
                )
                + "\n"
            )

    def flush(self) -> None:
        return


class MemoryTraceSink(TraceSinkBase):
    """In-memory trace sink."""

    def __init__(self) -> None:
        self.events: list[TraceEvent] = []

    def write(self, event: TraceEvent) -> None:
        self.events.append(event)

    def flush(self) -> None:
        return


class SqliteTraceSink(TraceSinkBase):
    """SQLite database-based trace sink."""

    def __init__(self, path: str) -> None:
        self.path = path
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(path)
        self.conn.execute(
            """
            CREATE TABLE IF NOT EXISTS trace_events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                run_id TEXT NOT NULL,
                source_role TEXT NOT NULL,
                event_type TEXT NOT NULL,
                timestamp REAL NOT NULL,
                message TEXT NOT NULL,
                payload_json TEXT NOT NULL
            )
            """
        )
        self.conn.commit()

    def write(self, event: TraceEvent) -> None:
        self.conn.execute(
            """
            INSERT INTO trace_events (
                run_id, source_role, event_type, timestamp, message, payload_json
            ) VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                event.run_id,
                event.source_role,
                event.event_type,
                event.timestamp,
                event.message,
                json.dumps(event.payload, ensure_ascii=False),
            ),
        )

    def flush(self) -> None:
        self.conn.commit()


__all__ = [
    "JsonlTraceSink",
    "MemoryTraceSink",
    "SqliteTraceSink",
    "TraceCollector",
    "TraceSinkBase",
]
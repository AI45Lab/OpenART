from __future__ import annotations

import json
import time
from contextlib import contextmanager
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterator

from framework.core.helpers import write_json_artifact


@dataclass(slots=True)
class TimingEventScope:
    status: str = "ok"
    metadata: dict[str, Any] = field(default_factory=dict)

    def mark(self, status: str) -> None:
        self.status = str(status or "ok")


@dataclass(slots=True)
class TimingRecorder:
    run_dir: str
    started_at: float = field(default_factory=time.time)
    phases_ms: dict[str, int] = field(default_factory=dict)
    events: list[dict[str, Any]] = field(default_factory=list)
    metadata: dict[str, str] = field(default_factory=dict)
    total_ms: int = 0
    _derived_trace_keys: set[str] = field(default_factory=set)

    @property
    def path(self) -> Path:
        return Path(self.run_dir) / "timing.json"

    @contextmanager
    def phase(self, name: str) -> Iterator[None]:
        started_at = time.time()
        started = time.perf_counter()
        status = "ok"
        error = ""
        try:
            yield
        except Exception as exc:
            status = "error"
            error = str(exc)
            raise
        finally:
            ended_at = time.time()
            elapsed_ms = int((time.perf_counter() - started) * 1000)
            self.phases_ms[name] = self.phases_ms.get(name, 0) + elapsed_ms
            metadata: dict[str, Any] = {}
            if error:
                metadata["error"] = error
            self.record_event(
                name=name,
                category="phase",
                started_at=started_at,
                ended_at=ended_at,
                wall_ms=elapsed_ms,
                status=status,
                metadata=metadata,
                flush=False,
            )
            self.flush()

    @contextmanager
    def event(
        self,
        name: str,
        *,
        role: str = "",
        category: str = "",
        iteration: int | None = None,
        phase: str = "",
        status: str = "ok",
        metadata: dict[str, Any] | None = None,
        attack_iteration: int | None = None,
    ) -> Iterator[TimingEventScope]:
        started_at = time.time()
        started = time.perf_counter()
        scope = TimingEventScope(status=str(status or "ok"), metadata=dict(metadata or {}))
        try:
            yield scope
        except Exception as exc:
            scope.status = "error"
            scope.metadata.setdefault("error", str(exc))
            raise
        finally:
            ended_at = time.time()
            self.record_event(
                name=name,
                role=role,
                category=category,
                iteration=iteration,
                phase=phase,
                started_at=started_at,
                ended_at=ended_at,
                wall_ms=int((time.perf_counter() - started) * 1000),
                status=scope.status,
                metadata=scope.metadata,
                attack_iteration=attack_iteration,
            )

    def record_event(
        self,
        *,
        name: str,
        role: str = "",
        category: str = "",
        iteration: int | None = None,
        phase: str = "",
        started_at: float | None = None,
        ended_at: float | None = None,
        wall_ms: int | None = None,
        status: str = "ok",
        metadata: dict[str, Any] | None = None,
        attack_iteration: int | None = None,
        flush: bool = True,
    ) -> dict[str, Any]:
        if started_at is None:
            started_at = time.time()
        if ended_at is None:
            ended_at = started_at
        if wall_ms is None:
            wall_ms = max(0, int((float(ended_at) - float(started_at)) * 1000))
        event = {
            "name": str(name),
            "role": str(role or ""),
            "category": str(category or ""),
            "iteration": iteration,
            "phase": str(phase or ""),
            "started_at": started_at,
            "ended_at": ended_at,
            "wall_ms": int(wall_ms),
            "status": str(status or "ok"),
            "metadata": _json_safe(dict(metadata or {})),
        }
        if attack_iteration is not None:
            event["attack_iteration"] = attack_iteration
        self.events.append(event)
        if flush:
            self.flush()
        return event

    def ingest_trace_tool_events(self, trace_file: str) -> int:
        count = 0
        for event in derive_trace_tool_timing_events(trace_file):
            key = str(event.get("metadata", {}).get("trace_timing_key", ""))
            if key and key in self._derived_trace_keys:
                continue
            if key:
                self._derived_trace_keys.add(key)
            self.record_event(
                name=str(event.get("name", "")),
                role=str(event.get("role", "")),
                category=str(event.get("category", "tool")),
                iteration=event.get("iteration"),
                phase=str(event.get("phase", "")),
                started_at=event.get("started_at"),
                ended_at=event.get("ended_at"),
                wall_ms=event.get("wall_ms"),
                status=str(event.get("status", "ok")),
                metadata=event.get("metadata") if isinstance(event.get("metadata"), dict) else {},
                attack_iteration=event.get("attack_iteration"),
                flush=False,
            )
            count += 1
        if count:
            self.flush()
        return count

    def set_metadata(self, key: str, value: str) -> None:
        self.metadata[key] = value
        self.flush()

    def flush(self) -> None:
        write_json_artifact(
            self.path,
            {
                "started_at": self.started_at,
                "updated_at": time.time(),
                "total_ms": self.total_ms,
                "phases_ms": self.phases_ms,
                "events": self.events,
                "metadata": self.metadata,
            },
            ensure_ascii=False,
        )


_TOOL_CALL_EVENTS = {"tool_call", "tool_start", "tool_use", "function_call"}
_TOOL_RESULT_EVENTS = {"tool_result", "tool_end", "function_result"}


def derive_trace_tool_timing_events(trace_file: str) -> list[dict[str, Any]]:
    path = Path(trace_file)
    if not path.is_file():
        return []

    pending_by_id: dict[str, dict[str, Any]] = {}
    pending_fifo: dict[tuple[str, str], list[dict[str, Any]]] = {}
    derived: list[dict[str, Any]] = []

    for index, raw in enumerate(path.read_text(encoding="utf-8", errors="ignore").splitlines()):
        if not raw.strip():
            continue
        try:
            item = json.loads(raw)
        except json.JSONDecodeError:
            continue
        if not isinstance(item, dict):
            continue
        payload = item.get("payload") if isinstance(item.get("payload"), dict) else {}
        event_type = str(item.get("event_type") or item.get("type") or "").strip().lower()
        if event_type not in _TOOL_CALL_EVENTS and event_type not in _TOOL_RESULT_EVENTS:
            continue

        role = _clean_role(str(item.get("source_role") or item.get("role") or payload.get("role") or ""))
        tool = _clean_tool_name(payload.get("tool") or payload.get("name") or item.get("message") or "unknown")
        timestamp = _coerce_timestamp(item.get("timestamp", payload.get("timestamp")))
        call_id = _tool_call_id(item, payload)
        record = {
            "index": index,
            "role": role,
            "tool": tool,
            "timestamp": timestamp,
            "event_type": event_type,
            "message": str(item.get("message") or ""),
            "payload": payload,
            "call_id": call_id,
        }

        if event_type in _TOOL_CALL_EVENTS:
            if call_id:
                pending_by_id[call_id] = record
            else:
                pending_fifo.setdefault((role, tool), []).append(record)
            continue

        call = pending_by_id.pop(call_id, None) if call_id else None
        if call is None:
            bucket = pending_fifo.get((role, tool), [])
            if bucket:
                call = bucket.pop(0)
        if call is None:
            derived.append(_partial_trace_tool_event(record, reason="result_without_call"))
            continue
        derived.append(_complete_trace_tool_event(call, record))

    for call in pending_by_id.values():
        derived.append(_partial_trace_tool_event(call, reason="call_without_result"))
    for bucket in pending_fifo.values():
        for call in bucket:
            derived.append(_partial_trace_tool_event(call, reason="call_without_result"))

    return derived


def _complete_trace_tool_event(call: dict[str, Any], result: dict[str, Any]) -> dict[str, Any]:
    started_at = call.get("timestamp")
    ended_at = result.get("timestamp")
    status = "ok"
    reason = ""
    if started_at is None or ended_at is None:
        status = "partial"
        reason = "missing_timestamp"
    exit_code = result.get("payload", {}).get("exit_code")
    if status == "ok" and exit_code not in (None, 0, "0"):
        status = "error"
    wall_ms = 0
    if started_at is not None and ended_at is not None and float(ended_at) >= float(started_at):
        wall_ms = int((float(ended_at) - float(started_at)) * 1000)
    elif started_at is not None and ended_at is not None:
        status = "partial"
        reason = "negative_duration"
    metadata = {
        "tool": call.get("tool", "unknown"),
        "trace_call_index": call.get("index"),
        "trace_result_index": result.get("index"),
        "trace_call_event_type": call.get("event_type"),
        "trace_result_event_type": result.get("event_type"),
        "trace_timing_key": f"{call.get('index')}:{result.get('index')}",
    }
    if call.get("call_id"):
        metadata["tool_call_id"] = call["call_id"]
    if reason:
        metadata["partial_reason"] = reason
    if exit_code is not None:
        metadata["exit_code"] = exit_code
    return _trace_event_payload(call, result, started_at, ended_at, wall_ms, status, metadata)


def _partial_trace_tool_event(record: dict[str, Any], *, reason: str) -> dict[str, Any]:
    timestamp = record.get("timestamp")
    metadata = {
        "tool": record.get("tool", "unknown"),
        "trace_event_index": record.get("index"),
        "trace_event_type": record.get("event_type"),
        "trace_timing_key": f"{record.get('index')}:partial:{reason}",
        "partial_reason": reason,
    }
    if record.get("call_id"):
        metadata["tool_call_id"] = record["call_id"]
    return _trace_event_payload(record, None, timestamp, timestamp, 0, "partial", metadata)


def _trace_event_payload(
    call: dict[str, Any],
    result: dict[str, Any] | None,
    started_at: float | None,
    ended_at: float | None,
    wall_ms: int,
    status: str,
    metadata: dict[str, Any],
) -> dict[str, Any]:
    payload = call.get("payload", {}) if isinstance(call.get("payload"), dict) else {}
    iteration = _coerce_int(payload.get("iteration") or payload.get("target_iteration") or payload.get("attack_iteration"))
    attack_iteration = _coerce_int(payload.get("attack_iteration"))
    phase = str(payload.get("phase") or payload.get("attack_phase") or "")
    role = _clean_role(str(call.get("role") or ""))
    tool = _clean_tool_name(call.get("tool") or "unknown")
    event = {
        "name": f"{role}.tool.{tool}" if role else f"tool.{tool}",
        "role": role,
        "category": "tool",
        "iteration": iteration,
        "phase": phase,
        "started_at": started_at,
        "ended_at": ended_at,
        "wall_ms": wall_ms,
        "status": status,
        "metadata": metadata,
    }
    if attack_iteration is not None:
        event["attack_iteration"] = attack_iteration
    return event


def _tool_call_id(item: dict[str, Any], payload: dict[str, Any]) -> str:
    for key in ("tool_call_id", "call_id", "id", "tool_use_id"):
        value = payload.get(key, item.get(key))
        if value is not None and str(value).strip():
            return str(value)
    return ""


def _coerce_timestamp(value: Any) -> float | None:
    try:
        if value is None or str(value).strip() == "":
            return None
        return float(value)
    except (TypeError, ValueError):
        return None


def _coerce_int(value: Any) -> int | None:
    try:
        if value is None or str(value).strip() == "":
            return None
        return int(value)
    except (TypeError, ValueError):
        return None


def _clean_role(value: str) -> str:
    role = str(value or "").strip().lower()
    if role in {"attacker", "attack-agent"}:
        return "attack"
    return role


def _clean_tool_name(value: Any) -> str:
    text = str(value or "unknown").strip() or "unknown"
    return "".join(ch if ch.isalnum() or ch in {"_", "-", "."} else "_" for ch in text).strip("_") or "unknown"


def _json_safe(value: Any) -> Any:
    try:
        json.dumps(value)
        return value
    except TypeError:
        if isinstance(value, dict):
            return {str(key): _json_safe(item) for key, item in value.items()}
        if isinstance(value, (list, tuple, set)):
            return [_json_safe(item) for item in value]
        return str(value)


__all__ = ["TimingEventScope", "TimingRecorder", "derive_trace_tool_timing_events"]

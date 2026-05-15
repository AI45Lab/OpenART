from __future__ import annotations

import time
from contextlib import contextmanager
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterator

from framework.core.helpers import write_json_artifact


@dataclass(slots=True)
class TimingRecorder:
    run_dir: str
    started_at: float = field(default_factory=time.time)
    phases_ms: dict[str, int] = field(default_factory=dict)
    metadata: dict[str, str] = field(default_factory=dict)
    total_ms: int = 0

    @property
    def path(self) -> Path:
        return Path(self.run_dir) / "timing.json"

    @contextmanager
    def phase(self, name: str) -> Iterator[None]:
        started = time.perf_counter()
        try:
            yield
        finally:
            elapsed_ms = int((time.perf_counter() - started) * 1000)
            self.phases_ms[name] = self.phases_ms.get(name, 0) + elapsed_ms
            self.flush()

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
                "metadata": self.metadata,
            },
            ensure_ascii=False,
        )


__all__ = ["TimingRecorder"]

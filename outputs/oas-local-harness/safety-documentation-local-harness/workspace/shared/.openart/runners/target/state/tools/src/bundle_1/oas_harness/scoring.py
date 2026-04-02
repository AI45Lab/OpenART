from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, List, Optional


@dataclass
class Checkpoint:
    # Keep compatibility with the common `Checkpoint(id, success)` form.
    # Some evaluators use keyword args: Checkpoint(total=1, result=...).
    id: int = 0
    success: int = 0

    def __init__(self, id: int = 0, success: int = 0, **kwargs):
        if kwargs:
            if "total" in kwargs and "id" not in kwargs:
                id = int(kwargs.get("total") or 0)
            if "result" in kwargs and "success" not in kwargs:
                success = int(kwargs.get("result") or 0)
        self.id = int(id)
        self.success = int(success)


@dataclass
class Result:
    checkpoints: List[Checkpoint]
    bonus: Optional[Callable] = None

    @property
    def points(self) -> int:
        return sum(int(c.success) for c in self.checkpoints)

    @property
    def total_points(self) -> int:
        # Some older code expects total_points; treat as points.
        return self.points

    def as_dict(self):
        return {
            "checkpoints": [
                {"id": c.id, "success": int(c.success)} for c in self.checkpoints
            ]
        }


def bonus_for_completing_any(results: List[Checkpoint]) -> int:
    return 1 if any(c.success for c in results) else 0


def bonus_for_completing_final(results: List[Checkpoint]) -> int:
    return 1 if results and results[-1].success else 0

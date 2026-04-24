from __future__ import annotations

from framework.attackers.base import AttackerBase


class AttackerRegistry:
    def __init__(self) -> None:
        self._classes: dict[str, type[AttackerBase]] = {}

    def register(self, name: str, attacker_cls: type[AttackerBase]) -> None:
        self._classes[name] = attacker_cls

    def get(self, name: str) -> type[AttackerBase]:
        if name not in self._classes:
            raise KeyError(f"Unknown attacker type: {name}")
        return self._classes[name]

    def create(self, name: str, **kwargs) -> AttackerBase:
        return self.get(name)(**kwargs)

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional


@dataclass(slots=True)
class MountSpec:
    host_path: str
    container_path: str
    read_only: bool = False


@dataclass(slots=True)
class PortSpec:
    host_port: Optional[int]
    container_port: int
    protocol: str = "tcp"


@dataclass(slots=True)
class HealthcheckSpec:
    command: list[str]
    interval_seconds: int = 10
    timeout_seconds: int = 5
    retries: int = 6


@dataclass(slots=True)
class ContainerSpec:
    name: str
    image: Optional[str] = None
    build_context: Optional[str] = None
    dockerfile: Optional[str] = None
    command: Optional[list[str]] = None
    env: dict[str, str] = field(default_factory=dict)
    mounts: list[MountSpec] = field(default_factory=list)
    ports: list[PortSpec] = field(default_factory=list)
    network: Optional[str] = None
    working_dir: Optional[str] = None
    healthcheck: Optional[HealthcheckSpec] = None
    lifecycle_log_path: Optional[str] = None
    labels: dict[str, str] = field(default_factory=dict)

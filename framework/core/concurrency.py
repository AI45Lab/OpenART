"""
Concurrency management for OpenART framework.

This module merges:
- ConcurrencyPolicy: Policy for managing concurrent runs
- ResourceLockManager: Manager for resource locks
- ResourceLease: Lease dataclass for resource locks
- ResourceLockError: Exception for lock conflicts
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Optional

from framework.models.specs import ConcurrencyDecision, ConcurrencySpec


@dataclass(slots=True)
class ResourceLease:
    """Represents a lease on a resource."""
    resource_key: str
    run_id: str
    acquired_at: float
    expires_at: float
    metadata: dict


class ResourceLockError(Exception):
    """Exception raised when a resource lock conflict occurs."""
    pass


class ResourceLockManager:
    """Manager for resource locks with lease-based expiration."""

    def __init__(self) -> None:
        self._locks: dict[str, ResourceLease] = {}

    def acquire_many(
        self,
        run_id: str,
        resource_keys: list[str],
        lease_seconds: int = 3600,
        metadata: Optional[dict] = None,
    ) -> list[ResourceLease]:
        now = time.time()
        metadata = metadata or {}

        self._reap_expired(now)

        for key in resource_keys:
            if key in self._locks:
                raise ResourceLockError(
                    f"Resource already locked: {key} by {self._locks[key].run_id}"
                )

        leases: list[ResourceLease] = []
        for key in resource_keys:
            lease = ResourceLease(
                resource_key=key,
                run_id=run_id,
                acquired_at=now,
                expires_at=now + lease_seconds,
                metadata=metadata,
            )
            self._locks[key] = lease
            leases.append(lease)

        return leases

    def release_many(self, run_id: str, resource_keys: list[str]) -> None:
        for key in resource_keys:
            lease = self._locks.get(key)
            if lease and lease.run_id == run_id:
                del self._locks[key]

    def release_all_for_run(self, run_id: str) -> None:
        to_delete = [
            key for key, lease in self._locks.items() if lease.run_id == run_id
        ]
        for key in to_delete:
            del self._locks[key]

    def is_free(self, resource_key: str) -> bool:
        self._reap_expired(time.time())
        return resource_key not in self._locks

    def list_locks(self) -> list[ResourceLease]:
        self._reap_expired(time.time())
        return list(self._locks.values())

    def renew_all_for_run(self, run_id: str, lease_seconds: int) -> None:
        now = time.time()
        for lease in self._locks.values():
            if lease.run_id == run_id:
                lease.expires_at = now + lease_seconds

    def _reap_expired(self, now: float) -> None:
        expired = [
            key for key, lease in self._locks.items() if lease.expires_at <= now
        ]
        for key in expired:
            del self._locks[key]


class ConcurrencyPolicy:
    """Policy for managing concurrent runs with resource locking."""

    def __init__(
        self,
        lock_manager: ResourceLockManager,
        max_local_parallel: int = 8,
    ) -> None:
        self.lock_manager = lock_manager
        self.max_local_parallel = max_local_parallel

    def can_start(
        self,
        run_id: str,
        spec: ConcurrencySpec,
        current_local_parallel: int,
    ) -> ConcurrencyDecision:
        if spec.mode == "local_only":
            if current_local_parallel >= self.max_local_parallel:
                return ConcurrencyDecision(
                    allowed=False,
                    reason="local capacity exhausted",
                )
            return ConcurrencyDecision(
                allowed=True,
                reason="local_only allowed",
            )

        if spec.mode == "shared_service":
            if not spec.resource_keys:
                return ConcurrencyDecision(
                    allowed=False,
                    reason="shared_service task missing resource_keys; serialize conservatively",
                )

            for key in spec.resource_keys:
                if not self.lock_manager.is_free(key):
                    return ConcurrencyDecision(
                        allowed=False,
                        reason=f"remote resource locked: {key}",
                    )

            return ConcurrencyDecision(
                allowed=True,
                reason="all shared resources free",
                required_locks=spec.resource_keys,
            )

        if spec.mode == "isolated_service":
            return ConcurrencyDecision(
                allowed=True,
                reason="requires isolated service provisioning",
                requires_isolated_service=True,
            )

        return ConcurrencyDecision(
            allowed=False,
            reason=f"unknown mode: {spec.mode}",
        )

    def acquire_if_needed(
        self,
        run_id: str,
        decision: ConcurrencyDecision,
        lease_seconds: int = 3600,
        metadata: dict | None = None,
    ) -> None:
        if decision.required_locks:
            self.lock_manager.acquire_many(
                run_id=run_id,
                resource_keys=decision.required_locks,
                lease_seconds=lease_seconds,
                metadata=metadata,
            )


__all__ = [
    "ConcurrencyPolicy",
    "ResourceLease",
    "ResourceLockError",
    "ResourceLockManager",
]
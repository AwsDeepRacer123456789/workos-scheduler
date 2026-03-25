"""
Weighted round-robin scheduler (in-memory).

KernelQ can use this to share dispatch turns across *tenants* so one noisy
neighbor does not permanently starve others, while still giving larger tenants
more turns when everyone has work waiting.

Rules implemented here:
- Each tenant has its own FIFO queue (order preserved *within* a tenant).
- A repeating "cycle" lists tenant_ids in proportion to their weights.
  Example: weights {a: 2, b: 1} → cycle [a, a, b] — in each full lap, `a`
  is visited twice and `b` once, so `a` gets about twice the chances to
  dequeue when both have jobs.
- If the next tenant in the cycle has no jobs, we skip that turn and keep
  rotating (so idle tenants do not block others).

This is pure Python standard library — no Kafka, no DB.
"""

from __future__ import annotations

import math
from collections import deque
from dataclasses import dataclass
from functools import reduce


@dataclass(frozen=True)
class Job:
    """
    Minimal job for multi-tenant scheduling demos.

    - job_id: unique id for this job
    - tenant_id: must match a key in the scheduler's weights map
    - created_at: integer timestamp; used for ordering only if you sort jobs
      before enqueue — *within* one tenant we preserve FIFO enqueue order.
    """

    job_id: str
    tenant_id: str
    created_at: int


def _gcd_of_weights(values: list[int]) -> int:
    """Greatest common divisor of all positive weights (shortens the cycle)."""
    return reduce(math.gcd, values)


def _build_weight_cycle(weights: dict[str, int]) -> list[str]:
    """
    Build one lap of the weighted round-robin pattern.

    Each tenant_id appears `w` times in the lap, where `w` is its (possibly
    GCD-reduced) weight. Lap order follows dict insertion order (Python 3.7+).

    Example: {"tenant-a": 2, "tenant-b": 1} → ["tenant-a", "tenant-a", "tenant-b"]
    """
    g = _gcd_of_weights(list(weights.values()))
    reduced = {tid: w // g for tid, w in weights.items()}
    lap: list[str] = []
    for tid, w in reduced.items():
        lap.extend([tid] * w)
    return lap


class WeightedRoundRobinScheduler:
    """
    Weighted round-robin across tenants.

    The constructor takes a mapping `tenant_id -> positive integer weight`.
    Higher weight ⇒ more slots in each lap ⇒ more dequeue *opportunities*
    when that tenant still has jobs waiting.
    """

    def __init__(self, weights: dict[str, int]) -> None:
        if not weights:
            raise ValueError("weights must not be empty")
        for tid, w in weights.items():
            if w <= 0:
                raise ValueError(f"weight for {tid!r} must be a positive integer, got {w}")

        # One FIFO queue per tenant (unknown tenants cannot enqueue).
        self._queues: dict[str, deque[Job]] = {tid: deque() for tid in weights}

        # Precomputed repeating pattern for one full lap of weighted turns.
        self._cycle: list[str] = _build_weight_cycle(weights)
        # Index into _cycle: where we start looking on the next dequeue/peek.
        self._cycle_pos: int = 0

    def enqueue(self, job: Job) -> None:
        """Append a job to its tenant's queue (FIFO within that tenant)."""

        if job.tenant_id not in self._queues:
            raise ValueError(
                f"unknown tenant_id {job.tenant_id!r}; "
                f"allowed tenants: {sorted(self._queues.keys())}"
            )
        self._queues[job.tenant_id].append(job)

    def dequeue(self) -> Job | None:
        """
        Remove and return the next job according to weighted round-robin.

        We walk at most one full lap of the cycle. At each step we look at the
        tenant for the current slot, advance the cycle pointer, and if that
        tenant has jobs we pop the oldest (FIFO). Empty tenants are skipped
        without dequeuing.
        """

        if self.size() == 0:
            return None

        n = len(self._cycle)
        # At most one full lap — if there is any job, some tenant must have one.
        for _ in range(n):
            tid = self._cycle[self._cycle_pos]
            self._cycle_pos = (self._cycle_pos + 1) % n
            q = self._queues[tid]
            if q:
                return q.popleft()

        # Should be unreachable if size() > 0 and queues stay consistent.
        return None

    def peek(self) -> Job | None:
        """
        Return the next job that dequeue() would return, without removing it.

        Does not advance the round-robin pointer (peek is non-mutating).
        """

        if self.size() == 0:
            return None

        n = len(self._cycle)
        pos = self._cycle_pos
        for _ in range(n):
            tid = self._cycle[pos]
            q = self._queues[tid]
            pos = (pos + 1) % n
            if q:
                return q[0]
        return None

    def size(self) -> int:
        """Total number of jobs waiting across all tenants."""

        return sum(len(q) for q in self._queues.values())

    def tenant_queue_sizes(self) -> dict[str, int]:
        """Per-tenant waiting counts (every known tenant appears in the dict)."""

        return {tid: len(q) for tid, q in self._queues.items()}

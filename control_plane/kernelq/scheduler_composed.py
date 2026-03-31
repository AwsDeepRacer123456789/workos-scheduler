"""
Composed scheduler (in-memory, educational version).

This module shows how KernelQ can combine multiple scheduling ideas in one flow:

1) Admission control with a bounded total capacity
2) Weighted round-robin (WRR) across tenants for fairness
3) Priority selection within the chosen tenant
4) created_at tie-break within equal priority

Design goals:
- Beginner-friendly and easy to read
- Standard library only (no external packages)
- Deterministic behavior for tests/interviews
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from functools import reduce

from .enqueue_result import EnqueueResult


@dataclass(frozen=True)
class Job:
    """
    Minimal job model for composed scheduling.

    - job_id: unique identifier for the job
    - tenant_id: tenant/customer this job belongs to
    - priority: larger number means "more important"
    - created_at: integer timestamp (smaller = older)
    """

    job_id: str
    tenant_id: str
    priority: int
    created_at: int


def _gcd_of_weights(values: list[int]) -> int:
    """Greatest common divisor for positive weights."""
    return reduce(math.gcd, values)


def _build_weight_cycle(weights: dict[str, int]) -> list[str]:
    """
    Build one weighted round-robin lap.

    Example:
        {"tenant-a": 2, "tenant-b": 1}
    becomes:
        ["tenant-a", "tenant-a", "tenant-b"]

    We first divide by the GCD to keep the cycle shorter but equivalent.
    """
    g = _gcd_of_weights(list(weights.values()))
    reduced = {tenant_id: w // g for tenant_id, w in weights.items()}

    cycle: list[str] = []
    for tenant_id, w in reduced.items():
        cycle.extend([tenant_id] * w)
    return cycle


class ComposedScheduler:
    """
    Combine bounded admission + WRR fairness + per-tenant priority.

    Behavior:
    - Global capacity limits the *total* number of queued jobs.
    - enqueue() returns typed EnqueueResult outcomes.
    - dequeue() picks:
        (a) next tenant by WRR (skipping empty tenants),
        (b) best job in that tenant by priority, then created_at.
    """

    def __init__(self, capacity: int, weights: dict[str, int]) -> None:
        """
        Create a scheduler.

        Args:
            capacity: Max total queued jobs across all tenants.
            weights: Mapping tenant_id -> positive integer weight.
        """
        if capacity <= 0:
            raise ValueError("capacity must be a positive integer")
        if not weights:
            raise ValueError("weights must not be empty")
        for tenant_id, w in weights.items():
            if not tenant_id.strip():
                raise ValueError("tenant ids in weights must not be blank")
            if w <= 0:
                raise ValueError(
                    f"weight for {tenant_id!r} must be a positive integer, got {w}"
                )

        self._capacity = capacity

        # One in-memory list per tenant.
        # We keep plain lists for readability. For each dequeue, we scan only
        # the selected tenant's list to find the "best" job.
        self._queues: dict[str, list[Job]] = {tenant_id: [] for tenant_id in weights}

        # Precomputed weighted cycle and pointer.
        self._cycle: list[str] = _build_weight_cycle(weights)
        self._cycle_pos: int = 0

    def enqueue(self, job: Job) -> EnqueueResult:
        """
        Try to add a job to the scheduler.

        Rejection rules:
        - REJECTED_INVALID if job_id or tenant_id is blank
        - REJECTED_FULL if total size already reached capacity
        - REJECTED_INVALID if tenant_id is unknown
        """
        if not job.job_id.strip():
            return EnqueueResult.rejected_invalid("job_id must not be blank")
        if not job.tenant_id.strip():
            return EnqueueResult.rejected_invalid("tenant_id must not be blank")
        if job.tenant_id not in self._queues:
            return EnqueueResult.rejected_invalid(
                f"unknown tenant_id {job.tenant_id!r}; allowed tenants: {sorted(self._queues)}"
            )
        if self.size() >= self._capacity:
            return EnqueueResult.rejected_full("queue is full")

        self._queues[job.tenant_id].append(job)
        return EnqueueResult.accepted("accepted")

    def dequeue(self) -> Job | None:
        """
        Remove and return the next job under composed policy.

        Steps:
        1) Choose tenant by WRR (skip empty tenant queues)
        2) Inside that tenant, choose highest priority
        3) Break priority ties by earliest created_at
        """
        tenant_id = self._next_tenant_advance()
        if tenant_id is None:
            return None

        tenant_jobs = self._queues[tenant_id]
        index = self._best_job_index(tenant_jobs)
        return tenant_jobs.pop(index)

    def peek(self) -> Job | None:
        """
        Return the next job dequeue() would return, without removing it.

        Important:
        - Does NOT mutate queues
        - Does NOT advance WRR pointer
        """
        tenant_id = self._next_tenant_no_advance()
        if tenant_id is None:
            return None

        tenant_jobs = self._queues[tenant_id]
        index = self._best_job_index(tenant_jobs)
        return tenant_jobs[index]

    def size(self) -> int:
        """Total queued jobs across all tenants."""
        return sum(len(q) for q in self._queues.values())

    def tenant_queue_sizes(self) -> dict[str, int]:
        """Per-tenant queued job counts."""
        return {tenant_id: len(q) for tenant_id, q in self._queues.items()}

    def remaining_capacity(self) -> int:
        """How many more jobs can be admitted before hitting capacity."""
        return self._capacity - self.size()

    def _next_tenant_advance(self) -> str | None:
        """
        WRR tenant selection that advances the internal cycle pointer.

        We check at most one full lap of the cycle. Any tenant with waiting jobs
        is eligible; empty tenants are skipped.
        """
        if self.size() == 0:
            return None

        n = len(self._cycle)
        for _ in range(n):
            tenant_id = self._cycle[self._cycle_pos]
            self._cycle_pos = (self._cycle_pos + 1) % n
            if self._queues[tenant_id]:
                return tenant_id
        return None

    def _next_tenant_no_advance(self) -> str | None:
        """
        WRR tenant selection for peek() without mutating the cycle pointer.
        """
        if self.size() == 0:
            return None

        n = len(self._cycle)
        pos = self._cycle_pos
        for _ in range(n):
            tenant_id = self._cycle[pos]
            pos = (pos + 1) % n
            if self._queues[tenant_id]:
                return tenant_id
        return None

    @staticmethod
    def _best_job_index(jobs: list[Job]) -> int:
        """
        Return the index of the best job in a tenant queue.

        Ranking:
        - Higher priority first
        - For equal priority, older created_at first
        - For fully equal values, smaller job_id first for deterministic behavior
        """
        best_index = 0
        best = jobs[0]

        for i in range(1, len(jobs)):
            candidate = jobs[i]
            if (
                candidate.priority > best.priority
                or (
                    candidate.priority == best.priority
                    and candidate.created_at < best.created_at
                )
                or (
                    candidate.priority == best.priority
                    and candidate.created_at == best.created_at
                    and candidate.job_id < best.job_id
                )
            ):
                best = candidate
                best_index = i

        return best_index

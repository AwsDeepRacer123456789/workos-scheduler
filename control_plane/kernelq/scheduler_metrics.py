"""
In-memory counters for scheduler simulation and tests.

These metrics match the "Scheduler Simulation Metrics" section in docs/perf.md.
They are intentionally simple: no threads, no external services—just tallies you
can update from a harness while enqueueing and dequeuing jobs.

Typical usage:
    m = SchedulerMetrics()
    m.record_enqueue_result(result.status)
    ...
    m.record_dispatch(job)
    m.observe_queue_depth(scheduler.size())
    print(m.snapshot())
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol

from .enqueue_result import EnqueueStatus


class _DispatchableJob(Protocol):
    """Anything with tenant_id and priority can be passed to record_dispatch."""

    tenant_id: str
    priority: int


@dataclass
class SchedulerMetrics:
    """
    Running totals for enqueue outcomes, dispatches, and queue depth.

    Counters start at zero. Per-tenant and per-priority maps grow keys as you
    see them—missing keys mean zero dispatches so far.
    """

    enqueue_accepted_count: int = 0
    enqueue_rejected_full_count: int = 0
    enqueue_rejected_invalid_count: int = 0

    dispatch_count_total: int = 0
    dispatch_count_by_tenant: dict[str, int] = field(default_factory=dict)
    dispatch_count_by_priority: dict[int, int] = field(default_factory=dict)

    queue_depth_peak: int = 0

    def record_enqueue_result(self, status: EnqueueStatus) -> None:
        """
        Bump the counter that matches this enqueue outcome.

        Use the status from EnqueueResult (or the same enum directly in tests).
        """
        if status is EnqueueStatus.ACCEPTED:
            self.enqueue_accepted_count += 1
        elif status is EnqueueStatus.REJECTED_FULL:
            self.enqueue_rejected_full_count += 1
        elif status is EnqueueStatus.REJECTED_INVALID:
            self.enqueue_rejected_invalid_count += 1
        else:
            # Helps catch typos or future enum values during development.
            raise ValueError(f"unknown EnqueueStatus: {status!r}")

    def record_dispatch(self, job: _DispatchableJob) -> None:
        """
        Count one job leaving the scheduler (dequeue).

        Expects ``job.tenant_id`` and ``job.priority`` (same shape as composed
        scheduler ``Job`` objects).
        """
        self.dispatch_count_total += 1

        tid = job.tenant_id
        self.dispatch_count_by_tenant[tid] = self.dispatch_count_by_tenant.get(tid, 0) + 1

        pri = job.priority
        self.dispatch_count_by_priority[pri] = self.dispatch_count_by_priority.get(pri, 0) + 1

    def observe_queue_depth(self, depth: int) -> None:
        """
        Record current queue depth; keep the highest value ever seen.

        Call this after enqueue/dequeue with ``scheduler.size()`` (or similar)
        so you capture backlog under your simulation workload.
        """
        if depth < 0:
            raise ValueError("depth must not be negative")
        if depth > self.queue_depth_peak:
            self.queue_depth_peak = depth

    def snapshot(self) -> dict[str, Any]:
        """
        Return a plain dict copy of all metrics (safe to log or serialize).

        Nested dicts are shallow-copied so callers cannot mutate our internal
        maps by accident.
        """
        return {
            "enqueue_accepted_count": self.enqueue_accepted_count,
            "enqueue_rejected_full_count": self.enqueue_rejected_full_count,
            "enqueue_rejected_invalid_count": self.enqueue_rejected_invalid_count,
            "dispatch_count_total": self.dispatch_count_total,
            "dispatch_count_by_tenant": dict(self.dispatch_count_by_tenant),
            "dispatch_count_by_priority": dict(self.dispatch_count_by_priority),
            "queue_depth_peak": self.queue_depth_peak,
        }

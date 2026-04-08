#!/usr/bin/env python3
"""
Compare FIFO, Priority, Weighted RR, and Composed scheduler behavior.

This script is intentionally beginner-friendly:
- one fixed workload
- no external libraries
- clear printed summaries

Run from repo root:
    python3 control_plane/scripts/compare_schedulers.py
"""

from __future__ import annotations

import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

# Allow direct script execution without installing a package.
REPO_ROOT = Path(__file__).resolve().parent.parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from control_plane.kernelq.enqueue_result import EnqueueStatus
from control_plane.kernelq.scheduler_composed import ComposedScheduler, Job as ComposedJob
from control_plane.kernelq.scheduler_fifo import FIFOScheduler, Job as FIFOJob
from control_plane.kernelq.scheduler_metrics import SchedulerMetrics
from control_plane.kernelq.scheduler_priority import Job as PriorityJob
from control_plane.kernelq.scheduler_priority import PriorityScheduler
from control_plane.kernelq.scheduler_weighted_rr import Job as WRRJob
from control_plane.kernelq.scheduler_weighted_rr import WeightedRoundRobinScheduler


@dataclass(frozen=True)
class WorkloadJob:
    """Logical workload job used across all scheduler experiments."""

    job_id: str
    tenant_id: str
    priority: int
    created_at: int


def _build_workload() -> list[WorkloadJob]:
    """
    Fixed, deterministic workload shared by every scheduler.

    Includes:
    - multiple tenants
    - mixed priorities (1, 2, 5, 10)
    - one invalid job (blank job_id)
    - one extra valid job beyond capacity (queue-full rejection)
    """
    return [
        WorkloadJob("a-low", "tenant-a", priority=1, created_at=-8),
        WorkloadJob("b-one", "tenant-b", priority=5, created_at=-7),
        WorkloadJob("a-high", "tenant-a", priority=10, created_at=-6),
        WorkloadJob("b-two", "tenant-b", priority=1, created_at=-5),
        WorkloadJob("", "tenant-a", priority=1, created_at=-4),  # invalid job_id
        WorkloadJob("a-mid", "tenant-a", priority=5, created_at=-3),
        WorkloadJob("b-three", "tenant-b", priority=2, created_at=-2),
        WorkloadJob("overflow", "tenant-a", priority=10, created_at=-1),  # full rejection
    ]


def _is_valid(job: WorkloadJob, allowed_tenants: set[str]) -> bool:
    """Simple admission validation shared by non-composed schedulers."""
    return bool(job.job_id.strip()) and bool(job.tenant_id.strip()) and job.tenant_id in allowed_tenants


def _print_result_block(title: str, result: dict[str, Any]) -> None:
    print(f"=== {title} Results ===")
    print(f"average_queue_wait_time: {result['average_queue_wait_time']}")
    print(f"average_queue_wait_time_by_tenant: {result['average_queue_wait_time_by_tenant']}")
    print(f"average_queue_wait_time_by_priority: {result['average_queue_wait_time_by_priority']}")
    print(f"dispatch_count_by_tenant: {result['dispatch_count_by_tenant']}")
    print(f"enqueue_rejected_full_count: {result['enqueue_rejected_full_count']}")
    print(f"enqueue_rejected_invalid_count: {result['enqueue_rejected_invalid_count']}")
    print()


def _run_fifo(workload: list[WorkloadJob], capacity: int, allowed_tenants: set[str]) -> dict[str, Any]:
    scheduler = FIFOScheduler()
    metrics = SchedulerMetrics()
    by_id: dict[str, WorkloadJob] = {}

    # Enqueue phase with explicit admission rules.
    for job in workload:
        if not _is_valid(job, allowed_tenants):
            metrics.record_enqueue_result(EnqueueStatus.REJECTED_INVALID)
            metrics.observe_queue_depth(scheduler.size())
            continue
        if scheduler.size() >= capacity:
            metrics.record_enqueue_result(EnqueueStatus.REJECTED_FULL)
            metrics.observe_queue_depth(scheduler.size())
            continue

        scheduler.enqueue(FIFOJob(job_id=job.job_id, created_at=job.created_at))
        by_id[job.job_id] = job
        metrics.record_enqueue_result(EnqueueStatus.ACCEPTED)
        metrics.observe_queue_depth(scheduler.size())

    # Dequeue phase with a deterministic integer dispatch clock.
    tick = 0
    while True:
        out = scheduler.dequeue()
        if out is None:
            break
        original = by_id[out.job_id]
        metrics.record_dispatch(original, dispatch_time=tick)
        metrics.observe_queue_depth(scheduler.size())
        tick += 1

    return {
        "average_queue_wait_time": metrics.average_queue_wait_time(),
        "average_queue_wait_time_by_tenant": metrics.average_queue_wait_time_by_tenant(),
        "average_queue_wait_time_by_priority": metrics.average_queue_wait_time_by_priority(),
        "dispatch_count_by_tenant": dict(metrics.dispatch_count_by_tenant),
        "enqueue_rejected_full_count": metrics.enqueue_rejected_full_count,
        "enqueue_rejected_invalid_count": metrics.enqueue_rejected_invalid_count,
    }


def _run_priority(
    workload: list[WorkloadJob], capacity: int, allowed_tenants: set[str]
) -> dict[str, Any]:
    scheduler = PriorityScheduler()
    metrics = SchedulerMetrics()
    by_id: dict[str, WorkloadJob] = {}

    for job in workload:
        if not _is_valid(job, allowed_tenants):
            metrics.record_enqueue_result(EnqueueStatus.REJECTED_INVALID)
            metrics.observe_queue_depth(scheduler.size())
            continue
        if scheduler.size() >= capacity:
            metrics.record_enqueue_result(EnqueueStatus.REJECTED_FULL)
            metrics.observe_queue_depth(scheduler.size())
            continue

        scheduler.enqueue(
            PriorityJob(
                job_id=job.job_id,
                priority=job.priority,
                created_at=job.created_at,
            )
        )
        by_id[job.job_id] = job
        metrics.record_enqueue_result(EnqueueStatus.ACCEPTED)
        metrics.observe_queue_depth(scheduler.size())

    tick = 0
    while True:
        out = scheduler.dequeue()
        if out is None:
            break
        original = by_id[out.job_id]
        metrics.record_dispatch(original, dispatch_time=tick)
        metrics.observe_queue_depth(scheduler.size())
        tick += 1

    return {
        "average_queue_wait_time": metrics.average_queue_wait_time(),
        "average_queue_wait_time_by_tenant": metrics.average_queue_wait_time_by_tenant(),
        "average_queue_wait_time_by_priority": metrics.average_queue_wait_time_by_priority(),
        "dispatch_count_by_tenant": dict(metrics.dispatch_count_by_tenant),
        "enqueue_rejected_full_count": metrics.enqueue_rejected_full_count,
        "enqueue_rejected_invalid_count": metrics.enqueue_rejected_invalid_count,
    }


def _run_weighted_rr(
    workload: list[WorkloadJob], capacity: int, weights: dict[str, int], allowed_tenants: set[str]
) -> dict[str, Any]:
    scheduler = WeightedRoundRobinScheduler(weights)
    metrics = SchedulerMetrics()
    by_id: dict[str, WorkloadJob] = {}

    for job in workload:
        if not _is_valid(job, allowed_tenants):
            metrics.record_enqueue_result(EnqueueStatus.REJECTED_INVALID)
            metrics.observe_queue_depth(scheduler.size())
            continue
        if scheduler.size() >= capacity:
            metrics.record_enqueue_result(EnqueueStatus.REJECTED_FULL)
            metrics.observe_queue_depth(scheduler.size())
            continue

        scheduler.enqueue(
            WRRJob(
                job_id=job.job_id,
                tenant_id=job.tenant_id,
                created_at=job.created_at,
            )
        )
        by_id[job.job_id] = job
        metrics.record_enqueue_result(EnqueueStatus.ACCEPTED)
        metrics.observe_queue_depth(scheduler.size())

    tick = 0
    while True:
        out = scheduler.dequeue()
        if out is None:
            break
        original = by_id[out.job_id]
        metrics.record_dispatch(original, dispatch_time=tick)
        metrics.observe_queue_depth(scheduler.size())
        tick += 1

    return {
        "average_queue_wait_time": metrics.average_queue_wait_time(),
        "average_queue_wait_time_by_tenant": metrics.average_queue_wait_time_by_tenant(),
        "average_queue_wait_time_by_priority": metrics.average_queue_wait_time_by_priority(),
        "dispatch_count_by_tenant": dict(metrics.dispatch_count_by_tenant),
        "enqueue_rejected_full_count": metrics.enqueue_rejected_full_count,
        "enqueue_rejected_invalid_count": metrics.enqueue_rejected_invalid_count,
    }


def _run_composed(
    workload: list[WorkloadJob], capacity: int, weights: dict[str, int]
) -> dict[str, Any]:
    scheduler = ComposedScheduler(capacity=capacity, weights=weights)
    metrics = SchedulerMetrics()

    for job in workload:
        result = scheduler.enqueue(
            ComposedJob(
                job_id=job.job_id,
                tenant_id=job.tenant_id,
                priority=job.priority,
                created_at=job.created_at,
            )
        )
        metrics.record_enqueue_result(result.status)
        metrics.observe_queue_depth(scheduler.size())

    tick = 0
    while True:
        out = scheduler.dequeue()
        if out is None:
            break
        metrics.record_dispatch(out, dispatch_time=tick)
        metrics.observe_queue_depth(scheduler.size())
        tick += 1

    return {
        "average_queue_wait_time": metrics.average_queue_wait_time(),
        "average_queue_wait_time_by_tenant": metrics.average_queue_wait_time_by_tenant(),
        "average_queue_wait_time_by_priority": metrics.average_queue_wait_time_by_priority(),
        "dispatch_count_by_tenant": dict(metrics.dispatch_count_by_tenant),
        "enqueue_rejected_full_count": metrics.enqueue_rejected_full_count,
        "enqueue_rejected_invalid_count": metrics.enqueue_rejected_invalid_count,
    }


def main() -> None:
    weights = {"tenant-a": 2, "tenant-b": 1}
    capacity = 6
    allowed_tenants = set(weights.keys())
    workload = _build_workload()

    fifo_result = _run_fifo(workload, capacity=capacity, allowed_tenants=allowed_tenants)
    priority_result = _run_priority(workload, capacity=capacity, allowed_tenants=allowed_tenants)
    wrr_result = _run_weighted_rr(
        workload, capacity=capacity, weights=weights, allowed_tenants=allowed_tenants
    )
    composed_result = _run_composed(workload, capacity=capacity, weights=weights)

    _print_result_block("FIFO", fifo_result)
    _print_result_block("Priority", priority_result)
    _print_result_block("Weighted RR", wrr_result)
    _print_result_block("Composed", composed_result)


if __name__ == "__main__":
    main()

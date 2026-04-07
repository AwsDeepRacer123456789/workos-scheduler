#!/usr/bin/env python3
"""
KernelQ: tiny simulation of the composed scheduler + metrics.

This is a teaching script. It does not connect to Kafka or a database.

Run from the repository root (so imports work):

    python3 control_plane/scripts/simulate_composed_scheduler.py

If you see ImportError for ``control_plane``, add the repo root to PYTHONPATH:

    PYTHONPATH=. python3 control_plane/scripts/simulate_composed_scheduler.py
"""

from __future__ import annotations

import sys
from pathlib import Path

# Allow `python path/to/simulate_composed_scheduler.py` without installing the package.
_REPO_ROOT = Path(__file__).resolve().parent.parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from control_plane.kernelq.scheduler_composed import ComposedScheduler, Job
from control_plane.kernelq.scheduler_metrics import SchedulerMetrics


def main() -> None:
    # --- Fixed scenario (deterministic every run) ---
    weights = {"tenant-a": 2, "tenant-b": 1}
    capacity = 6

    # Workload: mix of tenants, priorities, and created_at values.
    # Order is chosen on purpose:
    # - Several valid jobs on both tenants (four jobs).
    # - One invalid job (blank job_id) — rejected, does not use queue space.
    # - Two more valid jobs so the queue reaches exactly `capacity` (6).
    # - One more valid job while full → REJECTED_FULL.
    workload: list[Job] = [
        Job("a-low", "tenant-a", priority=1, created_at=-8),
        Job("b-one", "tenant-b", priority=5, created_at=-7),
        Job("a-high", "tenant-a", priority=10, created_at=-6),
        Job("b-two", "tenant-b", priority=1, created_at=-5),
        # Invalid: empty job_id (validation fails before capacity check).
        Job("", "tenant-a", priority=1, created_at=-4),
        Job("a-mid", "tenant-a", priority=5, created_at=-3),
        Job("b-three", "tenant-b", priority=2, created_at=-2),
        # Seventh submission: queue already has 6 jobs → rejected_full.
        Job("overflow", "tenant-a", priority=99, created_at=-1),
    ]

    sched = ComposedScheduler(capacity=capacity, weights=weights)
    metrics = SchedulerMetrics()

    enqueue_log: list[tuple[str, str]] = []

    print("=== Enqueue phase ===\n")
    for i, job in enumerate(workload, start=1):
        label = job.job_id if job.job_id.strip() else "(blank job_id)"
        result = sched.enqueue(job)
        metrics.record_enqueue_result(result.status)
        metrics.observe_queue_depth(sched.size())

        status_line = f"{result.status.value}: {result.message}"
        enqueue_log.append((label, status_line))
        print(f"  [{i:2}] submit {label!r:20} -> {status_line}")

    print()
    print("=== Dequeue phase (until empty) ===\n")

    dispatch_order: list[str] = []
    # Simple deterministic dispatch clock: starts at 0, ticks by 1 per dispatch.
    dispatch_tick = 0
    while True:
        job = sched.dequeue()
        if job is None:
            break
        metrics.record_dispatch(job, dispatch_time=dispatch_tick)
        metrics.observe_queue_depth(sched.size())
        dispatch_order.append(job.job_id)
        print(f"  dispatch {job.job_id!r} (tenant={job.tenant_id!r}, priority={job.priority})")
        dispatch_tick += 1

    print()
    print("=== Summary ===\n")

    print("Enqueue results (in order):")
    for label, line in enqueue_log:
        print(f"  - {label}: {line}")

    print()
    print("Dispatch order (job_id):")
    print("  " + " -> ".join(dispatch_order))

    print()
    print("=== Wait Time Summary ===\n")
    print(f"  average_queue_wait_time: {metrics.average_queue_wait_time()}")
    print(f"  average_queue_wait_time_by_tenant: {metrics.average_queue_wait_time_by_tenant()}")
    print(
        "  average_queue_wait_time_by_priority: "
        f"{metrics.average_queue_wait_time_by_priority()}"
    )

    print()
    print("Final metric snapshot:")
    snap = metrics.snapshot()
    for key in sorted(snap.keys()):
        print(f"  {key}: {snap[key]}")

    print()


if __name__ == "__main__":
    main()

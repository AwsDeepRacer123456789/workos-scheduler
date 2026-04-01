"""
Tests for SchedulerMetrics: enqueue counters, dispatch breakdowns, queue depth peak, snapshot.
"""

from dataclasses import dataclass

from control_plane.kernelq.enqueue_result import EnqueueStatus
from control_plane.kernelq.scheduler_metrics import SchedulerMetrics


@dataclass
class _FakeJob:
    """Minimal stand-in for composed scheduler jobs (tenant_id + priority only)."""

    tenant_id: str
    priority: int


def test_record_enqueue_result_increments_accepted_count():
    m = SchedulerMetrics()
    m.record_enqueue_result(EnqueueStatus.ACCEPTED)
    m.record_enqueue_result(EnqueueStatus.ACCEPTED)
    assert m.enqueue_accepted_count == 2
    assert m.enqueue_rejected_full_count == 0
    assert m.enqueue_rejected_invalid_count == 0


def test_record_enqueue_result_increments_rejected_full_count():
    m = SchedulerMetrics()
    m.record_enqueue_result(EnqueueStatus.REJECTED_FULL)
    m.record_enqueue_result(EnqueueStatus.REJECTED_FULL)
    assert m.enqueue_rejected_full_count == 2
    assert m.enqueue_accepted_count == 0
    assert m.enqueue_rejected_invalid_count == 0


def test_record_enqueue_result_increments_rejected_invalid_count():
    m = SchedulerMetrics()
    m.record_enqueue_result(EnqueueStatus.REJECTED_INVALID)
    assert m.enqueue_rejected_invalid_count == 1
    assert m.enqueue_accepted_count == 0
    assert m.enqueue_rejected_full_count == 0


def test_record_dispatch_updates_total_tenant_and_priority():
    m = SchedulerMetrics()
    m.record_dispatch(_FakeJob("tenant-a", 10))
    m.record_dispatch(_FakeJob("tenant-a", 10))
    m.record_dispatch(_FakeJob("tenant-b", 5))

    assert m.dispatch_count_total == 3
    assert m.dispatch_count_by_tenant == {"tenant-a": 2, "tenant-b": 1}
    assert m.dispatch_count_by_priority == {10: 2, 5: 1}


def test_observe_queue_depth_keeps_maximum_seen():
    m = SchedulerMetrics()
    m.observe_queue_depth(2)
    m.observe_queue_depth(1)
    m.observe_queue_depth(5)
    m.observe_queue_depth(3)
    assert m.queue_depth_peak == 5


def test_snapshot_returns_expected_structure_and_values():
    m = SchedulerMetrics()
    m.record_enqueue_result(EnqueueStatus.ACCEPTED)
    m.record_enqueue_result(EnqueueStatus.REJECTED_FULL)
    m.record_dispatch(_FakeJob("t1", 7))
    m.observe_queue_depth(4)

    snap = m.snapshot()

    assert snap == {
        "enqueue_accepted_count": 1,
        "enqueue_rejected_full_count": 1,
        "enqueue_rejected_invalid_count": 0,
        "dispatch_count_total": 1,
        "dispatch_count_by_tenant": {"t1": 1},
        "dispatch_count_by_priority": {7: 1},
        "queue_depth_peak": 4,
    }

    # Snapshot dicts are copies — mutating them does not change metrics.
    snap["dispatch_count_by_tenant"]["t1"] = 99
    assert m.dispatch_count_by_tenant["t1"] == 1

"""
Tests for SchedulerMetrics: enqueue counters, dispatch breakdowns, queue depth peak, snapshot.
"""

from dataclasses import dataclass

from control_plane.kernelq.enqueue_result import EnqueueStatus
from control_plane.kernelq.scheduler_metrics import SchedulerMetrics


@dataclass
class _FakeJob:
    """Minimal stand-in for composed scheduler jobs."""

    tenant_id: str
    priority: int
    created_at: int = 0


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
    m.record_dispatch(_FakeJob("tenant-a", 10, created_at=10), dispatch_time=20)
    m.record_dispatch(_FakeJob("tenant-a", 10, created_at=12), dispatch_time=22)
    m.record_dispatch(_FakeJob("tenant-b", 5, created_at=18), dispatch_time=30)

    assert m.dispatch_count_total == 3
    assert m.dispatch_count_by_tenant == {"tenant-a": 2, "tenant-b": 1}
    assert m.dispatch_count_by_priority == {10: 2, 5: 1}
    assert m.total_queue_wait_time == 32  # (10 + 10 + 12)


def test_record_dispatch_computes_wait_time_per_total_tenant_and_priority():
    m = SchedulerMetrics()
    # Wait times: 5 and 8
    m.record_dispatch(_FakeJob("tenant-a", 1, created_at=10), dispatch_time=15)
    m.record_dispatch(_FakeJob("tenant-b", 3, created_at=20), dispatch_time=28)

    assert m.total_queue_wait_time == 13
    assert m.total_queue_wait_time_by_tenant == {"tenant-a": 5, "tenant-b": 8}
    assert m.total_queue_wait_time_by_priority == {1: 5, 3: 8}


def test_average_queue_wait_time_returns_expected_value():
    m = SchedulerMetrics()
    # Wait times: 5, 7, 8 -> average = 20 / 3
    m.record_dispatch(_FakeJob("tenant-a", 1, created_at=10), dispatch_time=15)
    m.record_dispatch(_FakeJob("tenant-a", 1, created_at=13), dispatch_time=20)
    m.record_dispatch(_FakeJob("tenant-b", 2, created_at=12), dispatch_time=20)

    assert m.average_queue_wait_time() == 20 / 3


def test_average_queue_wait_time_by_tenant_returns_expected_values():
    m = SchedulerMetrics()
    # tenant-a waits: 5 and 7 -> 6.0
    # tenant-b waits: 8 -> 8.0
    m.record_dispatch(_FakeJob("tenant-a", 1, created_at=10), dispatch_time=15)
    m.record_dispatch(_FakeJob("tenant-a", 2, created_at=13), dispatch_time=20)
    m.record_dispatch(_FakeJob("tenant-b", 1, created_at=12), dispatch_time=20)

    assert m.average_queue_wait_time_by_tenant() == {"tenant-a": 6.0, "tenant-b": 8.0}


def test_average_queue_wait_time_by_priority_returns_expected_values():
    m = SchedulerMetrics()
    # priority 1 waits: 5 and 9 -> 7.0
    # priority 3 waits: 8 -> 8.0
    m.record_dispatch(_FakeJob("tenant-a", 1, created_at=10), dispatch_time=15)
    m.record_dispatch(_FakeJob("tenant-b", 1, created_at=11), dispatch_time=20)
    m.record_dispatch(_FakeJob("tenant-a", 3, created_at=12), dispatch_time=20)

    assert m.average_queue_wait_time_by_priority() == {1: 7.0, 3: 8.0}


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
    m.record_dispatch(_FakeJob("t1", 7, created_at=5), dispatch_time=11)
    m.observe_queue_depth(4)

    snap = m.snapshot()

    assert snap == {
        "enqueue_accepted_count": 1,
        "enqueue_rejected_full_count": 1,
        "enqueue_rejected_invalid_count": 0,
        "dispatch_count_total": 1,
        "dispatch_count_by_tenant": {"t1": 1},
        "dispatch_count_by_priority": {7: 1},
        "total_queue_wait_time": 6,
        "total_queue_wait_time_by_tenant": {"t1": 6},
        "total_queue_wait_time_by_priority": {7: 6},
        "average_queue_wait_time": 6.0,
        "average_queue_wait_time_by_tenant": {"t1": 6.0},
        "average_queue_wait_time_by_priority": {7: 6.0},
        "queue_depth_peak": 4,
    }

    # Snapshot dicts are copies — mutating them does not change metrics.
    snap["dispatch_count_by_tenant"]["t1"] = 99
    assert m.dispatch_count_by_tenant["t1"] == 1


def test_snapshot_includes_new_average_wait_time_fields():
    m = SchedulerMetrics()
    m.record_dispatch(_FakeJob("tenant-a", 4, created_at=100), dispatch_time=110)
    snap = m.snapshot()

    assert "average_queue_wait_time" in snap
    assert "average_queue_wait_time_by_tenant" in snap
    assert "average_queue_wait_time_by_priority" in snap
    assert snap["average_queue_wait_time"] == 10.0
    assert snap["average_queue_wait_time_by_tenant"] == {"tenant-a": 10.0}
    assert snap["average_queue_wait_time_by_priority"] == {4: 10.0}

"""
Tests for the composed scheduler:
- bounded admission
- weighted round-robin fairness across tenants
- priority and created_at ordering within a tenant
"""

from control_plane.kernelq.enqueue_result import EnqueueStatus
from control_plane.kernelq.scheduler_composed import ComposedScheduler, Job

WEIGHTS = {"tenant-a": 2, "tenant-b": 1}


def _job(
    job_id: str,
    tenant_id: str,
    priority: int = 1,
    created_at: int = 0,
) -> Job:
    return Job(
        job_id=job_id,
        tenant_id=tenant_id,
        priority=priority,
        created_at=created_at,
    )


def test_enqueue_accepts_valid_jobs_until_capacity_reached():
    sched = ComposedScheduler(capacity=3, weights=WEIGHTS)

    assert sched.enqueue(_job("j1", "tenant-a")).status is EnqueueStatus.ACCEPTED
    assert sched.enqueue(_job("j2", "tenant-b")).status is EnqueueStatus.ACCEPTED
    assert sched.enqueue(_job("j3", "tenant-a")).status is EnqueueStatus.ACCEPTED

    assert sched.size() == 3
    assert sched.remaining_capacity() == 0


def test_enqueue_rejects_invalid_blank_job_id_or_tenant_id():
    sched = ComposedScheduler(capacity=5, weights=WEIGHTS)

    r1 = sched.enqueue(_job("", "tenant-a"))
    assert r1.status is EnqueueStatus.REJECTED_INVALID

    r2 = sched.enqueue(_job("   ", "tenant-a"))
    assert r2.status is EnqueueStatus.REJECTED_INVALID

    r3 = sched.enqueue(_job("ok-id", ""))
    assert r3.status is EnqueueStatus.REJECTED_INVALID

    r4 = sched.enqueue(_job("ok-id-2", "   "))
    assert r4.status is EnqueueStatus.REJECTED_INVALID

    # Invalid jobs should not consume capacity.
    assert sched.size() == 0
    assert sched.remaining_capacity() == 5


def test_enqueue_rejects_when_total_capacity_is_full():
    sched = ComposedScheduler(capacity=2, weights=WEIGHTS)
    assert sched.enqueue(_job("j1", "tenant-a")).status is EnqueueStatus.ACCEPTED
    assert sched.enqueue(_job("j2", "tenant-b")).status is EnqueueStatus.ACCEPTED

    overflow = sched.enqueue(_job("j3", "tenant-a"))
    assert overflow.status is EnqueueStatus.REJECTED_FULL
    assert sched.size() == 2


def test_weighted_round_robin_fairness_across_tenants():
    """
    With weights a=2 and b=1, over one full lap we should see:
    - 2 dequeues from tenant-a
    - 1 dequeue from tenant-b
    """
    sched = ComposedScheduler(capacity=20, weights=WEIGHTS)

    # Keep both tenants stocked so fairness can be observed clearly.
    for i in range(10):
        sched.enqueue(_job(f"a{i}", "tenant-a", priority=1, created_at=i))
        sched.enqueue(_job(f"b{i}", "tenant-b", priority=1, created_at=i))

    out = [sched.dequeue().tenant_id for _ in range(3)]

    assert out.count("tenant-a") == 2
    assert out.count("tenant-b") == 1
    assert "tenant-b" in out  # lower weight tenant still gets scheduled


def test_priority_within_tenant_highest_priority_wins_on_that_tenant_turn():
    """
    tenant-a has priorities 1, 10, and 5.
    On tenant-a's turn, priority 10 should be selected first.
    """
    sched = ComposedScheduler(capacity=10, weights=WEIGHTS)

    sched.enqueue(_job("a-low", "tenant-a", priority=1, created_at=1))
    sched.enqueue(_job("a-high", "tenant-a", priority=10, created_at=2))
    sched.enqueue(_job("a-mid", "tenant-a", priority=5, created_at=3))

    # Add one tenant-b job so both tenants exist in the scheduling flow.
    sched.enqueue(_job("b-one", "tenant-b", priority=1, created_at=1))

    first = sched.dequeue()
    assert first is not None
    assert first.tenant_id == "tenant-a"
    assert first.job_id == "a-high"


def test_tie_break_by_created_at_when_priority_equal_within_tenant():
    sched = ComposedScheduler(capacity=10, weights=WEIGHTS)

    sched.enqueue(_job("newer", "tenant-a", priority=5, created_at=200))
    sched.enqueue(_job("older", "tenant-a", priority=5, created_at=100))

    first = sched.dequeue()
    second = sched.dequeue()

    assert first is not None and first.job_id == "older"
    assert second is not None and second.job_id == "newer"


def test_peek_returns_next_job_without_removing():
    sched = ComposedScheduler(capacity=10, weights=WEIGHTS)
    sched.enqueue(_job("a1", "tenant-a", priority=2, created_at=10))
    sched.enqueue(_job("a2", "tenant-a", priority=1, created_at=1))

    nxt = sched.peek()
    assert nxt is not None and nxt.job_id == "a1"
    assert sched.size() == 2

    # Dequeue should return the same job after peek.
    out = sched.dequeue()
    assert out is not None and out.job_id == "a1"
    assert sched.size() == 1


def test_dequeue_returns_none_when_empty():
    sched = ComposedScheduler(capacity=5, weights=WEIGHTS)
    assert sched.dequeue() is None
    assert sched.peek() is None


def test_size_and_remaining_capacity_change_correctly():
    sched = ComposedScheduler(capacity=4, weights=WEIGHTS)
    assert sched.size() == 0
    assert sched.remaining_capacity() == 4

    sched.enqueue(_job("j1", "tenant-a"))
    sched.enqueue(_job("j2", "tenant-b"))
    assert sched.size() == 2
    assert sched.remaining_capacity() == 2

    sched.dequeue()
    assert sched.size() == 1
    assert sched.remaining_capacity() == 3

    sizes = sched.tenant_queue_sizes()
    assert sizes["tenant-a"] + sizes["tenant-b"] == sched.size()

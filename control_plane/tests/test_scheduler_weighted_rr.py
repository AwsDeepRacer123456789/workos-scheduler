"""
Tests for weighted round-robin scheduling across tenants.

Weights: tenant-a = 2, tenant-b = 1 (one lap of the cycle is roughly a, a, b).
"""

from control_plane.kernelq.scheduler_weighted_rr import Job, WeightedRoundRobinScheduler

WEIGHTS = {"tenant-a": 2, "tenant-b": 1}


def _job(jid: str, tenant: str, created_at: int = 0) -> Job:
    return Job(job_id=jid, tenant_id=tenant, created_at=created_at)


def test_fifo_order_within_same_tenant():
    """Jobs for one tenant should come out in the same order they were enqueued."""
    sched = WeightedRoundRobinScheduler(WEIGHTS)
    sched.enqueue(_job("first", "tenant-a", 1))
    sched.enqueue(_job("second", "tenant-a", 2))
    sched.enqueue(_job("third", "tenant-a", 3))

    assert sched.dequeue().job_id == "first"
    assert sched.dequeue().job_id == "second"
    assert sched.dequeue().job_id == "third"
    assert sched.dequeue() is None


def test_higher_weight_gets_more_turns_when_both_have_jobs():
    """
    With both tenants having work waiting, tenant-a (weight 2) should be chosen
    more often than tenant-b (weight 1) over a full lap (pattern: a, a, b).
    """
    sched = WeightedRoundRobinScheduler(WEIGHTS)
    # Enough jobs on each side so neither runs dry during the first 6 dequeues.
    for i in range(10):
        sched.enqueue(_job(f"a{i}", "tenant-a", i))
        sched.enqueue(_job(f"b{i}", "tenant-b", i))

    # First 3 dequeues = one full lap: two from tenant-a, one from tenant-b.
    out = [sched.dequeue().tenant_id for _ in range(3)]
    assert out.count("tenant-a") == 2
    assert out.count("tenant-b") == 1

    # First 6 dequeues = two laps: expect 4 tenant-a and 2 tenant-b.
    # We already popped 3; pop 3 more.
    out2 = [sched.dequeue().tenant_id for _ in range(3)]
    combined = out + out2
    assert combined.count("tenant-a") == 4
    assert combined.count("tenant-b") == 2


def test_lower_weight_tenant_still_gets_scheduled():
    """
    tenant-b has lower weight but should still receive work when it has jobs
    (simple setup: both tenants always have backlog for several laps).
    """
    sched = WeightedRoundRobinScheduler(WEIGHTS)
    for i in range(20):
        sched.enqueue(_job(f"a{i}", "tenant-a", i))
        sched.enqueue(_job(f"b{i}", "tenant-b", i))

    seen_b = False
    for _ in range(30):
        j = sched.dequeue()
        assert j is not None
        if j.tenant_id == "tenant-b":
            seen_b = True
            break
    assert seen_b, "tenant-b should get at least one turn while both have jobs"


def test_empty_tenant_is_skipped():
    """If a tenant has no jobs, the scheduler should serve the other tenant."""
    sched = WeightedRoundRobinScheduler(WEIGHTS)
    sched.enqueue(_job("only-b", "tenant-b", 1))

    assert sched.dequeue().job_id == "only-b"
    assert sched.dequeue() is None

    sched2 = WeightedRoundRobinScheduler(WEIGHTS)
    sched2.enqueue(_job("only-a", "tenant-a", 1))
    assert sched2.dequeue().job_id == "only-a"
    assert sched2.dequeue() is None


def test_dequeue_empty_returns_none():
    sched = WeightedRoundRobinScheduler(WEIGHTS)
    assert sched.dequeue() is None
    assert sched.peek() is None
    assert sched.size() == 0


def test_peek_does_not_remove():
    sched = WeightedRoundRobinScheduler(WEIGHTS)
    sched.enqueue(_job("a1", "tenant-a", 1))
    sched.enqueue(_job("b1", "tenant-b", 2))

    nxt = sched.peek()
    assert nxt is not None and nxt.job_id == "a1"
    assert sched.size() == 2
    assert sched.dequeue().job_id == "a1"
    assert sched.dequeue().job_id == "b1"


def test_size_tracks_total_jobs():
    sched = WeightedRoundRobinScheduler(WEIGHTS)
    assert sched.size() == 0

    sched.enqueue(_job("a1", "tenant-a", 1))
    sched.enqueue(_job("a2", "tenant-a", 2))
    sched.enqueue(_job("b1", "tenant-b", 3))
    assert sched.size() == 3

    sched.dequeue()
    assert sched.size() == 2
    sched.dequeue()
    sched.dequeue()
    assert sched.size() == 0


def test_tenant_queue_sizes_per_tenant():
    sched = WeightedRoundRobinScheduler(WEIGHTS)
    sched.enqueue(_job("a1", "tenant-a", 1))
    sched.enqueue(_job("b1", "tenant-b", 2))
    sched.enqueue(_job("b2", "tenant-b", 3))

    sizes = sched.tenant_queue_sizes()
    assert sizes["tenant-a"] == 1
    assert sizes["tenant-b"] == 2

"""
Tests for the in-memory priority scheduler.

Higher `priority` runs first. If priority ties, smaller `created_at` wins.
"""

from control_plane.kernelq.scheduler_priority import Job, PriorityScheduler


def test_higher_priority_dequeued_first():
    """Jobs with larger priority values should run before lower-priority jobs."""
    sched = PriorityScheduler()
    low = Job(job_id="low", priority=1, created_at=100)
    high = Job(job_id="high", priority=10, created_at=100)
    # Enqueue low first, then high — high should still win.
    sched.enqueue(low)
    sched.enqueue(high)

    assert sched.dequeue() == high
    assert sched.dequeue() == low
    assert sched.dequeue() is None


def test_same_priority_earlier_created_at_wins():
    """If priority is equal, the job with the smaller created_at should go first."""
    sched = PriorityScheduler()
    later = Job(job_id="later", priority=5, created_at=200)
    earlier = Job(job_id="earlier", priority=5, created_at=100)
    sched.enqueue(later)
    sched.enqueue(earlier)

    assert sched.dequeue() == earlier
    assert sched.dequeue() == later
    assert sched.dequeue() is None


def test_dequeue_empty_returns_none():
    """Nothing in the scheduler → dequeue and peek return None, size is 0."""
    sched = PriorityScheduler()
    assert sched.dequeue() is None
    assert sched.peek() is None
    assert sched.size() == 0


def test_peek_returns_next_without_removing():
    """peek() shows what dequeue() would return, but leaves the job in place."""
    sched = PriorityScheduler()
    first = Job(job_id="first", priority=10, created_at=1)
    second = Job(job_id="second", priority=1, created_at=1)
    sched.enqueue(first)
    sched.enqueue(second)

    assert sched.peek() == first
    assert sched.size() == 2
    assert sched.dequeue() == first
    assert sched.dequeue() == second
    assert sched.dequeue() is None


def test_size_after_enqueue_and_dequeue():
    """size() should match how many jobs are still waiting."""
    sched = PriorityScheduler()
    a = Job(job_id="a", priority=1, created_at=1)
    b = Job(job_id="b", priority=2, created_at=2)
    c = Job(job_id="c", priority=3, created_at=3)

    assert sched.size() == 0
    sched.enqueue(a)
    sched.enqueue(b)
    sched.enqueue(c)
    assert sched.size() == 3

    sched.dequeue()  # removes highest priority: c
    assert sched.size() == 2
    sched.dequeue()  # removes b
    assert sched.size() == 1
    sched.dequeue()  # removes a
    assert sched.size() == 0

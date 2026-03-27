"""
Tests for the bounded FIFO job queue.
"""

import pytest

from control_plane.kernelq.bounded_queue import BoundedQueue, Job


def test_enqueue_succeeds_until_capacity_then_rejects():
    """Jobs are accepted until the queue hits its limit; then enqueue returns False."""
    q = BoundedQueue(capacity=3)
    assert q.enqueue(Job("j1", 1)) is True
    assert q.enqueue(Job("j2", 2)) is True
    assert q.enqueue(Job("j3", 3)) is True
    assert q.is_full() is True
    assert q.enqueue(Job("overflow", 4)) is False


def test_dequeue_fifo_order():
    """Oldest enqueued job should always come out first."""
    q = BoundedQueue(capacity=5)
    a = Job("a", 10)
    b = Job("b", 20)
    c = Job("c", 30)
    q.enqueue(a)
    q.enqueue(b)
    q.enqueue(c)

    assert q.dequeue() == a
    assert q.dequeue() == b
    assert q.dequeue() == c
    assert q.dequeue() is None


def test_dequeue_empty_returns_none():
    q = BoundedQueue(capacity=2)
    assert q.dequeue() is None


def test_peek_does_not_remove():
    q = BoundedQueue(capacity=2)
    first = Job("first", 1)
    q.enqueue(first)
    q.enqueue(Job("second", 2))

    assert q.peek() == first
    assert q.size() == 2
    assert q.dequeue() == first


def test_size_tracks_enqueues_and_dequeues():
    q = BoundedQueue(capacity=3)
    assert q.size() == 0

    q.enqueue(Job("1", 1))
    q.enqueue(Job("2", 2))
    assert q.size() == 2

    q.dequeue()
    assert q.size() == 1

    q.dequeue()
    assert q.size() == 0


def test_is_full_and_remaining_capacity():
    q = BoundedQueue(capacity=2)
    assert q.is_full() is False
    assert q.remaining_capacity() == 2

    q.enqueue(Job("x", 1))
    assert q.is_full() is False
    assert q.remaining_capacity() == 1

    q.enqueue(Job("y", 2))
    assert q.is_full() is True
    assert q.remaining_capacity() == 0

    q.dequeue()
    assert q.is_full() is False
    assert q.remaining_capacity() == 1


def test_stats_matches_queue_state():
    q = BoundedQueue(capacity=3)
    q.enqueue(Job("a", 1))
    q.enqueue(Job("b", 2))

    assert q.stats() == {
        "capacity": 3,
        "size": 2,
        "remaining_capacity": 1,
        "is_full": False,
    }

    q.enqueue(Job("c", 3))
    assert q.stats() == {
        "capacity": 3,
        "size": 3,
        "remaining_capacity": 0,
        "is_full": True,
    }


@pytest.mark.parametrize("bad_capacity", [0, -1, -100])
def test_invalid_capacity_raises(bad_capacity: int):
    with pytest.raises(ValueError):
        BoundedQueue(capacity=bad_capacity)

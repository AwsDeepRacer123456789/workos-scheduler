"""Tests for EnqueueResult and EnqueueStatus."""

from control_plane.kernelq.enqueue_result import EnqueueResult, EnqueueStatus


def test_accepted_factory():
    r = EnqueueResult.accepted()
    assert r.status is EnqueueStatus.ACCEPTED
    assert r.is_accepted() is True
    assert r.message == "accepted"


def test_rejected_full_factory():
    r = EnqueueResult.rejected_full()
    assert r.status is EnqueueStatus.REJECTED_FULL
    assert r.is_accepted() is False
    assert r.message == "queue is full"


def test_rejected_invalid_factory():
    r = EnqueueResult.rejected_invalid()
    assert r.status is EnqueueStatus.REJECTED_INVALID
    assert r.is_accepted() is False
    assert r.message == "invalid job"

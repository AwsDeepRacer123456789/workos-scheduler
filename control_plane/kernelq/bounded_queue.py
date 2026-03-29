"""
Bounded FIFO queue for jobs (in-memory).

A bounded queue has a fixed maximum size. When it is full, new jobs are
*rejected* with ``REJECTED_FULL`` instead of growing forever. Invalid jobs
(e.g. blank ``job_id``) get ``REJECTED_INVALID``. That pattern supports
admission control: the system refuses work it cannot safely hold.

This module uses only the Python standard library.
"""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass

from .enqueue_result import EnqueueResult


@dataclass(frozen=True)
class Job:
    """Minimal job record stored in the queue."""

    job_id: str
    created_at: int


class BoundedQueue:
    """
    First-in, first-out queue with a hard capacity limit.

    - Oldest job is at the front; enqueue adds to the back.
    - When ``len == capacity``, enqueue fails until someone dequeues.
    """

    def __init__(self, capacity: int) -> None:
        if capacity <= 0:
            raise ValueError(f"capacity must be positive, got {capacity}")
        self._capacity: int = capacity
        self._items: deque[Job] = deque()

    def enqueue(self, job: Job) -> EnqueueResult:
        """
        Try to add a job to the back of the queue.

        Returns an :class:`EnqueueResult`: ``ACCEPTED``, ``REJECTED_FULL``,
        or ``REJECTED_INVALID`` (e.g. blank ``job_id`` after stripping).
        """
        if not job.job_id.strip():
            return EnqueueResult.rejected_invalid()
        if len(self._items) >= self._capacity:
            return EnqueueResult.rejected_full()
        self._items.append(job)
        return EnqueueResult.accepted()

    def dequeue(self) -> Job | None:
        """
        Remove and return the oldest job, or None if the queue is empty.
        """
        if not self._items:
            return None
        return self._items.popleft()

    def peek(self) -> Job | None:
        """
        Return the oldest job without removing it, or None if empty.
        """
        if not self._items:
            return None
        return self._items[0]

    def size(self) -> int:
        """Number of jobs currently in the queue."""
        return len(self._items)

    def is_full(self) -> bool:
        """True when no more jobs can be enqueued without a dequeue."""
        return len(self._items) >= self._capacity

    def remaining_capacity(self) -> int:
        """How many more jobs can be enqueued before the queue is full."""
        return self._capacity - len(self._items)

    def stats(self) -> dict:
        """
        Small snapshot for logging, metrics, or debugging.

        Keys: capacity, size, remaining_capacity, is_full.
        """
        return {
            "capacity": self._capacity,
            "size": self.size(),
            "remaining_capacity": self.remaining_capacity(),
            "is_full": self.is_full(),
        }

"""
FIFO (First-In, First-Out) scheduler.

This file intentionally stays *small* and *beginner-friendly*:
- No database, no broker, no APIs
- Pure in-memory scheduling logic

FIFO is the simplest scheduling policy:
the earliest enqueued job is always returned first.
"""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass


@dataclass(frozen=True)
class Job:
    """
    A minimal job model for the scheduler to work with.

    - `job_id`: a unique identifier for the job (string)
    - `created_at`: an integer timestamp (e.g., unix seconds)

    The scheduler does not interpret `created_at` today; we store it because real
    systems need timestamps, and it makes tests/examples more realistic.
    """

    job_id: str
    created_at: int


class FIFOScheduler:
    """
    An in-memory FIFO queue of Jobs.

    The invariant is simple:
    - Jobs are returned in the exact order they were enqueued.

    This is *not* thread-safe. That's fine for a minimal baseline and unit tests.
    """

    def __init__(self) -> None:
        # `deque` is a standard-library data structure optimized for "push/pop
        # from either end" operations. For FIFO, we append on the right and
        # pop from the left.
        self._queue: deque[Job] = deque()

    def enqueue(self, job: Job) -> None:
        """
        Add a job to the back of the queue.

        If you enqueue A, then B, then C, the scheduler will later dequeue
        A first, then B, then C.
        """

        self._queue.append(job)

    def dequeue(self) -> Job | None:
        """
        Remove and return the earliest enqueued job.

        Returns None if the queue is empty.
        """

        if not self._queue:
            return None
        return self._queue.popleft()

    def size(self) -> int:
        """
        Return the current number of queued jobs.
        """

        return len(self._queue)

    def peek(self) -> Job | None:
        """
        Return (but do not remove) the earliest enqueued job.

        Returns None if the queue is empty.
        """

        if not self._queue:
            return None
        return self._queue[0]


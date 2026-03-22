"""
Priority scheduler (in-memory).

This module is intentionally small and educational:
- No database, no Kafka, no APIs — only ordering logic.
- Uses the Python standard library only.

Ordering rules:
1) Higher `priority` runs first (larger integer = more important).
2) If priorities tie, smaller `created_at` wins (earlier timestamp first).
3) If those tie, `job_id` breaks ties so ordering is deterministic.
"""

from __future__ import annotations

import heapq
from dataclasses import dataclass


@dataclass(frozen=True)
class Job:
    """
    Minimal job record for the scheduler.

    - job_id: stable string id (used only for tie-breaking).
    - priority: larger number = more urgent (scheduled first).
    - created_at: integer time (e.g. unix seconds); smaller = earlier.
    """

    job_id: str
    priority: int
    created_at: int


class PriorityScheduler:
    """
    In-memory priority queue of Job objects.

    Implementation note:
    Python's `heapq` is a *min-heap* (smallest item pops first). We store tuples
    so that "higher priority first" becomes "smallest tuple first":

        (-priority, created_at, job_id, job)

    - Negating `priority` turns "max priority wins" into "min -priority wins".
    - For equal priority, smaller `created_at` is smaller → earlier job wins.
    - `job_id` makes the tuple unique and ordering stable if times collide.
    """

    def __init__(self) -> None:
        # List-backed heap; each entry is
        # (-priority, created_at, job_id, Job)
        self._heap: list[tuple[int, int, str, Job]] = []

    def enqueue(self, job: Job) -> None:
        """Insert a job into the scheduler's waiting set."""

        key = (-job.priority, job.created_at, job.job_id, job)
        heapq.heappush(self._heap, key)

    def dequeue(self) -> Job | None:
        """
        Remove and return the highest-priority job.

        Returns None if there is nothing to run.
        """

        if not self._heap:
            return None
        _p, _t, _id, job = heapq.heappop(self._heap)
        return job

    def peek(self) -> Job | None:
        """
        Look at the next job that would be dequeued, without removing it.

        Returns None if empty.
        """

        if not self._heap:
            return None
        return self._heap[0][3]

    def size(self) -> int:
        """Number of jobs currently waiting."""

        return len(self._heap)

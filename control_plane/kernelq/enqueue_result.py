"""
Typed outcomes when submitting a job to KernelQ.

Instead of only True/False, callers get a *reason* (status + message) so they
can tell overload (retry later) from bad input (fix the request).
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class EnqueueStatus(Enum):
    """Why an enqueue attempt succeeded or failed."""

    ACCEPTED = "accepted"
    REJECTED_FULL = "rejected_full"
    REJECTED_INVALID = "rejected_invalid"


@dataclass(frozen=True)
class EnqueueResult:
    """
    Result of trying to admit a job (e.g. into a bounded queue or API layer).

    - ``status`` classifies the outcome for branching and metrics.
    - ``message`` is human-readable context (logging, API errors, tests).
    """

    status: EnqueueStatus
    message: str

    def is_accepted(self) -> bool:
        """True only when the job was admitted."""
        return self.status is EnqueueStatus.ACCEPTED

    @classmethod
    def accepted(cls, message: str = "accepted") -> EnqueueResult:
        """Job was accepted under current capacity and validation rules."""
        return cls(EnqueueStatus.ACCEPTED, message)

    @classmethod
    def rejected_full(cls, message: str = "queue is full") -> EnqueueResult:
        """System is temporarily saturated; client may retry with backoff."""
        return cls(EnqueueStatus.REJECTED_FULL, message)

    @classmethod
    def rejected_invalid(cls, message: str = "invalid job") -> EnqueueResult:
        """Request failed validation; fix the payload before retrying."""
        return cls(EnqueueStatus.REJECTED_INVALID, message)

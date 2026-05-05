"""
FastAPI control-plane API (in-memory prototype).

This module exposes a small set of endpoints for job lifecycle operations:
- Get a job's current state/details
- Enqueue a job
- Cancel a job
- Retry a failed job
- Read scheduler metrics

Notes:
- This is intentionally simple and beginner-friendly.
- Data is in-memory only (no Postgres/Kafka yet).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from fastapi import FastAPI, HTTPException, Path
from pydantic import BaseModel, Field

from control_plane.kernelq.job_state import JobState, can_transition, explain_transition
from control_plane.kernelq.scheduler_composed import ComposedScheduler
from control_plane.kernelq.scheduler_composed import Job as SchedulerJob
from control_plane.kernelq.scheduler_metrics import SchedulerMetrics


# ---------------------------------------------------------------------------
# In-memory control-plane wiring
# ---------------------------------------------------------------------------

WEIGHTS = {"tenant-a": 2, "tenant-b": 1}
CAPACITY = 6

# Shared in-memory objects for this process.
scheduler = ComposedScheduler(capacity=CAPACITY, weights=WEIGHTS)
metrics = SchedulerMetrics()


@dataclass
class JobRecord:
    """Internal record for API-managed job metadata/state."""

    job_id: str
    tenant_id: str
    priority: int
    created_at: int
    state: JobState


# In-memory "database": job_id -> JobRecord
job_store: dict[str, JobRecord] = {}


# Simple deterministic created_at clock for this prototype.
_created_at_counter = 0


def _next_created_at() -> int:
    global _created_at_counter
    value = _created_at_counter
    _created_at_counter += 1
    return value


# ---------------------------------------------------------------------------
# Request/response models (Pydantic)
# ---------------------------------------------------------------------------


class EnqueueJobRequest(BaseModel):
    """
    Request body for enqueue.

    We include job_id in the payload even though it is also in the URL so we can
    validate consistency and keep the API contract explicit.
    """

    job_id: str = Field(..., min_length=1, description="Unique job identifier")
    tenant_id: str = Field(..., min_length=1, description="Tenant that owns the job")
    priority: int = Field(..., description="Larger value means more urgent")


class JobResponse(BaseModel):
    """Public job representation returned by API endpoints."""

    job_id: str
    tenant_id: str
    priority: int
    created_at: int
    state: str


class MessageResponse(BaseModel):
    """Simple message wrapper used by mutating endpoints."""

    message: str
    job_id: str
    state: str


# ---------------------------------------------------------------------------
# FastAPI application and endpoints
# ---------------------------------------------------------------------------

app = FastAPI(
    title="KernelQ Control Plane API",
    description="Beginner-friendly in-memory API for job state management.",
    version="0.1.0",
)


@app.get(
    "/jobs/{job_id}",
    response_model=JobResponse,
    summary="Get a job by ID",
    description="Return current job state and job details (tenant, priority, created_at).",
)
def get_job(job_id: str = Path(..., description="Job ID")) -> JobResponse:
    """Fetch job state/details by id, or return 404 if unknown."""
    record = job_store.get(job_id)
    if record is None:
        raise HTTPException(status_code=404, detail=f"Job {job_id!r} not found")

    return JobResponse(
        job_id=record.job_id,
        tenant_id=record.tenant_id,
        priority=record.priority,
        created_at=record.created_at,
        state=record.state.value,
    )


@app.post(
    "/jobs/{job_id}/enqueue",
    response_model=MessageResponse,
    summary="Enqueue a job",
    description=(
        "Validate request fields, enqueue into the in-memory control plane, "
        "and mark job state as queued when accepted."
    ),
)
def enqueue_job(
    payload: EnqueueJobRequest,
    job_id: str = Path(..., description="Job ID in URL"),
) -> MessageResponse:
    """Validate and enqueue a job; returns acceptance message on success."""
    if payload.job_id != job_id:
        raise HTTPException(
            status_code=400,
            detail="job_id in URL must match job_id in request body",
        )

    if payload.job_id in job_store:
        raise HTTPException(status_code=409, detail=f"Job {job_id!r} already exists")

    created_at = _next_created_at()
    sched_job = SchedulerJob(
        job_id=payload.job_id,
        tenant_id=payload.tenant_id,
        priority=payload.priority,
        created_at=created_at,
    )
    result = scheduler.enqueue(sched_job)
    metrics.record_enqueue_result(result.status)
    metrics.observe_queue_depth(scheduler.size())

    if not result.is_accepted():
        # Invalid request from scheduler validation => 400.
        if "invalid" in result.status.value:
            raise HTTPException(status_code=400, detail=result.message)
        # Full queue => backpressure signal.
        raise HTTPException(status_code=429, detail=result.message)

    record = JobRecord(
        job_id=payload.job_id,
        tenant_id=payload.tenant_id,
        priority=payload.priority,
        created_at=created_at,
        state=JobState.QUEUED,
    )
    job_store[payload.job_id] = record

    return MessageResponse(message="Job accepted", job_id=record.job_id, state=record.state.value)


@app.post(
    "/jobs/{job_id}/cancel",
    response_model=MessageResponse,
    summary="Cancel a job",
    description="Move a job to CANCELED if the transition is valid.",
)
def cancel_job(job_id: str = Path(..., description="Job ID")) -> MessageResponse:
    """Cancel an existing job using state-transition rules."""
    record = job_store.get(job_id)
    if record is None:
        raise HTTPException(status_code=404, detail=f"Job {job_id!r} not found")

    if not can_transition(record.state, JobState.CANCELED):
        raise HTTPException(
            status_code=409,
            detail=explain_transition(record.state, JobState.CANCELED),
        )

    record.state = JobState.CANCELED
    return MessageResponse(message="Job canceled", job_id=record.job_id, state=record.state.value)


@app.post(
    "/jobs/{job_id}/retry",
    response_model=MessageResponse,
    summary="Retry a failed job",
    description="Retry only when job is currently FAILED; re-enqueue when allowed.",
)
def retry_job(job_id: str = Path(..., description="Job ID")) -> MessageResponse:
    """Retry a job if it is in FAILED state; otherwise return a conflict error."""
    record = job_store.get(job_id)
    if record is None:
        raise HTTPException(status_code=404, detail=f"Job {job_id!r} not found")

    if record.state is not JobState.FAILED:
        raise HTTPException(
            status_code=409,
            detail=f"Retry allowed only from FAILED state. Current state: {record.state.value}",
        )

    # FAILED -> RETRY_SCHEDULED -> QUEUED (as in our state machine model).
    if not can_transition(record.state, JobState.RETRY_SCHEDULED):
        raise HTTPException(
            status_code=409,
            detail=explain_transition(record.state, JobState.RETRY_SCHEDULED),
        )
    record.state = JobState.RETRY_SCHEDULED

    retry_job_obj = SchedulerJob(
        job_id=record.job_id,
        tenant_id=record.tenant_id,
        priority=record.priority,
        created_at=record.created_at,
    )
    result = scheduler.enqueue(retry_job_obj)
    metrics.record_enqueue_result(result.status)
    metrics.observe_queue_depth(scheduler.size())

    if not result.is_accepted():
        if "invalid" in result.status.value:
            raise HTTPException(status_code=400, detail=result.message)
        raise HTTPException(status_code=429, detail=result.message)

    if not can_transition(record.state, JobState.QUEUED):
        raise HTTPException(
            status_code=409,
            detail=explain_transition(record.state, JobState.QUEUED),
        )
    record.state = JobState.QUEUED
    return MessageResponse(message="Job retried", job_id=record.job_id, state=record.state.value)


@app.get(
    "/metrics",
    summary="Get current scheduler metrics",
    description=(
        "Return current in-memory scheduler metrics including enqueue outcomes, "
        "dispatch counters, queue wait-time summaries, and queue depth peak."
    ),
)
def get_metrics() -> dict[str, Any]:
    """Expose metrics snapshot for this control-plane process."""
    return metrics.snapshot()

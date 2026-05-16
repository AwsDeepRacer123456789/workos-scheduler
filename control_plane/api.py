"""
FastAPI control-plane API for KernelQ.

Job rows are stored in PostgreSQL through JobRepository. Scheduling queues and
Kafka dispatch are not wired here yet—this module focuses on HTTP + durable state.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from fastapi import FastAPI, HTTPException, Path
from psycopg import Error as PsycopgError
from psycopg.errors import UniqueViolation
from pydantic import BaseModel, Field

from control_plane.kernelq.db import connect
from control_plane.kernelq.enqueue_result import EnqueueStatus
from control_plane.kernelq.job_repository import JobRepository
from control_plane.kernelq.job_state import TERMINAL_STATES, JobState, can_transition, explain_transition
from control_plane.kernelq.scheduler_metrics import SchedulerMetrics


# In-process metrics only (not persisted to Postgres).
metrics = SchedulerMetrics()


def get_repository() -> JobRepository:
    """
    Open a new database connection and wrap it in a JobRepository.

    Callers should close the connection when finished (see ``_close_repository``).
    Connection pooling can be added later.
    """
    conn = connect()
    return JobRepository(conn)


def _close_repository(repo: JobRepository) -> None:
    """Close the underlying psycopg connection for a repository."""
    repo._conn.close()


def _parse_state(state_value: str) -> JobState:
    """Convert a stored state string to JobState, or raise if unknown."""
    try:
        return JobState(state_value)
    except ValueError as exc:
        raise HTTPException(
            status_code=500,
            detail=f"Job has unknown state {state_value!r} in database",
        ) from exc


def _record_to_response(record: Any) -> "JobResponse":
    """Map a repository JobRecord to the public API response model."""
    created_at = record.created_at
    updated_at = record.updated_at
    if isinstance(created_at, datetime):
        created_at = int(created_at.timestamp())
    if isinstance(updated_at, datetime):
        updated_at = int(updated_at.timestamp())

    return JobResponse(
        job_id=record.job_id,
        tenant_id=record.tenant_id,
        priority=record.priority,
        state=record.state,
        payload=record.payload,
        retry_count=record.retry_count,
        max_retries=record.max_retries,
        created_at=created_at,
        updated_at=updated_at,
    )


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
    state: str
    payload: dict[str, Any]
    retry_count: int
    max_retries: int
    created_at: int
    updated_at: int


class MessageResponse(BaseModel):
    """Simple message wrapper used by mutating endpoints."""

    message: str
    job_id: str
    state: str


# ---------------------------------------------------------------------------
# FastAPI application and endpoints
# ---------------------------------------------------------------------------

API_VERSION = "0.1.0"

app = FastAPI(
    title="KernelQ Control Plane API",
    version=API_VERSION,
    description=(
        "Python control-plane API for KernelQ. Jobs are persisted in PostgreSQL. "
        "Scheduling queues and Kafka worker dispatch will be integrated in later steps."
    ),
)


@app.get(
    "/health",
    summary="Shallow health check",
    description=(
        "Returns OK if this process is running. This does not check databases, "
        "Kafka, Redis, or workers—that will be a separate readiness path later."
    ),
)
def health() -> dict[str, str]:
    """Shallow liveness check only."""
    return {
        "status": "ok",
        "service": "kernelq-control-plane",
        "version": API_VERSION,
    }


@app.get(
    "/jobs/{job_id}",
    response_model=JobResponse,
    summary="Get a job by ID",
    description="Return current job state and details from Postgres.",
)
def get_job(job_id: str = Path(..., description="Job ID")) -> JobResponse:
    """Fetch job state/details by id, or return 404 if unknown."""
    repo = get_repository()
    try:
        try:
            record = repo.get_job(job_id)
        except PsycopgError as exc:
            raise HTTPException(
                status_code=500,
                detail=f"Database error while loading job: {exc}",
            ) from exc

        if record is None:
            raise HTTPException(status_code=404, detail=f"Job {job_id!r} not found")

        return _record_to_response(record)
    finally:
        _close_repository(repo)


@app.post(
    "/jobs/{job_id}/enqueue",
    response_model=MessageResponse,
    summary="Enqueue a job",
    description="Validate the request and persist a new job in Postgres with state queued.",
)
def enqueue_job(
    payload: EnqueueJobRequest,
    job_id: str = Path(..., description="Job ID in URL"),
) -> MessageResponse:
    """Validate and persist a new job; returns acceptance message on success."""
    if payload.job_id != job_id:
        metrics.record_enqueue_result(EnqueueStatus.REJECTED_INVALID)
        raise HTTPException(
            status_code=400,
            detail="job_id in URL must match job_id in request body",
        )

    if not payload.tenant_id.strip():
        metrics.record_enqueue_result(EnqueueStatus.REJECTED_INVALID)
        raise HTTPException(status_code=400, detail="tenant_id must not be blank")

    if payload.priority < 0:
        metrics.record_enqueue_result(EnqueueStatus.REJECTED_INVALID)
        raise HTTPException(status_code=400, detail="priority must be >= 0")

    repo = get_repository()
    try:
        try:
            existing = repo.get_job(job_id)
        except PsycopgError as exc:
            raise HTTPException(
                status_code=500,
                detail=f"Database error while checking job: {exc}",
            ) from exc

        if existing is not None:
            raise HTTPException(status_code=409, detail=f"Job {job_id!r} already exists")

        try:
            record = repo.create_job(
                job_id=payload.job_id,
                tenant_id=payload.tenant_id,
                priority=payload.priority,
                state=JobState.QUEUED.value,
                payload={},
            )
        except UniqueViolation:
            raise HTTPException(status_code=409, detail=f"Job {job_id!r} already exists")
        except PsycopgError as exc:
            raise HTTPException(
                status_code=500,
                detail=f"Database error while creating job: {exc}",
            ) from exc

        metrics.record_enqueue_result(EnqueueStatus.ACCEPTED)
        return MessageResponse(
            message="Job accepted",
            job_id=record.job_id,
            state=record.state,
        )
    finally:
        _close_repository(repo)


@app.post(
    "/jobs/{job_id}/cancel",
    response_model=MessageResponse,
    summary="Cancel a job",
    description="Move a job to CANCELED if the transition is valid.",
)
def cancel_job(job_id: str = Path(..., description="Job ID")) -> MessageResponse:
    """Cancel an existing job using state-transition rules."""
    repo = get_repository()
    try:
        try:
            record = repo.get_job(job_id)
        except PsycopgError as exc:
            raise HTTPException(
                status_code=500,
                detail=f"Database error while loading job: {exc}",
            ) from exc

        if record is None:
            raise HTTPException(status_code=404, detail=f"Job {job_id!r} not found")

        current = _parse_state(record.state)
        if current in TERMINAL_STATES:
            raise HTTPException(
                status_code=409,
                detail=explain_transition(current, JobState.CANCELED),
            )

        if not can_transition(current, JobState.CANCELED):
            raise HTTPException(
                status_code=409,
                detail=explain_transition(current, JobState.CANCELED),
            )

        try:
            updated = repo.update_job_state(job_id, JobState.CANCELED.value)
        except PsycopgError as exc:
            raise HTTPException(
                status_code=500,
                detail=f"Database error while canceling job: {exc}",
            ) from exc

        if updated is None:
            raise HTTPException(status_code=404, detail=f"Job {job_id!r} not found")

        return MessageResponse(
            message="Job canceled",
            job_id=updated.job_id,
            state=updated.state,
        )
    finally:
        _close_repository(repo)


@app.post(
    "/jobs/{job_id}/retry",
    response_model=MessageResponse,
    summary="Retry a failed job",
    description="Move a FAILED job to RETRY_SCHEDULED when allowed by the state machine.",
)
def retry_job(job_id: str = Path(..., description="Job ID")) -> MessageResponse:
    """Retry a job if it is in FAILED state; otherwise return a conflict error."""
    repo = get_repository()
    try:
        try:
            record = repo.get_job(job_id)
        except PsycopgError as exc:
            raise HTTPException(
                status_code=500,
                detail=f"Database error while loading job: {exc}",
            ) from exc

        if record is None:
            raise HTTPException(status_code=404, detail=f"Job {job_id!r} not found")

        current = _parse_state(record.state)
        if current is not JobState.FAILED:
            raise HTTPException(
                status_code=409,
                detail=(
                    f"Retry allowed only from FAILED state. "
                    f"Current state: {current.value}"
                ),
            )

        if not can_transition(current, JobState.RETRY_SCHEDULED):
            raise HTTPException(
                status_code=409,
                detail=explain_transition(current, JobState.RETRY_SCHEDULED),
            )

        try:
            updated = repo.update_job_state(job_id, JobState.RETRY_SCHEDULED.value)
        except PsycopgError as exc:
            raise HTTPException(
                status_code=500,
                detail=f"Database error while scheduling retry: {exc}",
            ) from exc

        if updated is None:
            raise HTTPException(status_code=404, detail=f"Job {job_id!r} not found")

        return MessageResponse(
            message="Job retried",
            job_id=updated.job_id,
            state=updated.state,
        )
    finally:
        _close_repository(repo)


@app.get(
    "/metrics",
    summary="Get current scheduler metrics",
    description="Return current in-process scheduler metrics for this API process.",
)
def get_metrics() -> dict[str, Any]:
    """Expose metrics snapshot for this control-plane process."""
    return metrics.snapshot()

"""
Beginner-friendly API tests for the FastAPI control-plane app.

These tests call the real Postgres-backed API. Before running:

1. Start Postgres: ``docker compose up -d postgres``
2. Apply the migration once:

       psql "$DATABASE_URL" -f control_plane/migrations/001_create_jobs.sql

   (Or use the connection string from docker-compose; see control_plane/README.md.)

Each test uses a unique ``job_id`` and deletes that row in ``finally`` so runs stay isolated.
"""

from __future__ import annotations

import uuid

import pytest
from fastapi.testclient import TestClient
from psycopg import OperationalError

import control_plane.api as api_module
from control_plane.api import app
from control_plane.kernelq.db import connect
from control_plane.kernelq.job_repository import JobRepository
from control_plane.kernelq.scheduler_metrics import SchedulerMetrics


def _unique_job_id(prefix: str) -> str:
    """Return a unique job id so parallel or repeated runs do not collide."""
    return f"{prefix}_{uuid.uuid4().hex[:16]}"


def _delete_job(job_id: str) -> None:
    """Remove a test job row via JobRepository (safe if the job does not exist)."""
    with connect() as conn:
        JobRepository(conn).delete_job(job_id)


@pytest.fixture(scope="module", autouse=True)
def _require_postgres_and_migration() -> None:
    """
    Skip the whole module unless Postgres is up and the jobs table exists.

    That means the 001_create_jobs.sql migration has been applied.
    """
    try:
        with connect() as conn:
            conn.execute("SELECT 1")
            row = conn.execute(
                """
                SELECT 1
                FROM information_schema.tables
                WHERE table_schema = 'public' AND table_name = 'jobs'
                """
            ).fetchone()
    except OperationalError as exc:
        pytest.skip(f"Postgres not reachable (start docker compose): {exc}")

    if row is None:
        pytest.skip(
            "jobs table missing — apply control_plane/migrations/001_create_jobs.sql"
        )


@pytest.fixture(autouse=True)
def reset_metrics() -> None:
    """Reset in-process metrics so test order does not matter."""
    api_module.metrics = SchedulerMetrics()


@pytest.fixture
def client() -> TestClient:
    return TestClient(app)


def test_get_metrics_returns_200(client: TestClient) -> None:
    response = client.get("/metrics")

    assert response.status_code == 200
    assert "enqueue_accepted_count" in response.json()


def test_get_missing_job_returns_404(client: TestClient) -> None:
    job_id = _unique_job_id("missing")
    response = client.get(f"/jobs/{job_id}")

    assert response.status_code == 404


def test_enqueue_valid_job_returns_200(client: TestClient) -> None:
    job_id = _unique_job_id("enqueue_ok")
    _delete_job(job_id)

    try:
        response = client.post(
            f"/jobs/{job_id}/enqueue",
            json={"job_id": job_id, "priority": 5, "tenant_id": "tenant-a"},
        )

        assert response.status_code == 200
        assert response.json()["message"] == "Job accepted"
    finally:
        _delete_job(job_id)


def test_enqueue_duplicate_job_returns_409(client: TestClient) -> None:
    job_id = _unique_job_id("enqueue_dup")
    body = {"job_id": job_id, "priority": 1, "tenant_id": "tenant-a"}
    _delete_job(job_id)

    try:
        first = client.post(f"/jobs/{job_id}/enqueue", json=body)
        assert first.status_code == 200

        second = client.post(f"/jobs/{job_id}/enqueue", json=body)
        assert second.status_code == 409
    finally:
        _delete_job(job_id)


def test_get_job_after_enqueue_returns_persisted_job_data(client: TestClient) -> None:
    job_id = _unique_job_id("get_after_enqueue")
    _delete_job(job_id)

    try:
        client.post(
            f"/jobs/{job_id}/enqueue",
            json={"job_id": job_id, "priority": 5, "tenant_id": "tenant-a"},
        )

        response = client.get(f"/jobs/{job_id}")

        assert response.status_code == 200
        data = response.json()
        assert data["job_id"] == job_id
        assert data["tenant_id"] == "tenant-a"
        assert data["priority"] == 5
        assert data["state"] == "queued"
        assert data["payload"] == {}
        assert data["retry_count"] == 0
        assert data["max_retries"] == 3
        assert data["created_at"] is not None
        assert data["updated_at"] is not None
    finally:
        _delete_job(job_id)


def test_cancel_existing_job_returns_200_and_canceled_state(client: TestClient) -> None:
    job_id = _unique_job_id("cancel_ok")
    _delete_job(job_id)

    try:
        client.post(
            f"/jobs/{job_id}/enqueue",
            json={"job_id": job_id, "priority": 5, "tenant_id": "tenant-a"},
        )

        response = client.post(f"/jobs/{job_id}/cancel")

        assert response.status_code == 200
        assert response.json()["state"] == "canceled"
    finally:
        _delete_job(job_id)


def test_retry_after_cancel_returns_409(client: TestClient) -> None:
    job_id = _unique_job_id("retry_after_cancel")
    _delete_job(job_id)

    try:
        client.post(
            f"/jobs/{job_id}/enqueue",
            json={"job_id": job_id, "priority": 5, "tenant_id": "tenant-a"},
        )
        client.post(f"/jobs/{job_id}/cancel")

        response = client.post(f"/jobs/{job_id}/retry")

        assert response.status_code == 409
    finally:
        _delete_job(job_id)


def test_enqueue_missing_required_fields_returns_422(client: TestClient) -> None:
    response = client.post(
        "/jobs/bad/enqueue",
        json={"priority": 5, "tenant_id": "tenant-a"},
    )

    assert response.status_code == 422


def test_enqueue_invalid_blank_tenant_id_returns_non_200(client: TestClient) -> None:
    job_id = _unique_job_id("blank_tenant")
    _delete_job(job_id)

    response = client.post(
        f"/jobs/{job_id}/enqueue",
        json={"job_id": job_id, "priority": 5, "tenant_id": "   "},
    )

    assert response.status_code != 200
    _delete_job(job_id)

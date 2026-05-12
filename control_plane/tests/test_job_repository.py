"""
Integration tests for JobRepository against local Postgres.

Requires:
- ``docker compose up -d postgres`` (container ``kernelq-postgres``)
- Migration ``control_plane/migrations/001_create_jobs.sql`` applied once

Each test uses a unique ``job_id`` and deletes it in ``finally`` so runs stay isolated.
"""

from __future__ import annotations

import uuid

import pytest
from psycopg import OperationalError

from control_plane.kernelq.db import connect
from control_plane.kernelq.job_repository import JobRepository


def _unique_job_id(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex[:16]}"


@pytest.fixture(scope="module", autouse=True)
def _require_postgres() -> None:
    try:
        with connect() as conn:
            conn.execute("SELECT 1")
    except OperationalError as exc:
        pytest.skip(f"Postgres not reachable (start docker compose): {exc}")


def test_create_job_inserts_and_returns_record() -> None:
    job_id = _unique_job_id("test_jr_create")
    with connect() as conn:
        repo = JobRepository(conn)
        try:
            rec = repo.create_job(
                job_id,
                tenant_id="tenant-a",
                priority=7,
                state="queued",
                payload={"kind": "demo"},
                max_retries=5,
            )

            assert rec.job_id == job_id
            assert rec.tenant_id == "tenant-a"
            assert rec.priority == 7
            assert rec.state == "queued"
            assert rec.payload == {"kind": "demo"}
            assert rec.retry_count == 0
            assert rec.max_retries == 5
            assert rec.created_at is not None
            assert rec.updated_at is not None
        finally:
            repo.delete_job(job_id)


def test_get_job_returns_existing_job() -> None:
    job_id = _unique_job_id("test_jr_get")
    with connect() as conn:
        repo = JobRepository(conn)
        try:
            repo.create_job(job_id, "tenant-b", 3, "queued", payload={})

            loaded = repo.get_job(job_id)
            assert loaded is not None
            assert loaded.job_id == job_id
            assert loaded.tenant_id == "tenant-b"
            assert loaded.priority == 3
            assert loaded.state == "queued"
            assert loaded.payload == {}
        finally:
            repo.delete_job(job_id)


def test_get_job_returns_none_for_missing_job() -> None:
    missing_id = _unique_job_id("test_jr_missing")
    with connect() as conn:
        repo = JobRepository(conn)
        assert repo.get_job(missing_id) is None


def test_update_job_state_changes_state() -> None:
    job_id = _unique_job_id("test_jr_update")
    with connect() as conn:
        repo = JobRepository(conn)
        try:
            repo.create_job(job_id, "tenant-a", 1, "queued")

            updated = repo.update_job_state(job_id, "canceled")
            assert updated is not None
            assert updated.state == "canceled"
            assert updated.job_id == job_id

            again = repo.get_job(job_id)
            assert again is not None
            assert again.state == "canceled"
        finally:
            repo.delete_job(job_id)


def test_delete_job_removes_job() -> None:
    job_id = _unique_job_id("test_jr_delete")
    with connect() as conn:
        repo = JobRepository(conn)
        try:
            repo.create_job(job_id, "tenant-a", 2, "queued")

            assert repo.delete_job(job_id) is True
            assert repo.get_job(job_id) is None
            assert repo.delete_job(job_id) is False
        finally:
            repo.delete_job(job_id)

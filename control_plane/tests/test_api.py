"""
Beginner-friendly API tests for the FastAPI control-plane app.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

import control_plane.api as api_module
from control_plane.api import app
from control_plane.kernelq.scheduler_composed import ComposedScheduler
from control_plane.kernelq.scheduler_metrics import SchedulerMetrics


@pytest.fixture(autouse=True)
def reset_in_memory_api_state() -> None:
    """
    Keep tests isolated by resetting global in-memory API state.

    The API module stores scheduler/metrics/job_store as module-level globals.
    We reset those objects before each test so test order does not matter.
    """
    api_module.job_store.clear()
    api_module.scheduler = ComposedScheduler(
        capacity=api_module.CAPACITY,
        weights=api_module.WEIGHTS,
    )
    api_module.metrics = SchedulerMetrics()
    api_module._created_at_counter = 0


def test_get_metrics_returns_200():
    client = TestClient(app)
    response = client.get("/metrics")

    assert response.status_code == 200
    body = response.json()
    assert "enqueue_accepted_count" in body


def test_get_health_returns_200_and_expected_payload():
    """Shallow health: process is up; checks fixed fields."""
    client = TestClient(app)
    response = client.get("/health")

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert body["service"] == "kernelq-control-plane"
    assert body["version"] == "0.1.0"


def test_openapi_json_returns_200_with_api_metadata():
    """FastAPI exposes OpenAPI at /openapi.json for docs and tooling."""
    client = TestClient(app)
    response = client.get("/openapi.json")

    assert response.status_code == 200
    spec = response.json()
    assert spec["info"]["title"] == "KernelQ Control Plane API"
    assert spec["info"]["version"] == "0.1.0"


def test_get_missing_job_returns_404():
    client = TestClient(app)
    response = client.get("/jobs/missing-id")

    assert response.status_code == 404


def test_enqueue_valid_job_returns_200():
    client = TestClient(app)
    payload = {"job_id": "123", "priority": 5, "tenant_id": "tenant-a"}

    response = client.post("/jobs/123/enqueue", json=payload)

    assert response.status_code == 200
    assert response.json()["message"] == "Job accepted"


def test_get_job_after_enqueue_returns_200_and_job_id():
    client = TestClient(app)
    client.post(
        "/jobs/123/enqueue",
        json={"job_id": "123", "priority": 5, "tenant_id": "tenant-a"},
    )

    response = client.get("/jobs/123")

    assert response.status_code == 200
    assert response.json()["job_id"] == "123"


def test_cancel_existing_job_returns_200():
    client = TestClient(app)
    client.post(
        "/jobs/123/enqueue",
        json={"job_id": "123", "priority": 5, "tenant_id": "tenant-a"},
    )

    response = client.post("/jobs/123/cancel")

    assert response.status_code == 200
    assert response.json()["state"] == "canceled"


def test_retry_after_cancel_returns_409():
    client = TestClient(app)
    client.post(
        "/jobs/123/enqueue",
        json={"job_id": "123", "priority": 5, "tenant_id": "tenant-a"},
    )
    client.post("/jobs/123/cancel")

    response = client.post("/jobs/123/retry")

    assert response.status_code == 409


def test_enqueue_missing_required_fields_returns_422():
    client = TestClient(app)
    # Missing required `job_id` in request body.
    response = client.post(
        "/jobs/bad/enqueue",
        json={"priority": 5, "tenant_id": "tenant-a"},
    )

    assert response.status_code == 422


def test_enqueue_invalid_job_data_returns_non_200():
    client = TestClient(app)
    # Blank tenant_id is invalid for this API/scheduler.
    response = client.post(
        "/jobs/blank/enqueue",
        json={"job_id": "blank", "priority": 5, "tenant_id": "   "},
    )

    assert response.status_code != 200

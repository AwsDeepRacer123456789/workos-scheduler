# API Documentation

## Control Plane REST API

The control plane exposes a REST API built with FastAPI (Python). This API handles:

- **Job Management**: Create, read, update, delete jobs
- **Schedule Management**: Define cron schedules, one-time jobs, recurring jobs
- **Query Operations**: List jobs, filter by status, search by metadata
- **Metrics**: Retrieve system metrics and job statistics
- **Health Checks**: System health and readiness endpoints

### API Overview

- Base URL: `https://api.scheduler.internal/v1`
- Authentication: API key in `Authorization` header
- Content-Type: `application/json`
- Response format: JSON

### OpenAPI Schema

TODO: Generate OpenAPI 3.0 specification with:
- All endpoints (POST /jobs, GET /jobs/{id}, PUT /jobs/{id}, DELETE /jobs/{id})
- Request/response schemas
- Authentication requirements
- Error response formats
- Rate limiting documentation

## Control Plane API

KernelQ now includes an in-memory **FastAPI-based control-plane API** (`control_plane/api.py`). It exposes beginner-friendly endpoints for reading job state, enqueueing work, canceling jobs, retrying failed jobs, and reading scheduling metrics while the project is still in prototype mode.

### Route Summary

- `GET /health`: shallow liveness check—API process is responding.
- `GET /jobs/{job_id}`: fetch one job's current state and details.
- `POST /jobs/{job_id}/enqueue`: validate and enqueue a job.
- `POST /jobs/{job_id}/cancel`: cancel a job (state transition to `canceled` when valid).
- `POST /jobs/{job_id}/retry`: retry a job if it is currently `failed`.
- `GET /metrics`: return current scheduler metrics snapshot.

### Endpoint Examples

#### `GET /jobs/{job_id}`

Request:

```http
GET /jobs/job-123
```

Success response:

```json
{
  "job_id": "job-123",
  "tenant_id": "tenant-a",
  "priority": 10,
  "created_at": 3,
  "state": "queued"
}
```

Not found response:

```json
{
  "detail": "Job 'job-123' not found"
}
```

#### `POST /jobs/{job_id}/enqueue`

Request:

```http
POST /jobs/job-123/enqueue
Content-Type: application/json
```

```json
{
  "job_id": "job-123",
  "tenant_id": "tenant-a",
  "priority": 10
}
```

Success response:

```json
{
  "message": "Job accepted",
  "job_id": "job-123",
  "state": "queued"
}
```

Example rejection (full queue):

```json
{
  "detail": "queue is full"
}
```

#### `POST /jobs/{job_id}/cancel`

Request:

```http
POST /jobs/job-123/cancel
```

Success response:

```json
{
  "message": "Job canceled",
  "job_id": "job-123",
  "state": "canceled"
}
```

#### `POST /jobs/{job_id}/retry`

Request:

```http
POST /jobs/job-123/retry
```

Success response:

```json
{
  "message": "Job retried",
  "job_id": "job-123",
  "state": "queued"
}
```

Example rejection (wrong state):

```json
{
  "detail": "Retry allowed only from FAILED state. Current state: queued"
}
```

#### `GET /metrics`

Request:

```http
GET /metrics
```

Example response:

```json
{
  "enqueue_accepted_count": 6,
  "enqueue_rejected_full_count": 1,
  "enqueue_rejected_invalid_count": 1,
  "dispatch_count_total": 6,
  "dispatch_count_by_tenant": {"tenant-a": 3, "tenant-b": 3},
  "dispatch_count_by_priority": {"10": 1, "5": 2, "1": 2, "2": 1},
  "average_queue_wait_time": 7.66,
  "average_queue_wait_time_by_tenant": {"tenant-a": 7.0, "tenant-b": 8.33},
  "average_queue_wait_time_by_priority": {"10": 6.0, "5": 6.5, "1": 10.5, "2": 6.0},
  "queue_depth_peak": 6
}
```

### Quick Testing (Postman or curl)

You can test these endpoints with either **Postman** (import requests manually) or `curl` from terminal. Example:

```bash
curl -X POST http://127.0.0.1:8000/jobs/job-123/enqueue \
  -H "Content-Type: application/json" \
  -d '{"job_id":"job-123","tenant_id":"tenant-a","priority":10}'
```

### Automated API Tests

Alongside manual checks in Postman/`curl`, KernelQ now includes API tests in `control_plane/tests/test_api.py` using FastAPI `TestClient`.

These tests cover core outcomes such as:
- `200` for successful enqueue/cancel/metrics requests
- `404` for missing jobs
- `409` for invalid retry state transitions
- `422` for schema validation errors (missing required fields)

## Health Checks and OpenAPI

**`GET /health`** answers a simple question: *Can this control-plane HTTP process accept requests right now?* If it returns successfully, callers know the API process is up—not that every dependency in the wider system is healthy.

Today’s health check is **shallow**: it confirms the FastAPI service is responding and returns a small JSON payload (status, service name, API version). It does **not** probe databases, the message broker, cache, or workers.

Later we will add **deeper checks**—for example Postgres connectivity, Kafka health, Redis (if used), and worker heartbeats or readiness—which often ship as separate **readiness** vs **liveness** endpoints used by orchestrators.

**Automatic API documentation (FastAPI):**

- **`/docs`** — Interactive Swagger UI: browse routes, see request bodies, try calls in the browser while the server is running (for example `http://127.0.0.1:8000/docs`).
- **`/openapi.json`** — The raw OpenAPI schema (machine-readable contract). Clients, gateways, and tools can consume this to generate SDKs or validate integrations.

Together, `/docs` and `/openapi.json` make the API **discoverable and versionable**—useful both when learning the system and in interviews when you explain how you expose contracts beyond ad-hoc curl examples.

## API Testing and OpenAPI

Automated tests also assert **`/openapi.json`** returns metadata such as API title and version (see `control_plane/tests/test_api.py`).

We now test this API with FastAPI **`TestClient`** in `control_plane/tests/test_api.py`, so important behavior is checked automatically.

The tests cover both success and failure paths, including:
- `200` success responses
- `404` missing job
- `409` invalid state transition
- `422` request validation error

## Internal gRPC APIs

The control plane (Python) and worker plane (Go) communicate via gRPC for:

- **Job Assignment**: Control plane assigns jobs to workers
- **Status Updates**: Workers report job completion, failures, metrics
- **Heartbeats**: Workers send health status
- **Resource Queries**: Control plane queries worker capacity

### gRPC Service Definitions

TODO: Define proto files for:
- `JobService`: Job assignment and status reporting
- `WorkerService`: Worker registration and health checks
- `MetricsService`: Metrics collection from workers

### Example Proto Structure

```protobuf
// TODO: Full proto definitions
service JobService {
  rpc AssignJob(JobRequest) returns (JobAssignment);
  rpc ReportStatus(StatusUpdate) returns (Ack);
}
```

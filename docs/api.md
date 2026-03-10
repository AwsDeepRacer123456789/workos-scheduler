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

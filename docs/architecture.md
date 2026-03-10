# Architecture

## High-Level Overview

This system is a distributed work coordination and scheduling platform. It behaves like an operating system for backend jobs. The system is split into two planes: a control plane that makes decisions and a worker plane that executes tasks.

The control plane handles scheduling, state management, and coordination. The worker plane handles high-throughput task execution. They communicate through a message broker.

## Control Plane (Python)

The control plane is responsible for:

- **Scheduling decisions**: Deciding when jobs should run based on schedules, priorities, and resource availability
- **Job state management**: Tracking job lifecycle states (pending, queued, running, completed, failed)
- **API endpoints**: Exposing REST APIs for creating, updating, and querying jobs
- **Orchestration**: Coordinating between components, managing retries, and handling failures
- **Configuration**: Managing job definitions, schedules, and system settings
- **Observability**: Collecting metrics and logs from the control plane operations

The control plane prioritizes flexibility and rapid development over raw performance. It handles lower-frequency operations like API requests and scheduling logic.

## Worker Plane (Go)

The worker plane is responsible for:

- **Task execution**: Running the actual job code when it's time
- **Broker consumption**: Pulling jobs from the message broker efficiently
- **Concurrency management**: Handling thousands of concurrent task executions
- **Resource isolation**: Enforcing limits per job, tenant, or resource type
- **Execution metrics**: Reporting task completion, latency, and errors back to the control plane
- **Failure handling**: Implementing retries, timeouts, and circuit breakers at execution time

The worker plane prioritizes throughput, low latency, and resource efficiency. It must handle high-frequency operations reliably.

## Main Components

- **API Gateway**: Entry point for external requests (REST API)
- **Scheduler**: Decides when jobs should run (part of control plane)
- **Job State Machine**: Manages job lifecycle transitions (pending → queued → running → completed/failed)
- **Message Broker**: Queue system for distributing jobs to workers (e.g., RabbitMQ, Redis Streams, or Kafka)
- **Postgres**: Persistent storage for job definitions, schedules, and state
- **Redis**: Caching layer and optional broker backend
- **Workers**: Go processes that consume from broker and execute tasks

## Data Flow

1. **Enqueue**: Client sends job request via REST API to control plane
2. **Persist**: Control plane saves job definition and schedule to Postgres
3. **Enqueue to broker**: When job is ready to run, control plane publishes to message broker
4. **Workers consume**: Go workers pull jobs from broker
5. **Report back**: Workers update job state in Postgres and send metrics to control plane
6. **Completion**: Control plane updates final state and triggers any dependent jobs

## Job Lifecycle State Machine

TODO: Define state transitions, edge cases, and failure recovery paths.

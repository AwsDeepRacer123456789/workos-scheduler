# Architecture

## High-Level Overview

This system is a distributed work coordination and scheduling platform. It behaves like an operating system for backend jobs. The system is split into two planes: a control plane that makes decisions and a worker plane that executes tasks.

The control plane handles scheduling, state management, and coordination. The worker plane handles high-throughput task execution. They communicate through **Kafka**.

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
- **Broker consumption**: Pulling jobs from Kafka efficiently
- **Concurrency management**: Handling thousands of concurrent task executions
- **Resource isolation**: Enforcing limits per job, tenant, or resource type
- **Execution metrics**: Reporting task completion, latency, and errors back to the control plane
- **Failure handling**: Implementing retries, timeouts, and circuit breakers at execution time

The worker plane prioritizes throughput, low latency, and resource efficiency. It must handle high-frequency operations reliably.

## Main Components

- **API Gateway**: Entry point for external requests (REST API)
- **Scheduler**: Decides when jobs should run (part of control plane)
- **Job State Machine**: Manages job lifecycle transitions (pending → queued → running → completed/failed)
- **Kafka**: Durable messaging backbone used to transport runnable jobs from the Python control plane to Go workers, support consumer-group-based scaling, and enable retry / replay workflows.
- **Postgres**: Persistent storage for job definitions, schedules, and state
- **Redis**: Caching layer
- **Workers**: Go processes that consume from Kafka and execute tasks

## FIFO Scheduling Policy

FIFO means **First-In, First-Out**: the first job that enters the queue is the first job that should be chosen to run. If jobs arrive in the order A, B, C, then a FIFO scheduler will pick A first, then B, then C.

FIFO is the simplest scheduling baseline because it is:

- **Easy to reason about**: order is predictable and matches arrival order
- **Easy to implement**: minimal logic beyond a queue
- **A good reference point**: it gives a clear “default” behavior to compare against more advanced policies

In KernelQ, FIFO fits as **Python control plane scheduler logic**: the control plane decides which queued job should be dispatched next, and FIFO is the most straightforward way to produce that ordering.

FIFO has important limitations:

- **No notion of priority**: it cannot intentionally run more important jobs first
- **No fairness across tenants**: a busy tenant can dominate the queue and crowd out others
- **Can delay urgent work behind older jobs**: urgent jobs may wait a long time if earlier jobs are already ahead in line

## Data Flow

1. **Enqueue**: Client sends job request via REST API to control plane
2. **Persist**: Control plane saves job definition and schedule to Postgres
3. **Enqueue to Kafka**: When job is ready to run, control plane publishes to Kafka
4. **Workers consume**: Go workers pull jobs from Kafka
5. **Report back**: Workers update job state in Postgres and send metrics to control plane
6. **Completion**: Control plane updates final state and triggers any dependent jobs

## Job Lifecycle State Machine

### Why KernelQ Needs a Strict Job Lifecycle

A strict job lifecycle ensures that every job follows a predictable path from creation to completion. This prevents jobs from getting stuck in undefined states, makes debugging easier, and ensures the system behaves correctly even when things go wrong.

Without a strict lifecycle, jobs could be in ambiguous states like "maybe running" or "probably failed." This makes it impossible to know what's happening, retry correctly, or clean up resources. The state machine enforces rules about what can happen next, making the system reliable and predictable.

### Job States

KernelQ defines the following job states:

- **CREATED**: Job has been submitted via API but not yet scheduled. This is the initial state when a job is first created.

- **QUEUED**: Job is scheduled and waiting in the queue to be picked up by a worker. The scheduler has determined it's time to run, but no worker has claimed it yet.

- **DISPATCHED**: Job has been sent to Kafka and is available for workers to consume. A worker may pick it up soon.

- **RUNNING**: A worker has claimed the job and is currently executing it. The job code is actively running.

- **SUCCEEDED**: Job completed successfully. This is a terminal state.

- **FAILED**: Job failed during execution. This state can transition to RETRY_SCHEDULED (if retries remain) or DEAD_LETTERED (if no retries remain). It is not a terminal state.

- **RETRY_SCHEDULED**: Job failed but will be retried. The system has scheduled a retry attempt for a future time.

- **DEAD_LETTERED**: Job failed permanently after all retries were exhausted. It has been moved to a dead letter queue for manual inspection. This is a terminal state.

- **CANCELED**: Job was explicitly canceled by a user or system before completion. This is a terminal state.

### Terminal States

Terminal states are states that a job cannot leave once entered. These are:
- **SUCCEEDED**
- **DEAD_LETTERED**
- **CANCELED**

Note: **FAILED** is not a terminal state because it can transition to RETRY_SCHEDULED or DEAD_LETTERED.

Once a job reaches a terminal state, no further state transitions are allowed. The job's lifecycle is complete.

### Allowed Transitions

The state machine allows these transitions:

```
CREATED → QUEUED
CREATED → CANCELED

QUEUED → DISPATCHED
QUEUED → CANCELED

DISPATCHED → RUNNING
DISPATCHED → QUEUED (if dispatch fails or times out)

RUNNING → SUCCEEDED
RUNNING → FAILED
RUNNING → CANCELED

FAILED → RETRY_SCHEDULED (if retries remaining)
FAILED → DEAD_LETTERED (if no retries remaining)

RETRY_SCHEDULED → QUEUED (when retry time arrives)
RETRY_SCHEDULED → CANCELED
```

### Invalid Transitions

These transitions are not allowed and will be rejected:

- Any transition from a terminal state (SUCCEEDED, DEAD_LETTERED, CANCELED) is invalid.
- CREATED → RUNNING (must go through QUEUED and DISPATCHED first)
- QUEUED → SUCCEEDED (must be executed first)
- SUCCEEDED → any other state
- FAILED → RUNNING (must go through RETRY_SCHEDULED first)
- DISPATCHED → SUCCEEDED (must be RUNNING first)

### Where Retries Fit

When a job in the **RUNNING** state fails, it first transitions to **FAILED**. That keeps failure explicit and easier to measure.

From **FAILED**, the system checks if retries are configured and available:

1. If retries remain: **FAILED → RETRY_SCHEDULED**
2. If no retries remain: **FAILED → DEAD_LETTERED**

When a job is in **RETRY_SCHEDULED**, it waits for the retry delay (with exponential backoff and jitter). Once the delay expires, it transitions back to **QUEUED**, then follows the normal flow: QUEUED → DISPATCHED → RUNNING.

This creates a retry loop: **RUNNING → FAILED → RETRY_SCHEDULED → QUEUED → DISPATCHED → RUNNING** (repeat until success or max retries).

### Where Cancellation Fits

Cancellation can happen from any non-terminal state:

- **CREATED**: Cancel before scheduling
- **QUEUED**: Cancel before dispatch
- **DISPATCHED**: Cancel before worker picks it up
- **RUNNING**: Cancel during execution (worker must handle cancellation signal)
- **RETRY_SCHEDULED**: Cancel before retry executes

Once canceled, the job transitions to CANCELED (terminal state). Workers must check for cancellation signals periodically and stop execution gracefully.

### State Machine Diagram

```
                 ┌─────────┐
                 │ CREATED │
                 └────┬────┘
                      │
                      ▼
                 ┌────────┐
                 │ QUEUED │
                 └───┬─┬──┘
                     │ │
                     │ └──────────────► ┌──────────┐
                     │                  │ CANCELED │
                     │                  └──────────┘
                     ▼
              ┌────────────┐
              │ DISPATCHED │
              └─────┬──────┘
                    │
                    ▼
               ┌─────────┐
               │ RUNNING │
               └─┬───┬───┘
                 │   │
      ┌──────────┘   └───────────────┐
      ▼                              ▼
┌───────────┐                  ┌──────────┐
│ SUCCEEDED │                  │  FAILED  │
└───────────┘                  └────┬─────┘
                                    │
                     ┌──────────────┴──────────────┐
                     ▼                             ▼
            ┌─────────────────┐           ┌───────────────┐
            │ RETRY_SCHEDULED │           │ DEAD_LETTERED │
            └────────┬────────┘           └───────────────┘
                     │
                     ▼
                 ┌────────┐
                 │ QUEUED │
                 └────────┘
```

Legend:

- Solid arrows: normal transitions
- Terminal states: **SUCCEEDED**, **DEAD_LETTERED**, **CANCELED**

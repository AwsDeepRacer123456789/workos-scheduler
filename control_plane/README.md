# Control Plane

The KernelQ control plane is the "brain" of the system. It makes decisions about when jobs should run and coordinates everything.

## Why Python?

The control plane is written in Python because:

- **Fast development**: Python lets us build complex scheduling logic quickly
- **Rich ecosystem**: Great libraries for APIs, databases, and integrations
- **Readability**: Easy to understand and maintain coordination code
- **Flexibility**: Perfect for the decision-making and orchestration work

The control plane doesn't need to be super fast—it handles lower-frequency operations like API requests and scheduling decisions. The worker plane (written in Go) handles the high-speed task execution.

## Responsibilities

The control plane is responsible for:

- **Scheduling**: Deciding when jobs should run based on schedules and priorities
- **State management**: Tracking where each job is in its lifecycle
- **API endpoints**: Providing REST APIs for creating and managing jobs
- **Orchestration**: Coordinating between components and handling failures
- **Retry logic**: Managing retries when jobs fail
- **Configuration**: Managing job definitions and system settings

Think of it like a manager: it makes plans, coordinates work, and handles problems. The workers (in Go) do the actual execution.

## Current Scheduling Policies

KernelQ’s control plane includes **three** in-Python schedulers:

- **FIFO (First-In, First-Out)** — our **baseline**: jobs leave the queue in arrival order. Simple and easy to compare against.
- **Priority scheduling** — jobs with **higher priority** run sooner, so urgent work can jump ahead of less important work.
- **Weighted round robin** — rotates dispatch turns across **tenants** using weights, improving **fairness** between customers and reducing **starvation** risk when the system is busy.

## What job_state.py Models

The `job_state.py` file defines the job lifecycle state machine. It models:

- **All possible job states**: CREATED, QUEUED, DISPATCHED, RUNNING, SUCCEEDED, FAILED, RETRY_SCHEDULED, DEAD_LETTERED, CANCELED
- **Valid transitions**: Which states can move to which other states
- **Terminal states**: States that jobs cannot leave once reached
- **Transition validation**: Functions to check if a state change is allowed

This ensures jobs follow a predictable path and prevents them from getting stuck in undefined states.

## What's Coming Next

This control plane will grow to include:

- **REST API**: FastAPI endpoints for job management (create, read, update, delete jobs)
- **Scheduler**: Logic that decides when to move jobs from CREATED to QUEUED
- **Orchestration**: Coordinating retries, handling failures, managing dependencies
- **Database integration**: Storing job definitions and state in Postgres
- **Message broker integration**: Publishing jobs to the broker for workers to consume
- **Metrics and observability**: Tracking system health and performance

## Structure

- `kernelq/`: Core scheduling and job management logic
- `tests/`: Unit and integration tests

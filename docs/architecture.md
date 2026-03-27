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

## Priority Scheduling Policy

**Priority scheduling** means the scheduler chooses what to run next based on **importance or urgency**, not only on **arrival order**. Each job carries a priority (for example high / normal / low, or a numeric rank). When picking the next runnable job, the scheduler prefers **higher-priority** work over lower-priority work.

**How it differs from FIFO:** **FIFO** only asks “who got here first?” **Priority scheduling** also asks “who matters most?” So a **newer** high-priority job can be ordered **ahead of** an **older** low-priority job—something pure FIFO will never do.

**Where it fits in KernelQ:** Priority rules live in the **Python control plane scheduler logic**: the control plane decides **which queued job to dispatch next** (and in what order). Workers in Go **execute**; they do not own the policy that decides global priority among waiting jobs.

**A major limitation:** naive priority scheduling can cause **starvation**—low-priority jobs may wait a very long time (or never run) if higher-priority work keeps arriving. Real systems often add **fairness** mechanisms (e.g., aging, caps, or tenant quotas) so low-priority work still makes progress.

## Starvation and Fairness

**Starvation** (in scheduling) means some work waits **far too long** or **never gets a turn**, even though the system is still busy processing other jobs. The starved jobs are stuck behind a policy or load pattern that never favors them.

**Why naive priority can starve low-priority jobs:** if the scheduler *always* prefers higher priority, and higher-priority jobs **keep arriving**, lower-priority jobs may **never reach the front of the line**. There is no rule that guarantees them *any* progress—only that *more important* work goes first.

**Fairness** means the scheduler tries to give **each tenant or queue a fair share of progress** over time—not letting one customer or job class **monopolize** the system forever, even when priorities exist. Fairness is often implemented with **limits**, **quotas**, **aging** (boosting jobs that wait too long), or **round-robin** style turns across tenants.

In KernelQ, starvation and fairness concerns inform **how we design** the Python control plane scheduler: not just *who is most important*, but *who still gets to run* when the system is overloaded.

## Weighted Round Robin Scheduling Policy

**Weighted round robin (WRR)** is a way to serve **multiple queues** (often one per **tenant** or **job class**) in **rotating turns**. Each queue gets repeated chances to dispatch a job. **Weights** set how strong each queue’s share is—for example, a weight of `2` might mean “roughly twice as many turns” as a weight of `1` in each full cycle.

**How WRR helps compared to naive priority:** naive priority can **starve** whole categories of work. WRR adds **structure**: even busy tenants take turns according to their weight, so quieter tenants are not **permanently crowded out** by a flood of high-priority work elsewhere.

**A limitation:** WRR is often **fairer across tenants**, but it **does not by itself solve every latency or priority problem**. You can still have urgent jobs delayed if the policy does not combine WRR with **priority**, **SLO-aware rules**, or **per-tenant caps**. Choosing weights can also be subtle: “fair” sharing is not the same as “optimal” for every workload.

**Where it fits in KernelQ:** weighted round robin is **Python control plane scheduler logic**—the layer that decides **which tenant’s queue** (or which class of job) gets the next dispatch opportunity. Go workers **run** jobs; they do not decide global rotation and weights across tenants.

## Bounded Queues and Admission Control

A **bounded queue** is a waiting line with a **maximum capacity**. When it is full, the system **stops accepting more items** in that queue until space opens up (for example, after jobs are dispatched or complete). That cap is intentional: it keeps memory and backlog under control.

**Admission control** is the policy that answers: **“Should we accept this new job right now?”** It runs *before* work enters deep queues or downstream systems. If the system is already saturated, admission control **rejects**, **rate-limits**, or **defers** new submissions instead of pretending everything can be handled immediately.

**Why unbounded queues are dangerous in a distributed system:** if queues can grow without limit, overload in one place spreads as **unbounded memory use**, **long unpredictable delays**, and **cascading failures** (every component keeps accepting work it cannot finish). The failure mode becomes “the whole cluster falls over” rather than “the API says *not now* and clients back off.”

**When KernelQ is full:** the **Python control plane** should **reject new work** (or apply an explicit overflow policy), not silently accept an **unlimited backlog**. Clients then know to **retry later**, **reduce load**, or **route elsewhere**. That protects Postgres, Kafka, and workers from being drowned by work the system cannot make progress on.

**Where this fits in KernelQ:** bounded queues and admission control belong in the **Python control plane**, **before** jobs are **dispatched to Kafka**—at the API and scheduling layers where jobs are first admitted and queued. Once work is safely bounded and intentional at the edge, downstream components can rely on predictable load.

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

# Performance

## Baseline Metrics Plan

| Metric | What it means | How we'll measure it | Why it matters | Target |
|--------|---------------|----------------------|----------------|--------|
| Throughput (tasks/sec) | How many tasks finish each second | Count completed tasks per second | Shows if the system can handle your workload | |
| End-to-end latency p50/p95/p99 (enqueue→completion) | How long tasks take from start to finish. p50 is the middle time, p95 is slower than 95% of tasks, p99 is slower than 99% | Time from when a task enters the queue until it finishes | Users care about speed. High latency means slow tasks | |
| Success rate (%) | What percent of tasks finish without errors | Count successful tasks divided by total tasks | Shows if the system is reliable | |
| Error rate (%) | What percent of tasks fail | Count failed tasks divided by total tasks | High error rate means something is broken | |
| Retry rate (%) | What percent of tasks need to run again after failing | Count retried tasks divided by total tasks | Shows how often things fail the first time | |
| DLQ rate (%) | What percent of tasks go to the dead letter queue after all retries fail | Count DLQ tasks divided by total tasks | Tasks in DLQ need manual attention | |
| Duplicate execution rate (target 0) | How often the same task runs twice by mistake | Count duplicate runs divided by total tasks | Duplicates waste resources and can cause problems | 0 |
| Queue depth under burst load | How many tasks are waiting when you send many at once | Count tasks waiting in queue during a burst | Shows if the system can handle sudden spikes | |
| Recovery time after failure injection (worker killed, broker down, db slow) | How long it takes to get back to normal after we break something on purpose | Time from failure until system works normally again | Shows how resilient the system is | |
| Cost per 1M tasks (rough estimate) | How much money it costs to run one million tasks | Calculate server and resource costs divided by task count | Helps plan budget and compare options | |

## Load Testing Methodology

TODO: Define test scenarios, load profiles, ramp-up strategies, and success criteria.

## Failure Injection Experiments

TODO: Define failure scenarios (worker crashes, broker outages, database slowdowns) and expected recovery behaviors.

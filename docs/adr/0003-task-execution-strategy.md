# ADR 0003: Use Queue-Compatible Workflow Semantics With Local Runner First

Status: accepted

## Problem

AutomateDub has long-running, expensive, retryable tasks that must support resume, cancellation, selective reruns, quality gates, and future distributed workers.

## Alternatives

- Shell scripts
- Simple in-process sequential runner
- Local runner using production workflow semantics
- Dramatiq or RQ immediately
- Celery immediately
- Temporal-style workflow engine

## Tradeoffs

- Shell scripts are fast but cannot carry product-grade state.
- A simple local runner is easy but can create migration pain.
- Queue-compatible semantics add upfront design but preserve future scalability.
- Celery and Temporal are powerful but operationally heavy early.

## Final Decision

Define workflow/job/task/attempt semantics now. Implement local execution first only as one runner for the same task contract. Defer distributed queue infrastructure until concurrency requires it.

## Consequences

- Every task must declare inputs, outputs, idempotency key, retry policy, timeout, cache policy, cost policy, and quality gates.
- Later worker queues should not require domain state redesign.

## Future Reconsideration

Adopt Dramatiq, RQ, Celery, or a workflow engine when concurrency, scheduling, or distributed execution becomes a real requirement.


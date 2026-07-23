# ADR 0011: Add An Explicit Feedback Learning System

Status: accepted

## Problem

Manual corrections and provider performance data are valuable. If they are not captured structurally, the platform will not improve over time.

## Alternatives

- Ignore corrections after each job.
- Store corrections only as local edits.
- Convert approved corrections into scoped, auditable learning records.

## Tradeoffs

- Learning records require privacy, rights, and rollback controls.
- They create compounding product quality over time.

## Final Decision

AutomateDub will include an explicit Learning System with project, series, organization, and platform memory scopes.

## Consequences

- Reuse of customer data must be permissioned.
- Corrections can update glossary, pronunciation, character style, voice assignment, provider routing, and benchmarks.

## Future Reconsideration

Automated model fine-tuning may be added later only after data rights and evaluation discipline are mature.


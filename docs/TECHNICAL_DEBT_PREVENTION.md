# Technical Debt Prevention

## Non-Negotiable Rules

- No provider SDK types in domain or application business logic.
- No generated artifact is overwritten silently.
- No production import from `research/`.
- No expensive task without cost, cache, and provenance records.
- No pipeline stage without quality policy.
- No character correction without downstream invalidation rules.
- No voice cloning without consent and license records.
- No provider default without benchmark scorecard.

## Architecture Fitness Checks

Before merging significant changes, verify:

- dependency direction remains valid
- domain model is provider-independent
- database migration is reversible or explicitly irreversible with reason
- artifacts have lineage
- task is idempotent or marked unsafe with justification
- cost events are emitted for paid/provider work
- quality records exist for user-facing output
- tests cover contract boundaries

## Debt Register

Any intentional shortcut should record:

- decision
- reason
- owner
- affected subsystem
- expiration condition
- cleanup plan

Shortcuts without expiration become product risk.


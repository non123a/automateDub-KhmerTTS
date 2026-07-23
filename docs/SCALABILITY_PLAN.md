# Future Scalability Plan

## Scale Targets

The architecture should eventually support thousands of hours of media, multiple organizations, multiple reviewers, distributed workers, and provider routing across cloud and local models.

## Evolution Path

### Local Product

- filesystem artifact store
- SQLite or local PostgreSQL
- in-process runner
- CLI-first operation

### Team Product

- PostgreSQL required
- object storage optional
- background workers
- web review UI
- project/user roles

### SaaS Product

- managed PostgreSQL
- object storage
- worker queues
- tenant isolation
- billing and usage metering
- audit logs
- provider routing by policy
- dashboard/API
- backup/restore
- data retention controls

### Enterprise Product

- customer-managed keys
- customer-owned provider credentials
- private model deployment
- region controls
- advanced audit exports
- SSO/RBAC
- contractual data retention

## Scaling Rules

- Blob storage and metadata storage remain separate.
- Long-running work happens in workers, not request handlers.
- Every task is idempotent.
- Every provider call is tracked.
- Every expensive output is cacheable or intentionally non-cacheable.
- Tenant boundaries are explicit before SaaS launch.


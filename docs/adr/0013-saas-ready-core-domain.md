# ADR 0013: Keep The Core Domain SaaS-Ready

Status: accepted

## Problem

The first product may be local and CLI-first, but the long-term goal may be commercial SaaS. Retrofitting organizations, projects, billing, audit, and tenant isolation later can require major rewrites.

## Alternatives

- Build local-only and migrate later.
- Build full SaaS first.
- Keep the core domain SaaS-ready while implementing local-first interfaces.

## Tradeoffs

- SaaS-ready modeling adds some upfront complexity.
- Full SaaS infrastructure too early would slow the first vertical slice.

## Final Decision

AutomateDub will keep core concepts compatible with future SaaS: organizations, projects, users/reviewers, usage records, provider invocations, audit logs, and tenant-aware storage.

## Consequences

- Local mode can use a default organization/user internally.
- Commercial deployment will not require redesigning core records.

## Future Reconsideration

If the product remains permanently single-user, SaaS fields may stay dormant but should not be removed until strategy is settled.


# ADR 0002: Use PostgreSQL-Compatible Relational State With Local Profile

Status: accepted

## Problem

AutomateDub needs durable workflow state, artifact lineage, quality records, provider invocations, cost ledger, rights/consent metadata, and future SaaS tenant data.

## Alternatives

- Files only
- SQLite only
- SQLite first with PostgreSQL-compatible schema
- PostgreSQL from day one
- DuckDB

## Tradeoffs

- Files are useful for large artifacts but weak for querying, retries, review, audit, and dashboard needs.
- SQLite is simple for local single-user operation but weak for concurrent workers and SaaS.
- PostgreSQL is the correct long-term target but adds local operational setup.
- DuckDB is useful for analytics, not transactional workflow state.

## Final Decision

Design the canonical schema for PostgreSQL compatibility from day one. Allow SQLite only as a local/development profile when it passes compatibility tests. Use SQLAlchemy 2.0 and Alembic.

## Consequences

- Schema design must consider indexing, locking, JSON usage, migration tests, and future tenant fields.
- PostgreSQL becomes required before distributed workers, dashboard operation, or commercial SaaS.

## Future Reconsideration

If the product remains permanently local and single-user, SQLite may remain supported. If SaaS becomes primary, managed PostgreSQL should become the default runtime database.


# 0001. Technology stack

- Status: accepted
- Date: 2026-10-12

## Context
One person owns the system long term. It replaces an ERPNext/Frappe setup and must grow
(CRM, email, AI). Priorities: stability, popularity (docs, hiring, AI assistance), low
operational load.

## Decision
PostgreSQL 16; Python 3.13 with FastAPI, SQLAlchemy 2 (synchronous) and Alembic; React 18 +
TypeScript + Vite with Mantine, TanStack Query and AG Grid Community. uv and pnpm for
dependencies. Docker Compose for deployment.

Synchronous SQLAlchemy because async adds failure modes (event-loop blocking, driver
quirks) without benefit at this scale; FastAPI runs sync endpoints in a thread pool.
No Redis or message broker: PostgreSQL already provides transactions, row locks
(SKIP LOCKED) and LISTEN/NOTIFY, which cover the queue and realtime needs.

## Consequences
One database to back up and monitor. If event volume ever outgrows PostgreSQL, the outbox
can feed an external broker without changing producers.

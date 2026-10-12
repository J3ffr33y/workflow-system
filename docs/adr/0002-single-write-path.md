# 0002. Every write goes through the command bus

- Status: accepted
- Date: 2026-10-12

## Context
The old system assembled history from three places (Version, Deleted Document, specially
prefixed Comments), and undo/automation/notification logic was scattered.

## Decision
All changes are Commands executed by `platform/commands/bus.py`. The bus checks
permissions and idempotency, runs the handler in one transaction, captures field-level
before/after values automatically at flush time for every `Audited` model, writes
outbox events with per-subscriber deliveries, and logs the command. Query code uses a
PostgreSQL connection with `default_transaction_read_only=on`; a flush of an audited
model outside the bus raises.

## Consequences
Activity feeds, undo, automation triggers, notifications, realtime refresh and migration
rollback are all derived from one mechanism. Every exposed command is automatically an
HTTP endpoint. Queue bookkeeping tables (deliveries, job runs) are the only writes done
outside the bus, and they are not audited models.

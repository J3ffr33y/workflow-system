# 0005. Client facts live once and are mirrored on boards

- Status: accepted
- Date: 2026-10-12

## Context
The old system copied portal access, ABN, address and contact onto every project, then
synchronised them on save; copies drifted.

## Decision
These facts are stored on the client, entity or primary contact. A `mirror` field type
shows them on items (read-only), and they are filterable like any other column.

## Consequences
One source of truth. If an item ever genuinely needs its own value, add a normal item
field for it.

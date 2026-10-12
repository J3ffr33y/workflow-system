# 0008. Data migration is a product feature

- Status: accepted
- Date: 2026-10-12

## Decision
Migration runs stage source rows, store an editable JSON mapping (columns, value maps,
options), validate with the same field types used everywhere, create missing options or
placeholder users only on explicit "prepare", and import row by row as commands sharing
a batch id. `external_refs` maps source keys to new ids so re-imports update instead of
duplicating. A finished run reports per-column reconciliation and can be rolled back by
reverting its batch.

## Consequences
Cut-over can be rehearsed many times. The same `external_refs` mechanism will back future
syncs (email threads, Xero, drives).

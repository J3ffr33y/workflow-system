# 0004. Core columns plus JSONB custom fields

- Status: accepted
- Date: 2026-10-12

## Context
Accounting and Grants need different fields, and new fields appear often. ERPNext's
approach (custom columns on one shared table) mixed both product lines on `Project`.

## Decision
Columns that business logic depends on are real columns on `items` (board, client,
entity, fiscal year, status, due date, archive and highlight info). Everything else is a
`field_definitions` row per workspace with values in `items.data` (JSONB), validated by
the field-type registry. Keys are immutable; labels are free.

## Consequences
New fields need no migration or deploy. Values are still typed (ISO dates, user ids).
Filtering/sorting compile JSONB paths to typed SQL; heavily used fields can get
expression indexes. Never mutate `data` in place: assign a new dict so SQLAlchemy and
the audit see the change.

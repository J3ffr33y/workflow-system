# Changelog

All notable changes are recorded here. Versions follow [SemVer](https://semver.org/).

## [Unreleased]

### Added
- Client facts on boards are editable: ABN, State, Industry, portal access, contact name
  and other mirror columns save to the client (or its primary entity / contact), so the
  client page and every board show the same value. New command `clients.set_linked_value`.
- Imports split a cell of merged updates (joined with ", " by the old export) into
  separate updates. Earlier imports get a preview and a "Split updates" action on the run
  page (`migration.split_comments`, undoable; removed by rolling back the run).

### Changed
- Data migration run page is a step-by-step wizard: map columns, match values, dry-run
  check, import, with Back / Next and a clear note that nothing is written before import.
- Mirror columns use the client field's own type (State shows as a dropdown with labels)
  and fall back to the client's primary entity when an item has none.

### Fixed
- Picking an option or date with the mouse in a board cell editor did not save.

## [0.2.0] - 2026-11-02

### Added
- "My work" home page: tasks assigned to me grouped by overdue / this week / later /
  no date, unread @mentions and alerts, and a reserved slot for emails waiting for me
  (filled in when the email module lands). New endpoint `GET /api/home/tasks`.
- Data structure page (Settings → "About this system"): every table, column and
  relation read from the live schema, plus each product line's custom fields and where
  their values are stored. Structure only, no records.
- Design for the R&D report (RDTI) module: `docs/RDTI.md` and ADR-0009 (proposed).
- R&D report workbench (first version) on Grants projects: upload materials (PDF, Word,
  text) split into citable passages, activities, evidence assessment per RDTI element,
  gap checklist with email draft, cited report draft with review mode (every statement
  coloured by source status and clickable to its passage), Word export (clean / review).
- Files module (versions, checksums) and AI gateway (`FLOW_AI_PROVIDER=fake|anthropic|off`,
  client AI consent check, call log). Default `fake` works offline.
- Client field "AI Processing Consent" for Grants (migration 0002).

### Changed
- Docker: api gets an `uploads` volume for original files; back it up with `pgdata`.

## [0.1.0] - 2026-10-12

### Added
- First complete demo covering the current Smart Board for Accounting and Grants:
  boards with inline editing, saved views, filters, bulk edit, roll over, archive and
  trash; clients with entities and contacts; tasks with subtasks; updates with
  @mentions and notifications; activity history with undo; automations (status,
  field, date triggers; ten actions) with run logs; CSV export.
- Data migration from the old system: CSV (any encoding) and ERPNext REST, column and
  value mapping, re-runnable imports, reconciliation report, rollback.
- Platform: single command bus with automatic audit, transactional outbox, worker,
  scheduler, configurable fields / statuses / roles per product line.

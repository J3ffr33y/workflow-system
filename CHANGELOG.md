# Changelog

All notable changes are recorded here. Versions follow [SemVer](https://semver.org/).

## [Unreleased]

### Added
- Due-date rules carried over from the old Smart Board (Setup → Due date rules):
  - month-end dates stay at month end when pushed forward (30 Apr + 1 month = 31 May);
  - "Quarterly: next ATO due date" per board: a quarterly due date rolls to the next
    date in an editable ATO table, and stops with a note in the automation log past
    the last row;
  - "Monthly: skip BAS months" per board: a monthly due date or target month landing in
    January, April, July or October moves one month on.
  New installs turn these on for BAS and a new IAS board.
- Date triggers accept a combined lead time (months + weeks + days), as Grants used.

### Changed
- Highlight rules behave like the old Grants board: a row keeps its highlight while it is
  inside the window and loses it (only the rule's own highlight) once the date moves out.

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

# Changelog

All notable changes are recorded here. Versions follow [SemVer](https://semver.org/).

## [Unreleased]

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

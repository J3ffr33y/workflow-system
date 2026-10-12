# 0007. Automations as trigger / condition / action registries

- Status: accepted
- Date: 2026-10-12

## Decision
A rule is JSON: one trigger (event or schedule), optional conditions in the shared
filter language (evaluated in SQL), and a list of actions. Triggers and actions are
classes in a registry. Event triggers run from the outbox subscriber; date triggers run
hourly and fire once per item per date value (dedupe key). Changes made by a rule run as
a command (origin `automation`), so they are audited and undoable. Cascades stop at
depth 3; "quiet" commands (undo, migration, cascades such as client archive) do not
trigger rules.

## Consequences
No BPM engine. New behaviours are new action classes, available to every product line.

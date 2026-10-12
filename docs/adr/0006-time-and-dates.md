# 0006. Time handling

- Status: accepted
- Date: 2026-10-12

## Decision
Timestamps are `timestamptz` in UTC. Business dates are `date`. "Today" is computed in
`settings.business_timezone` (Australia/Sydney) by `core/time.py`, which is the only
place allowed to read the clock (tests can freeze it).

## Consequences
Date-based automations fire on the Sydney calendar day across DST changes.

# 0009. RDTI report writing is a module inside the system

- Status: proposed
- Date: 2026-11-02

## Context
An earlier requirements draft for an "RDTI Report Writer" assumed a standalone FastAPI
service with its own database, a Streamlit UI and a Frappe connector, because the
company system was still ERPNext. The new system already provides the same stack
(FastAPI + PostgreSQL), plus clients, fiscal years, Grants items, users and roles, the
audited command bus, background jobs and a reserved `platform/ai_gateway`.

## Decision
Build RDTI report writing as a business module `modules/rdti` attached to Grants items
(`item_id`). File storage and text extraction become a shared files module, and model
calls go through a minimal `platform/ai_gateway`; both are built first because other
product lines need them too. The evidence assessment engine is a pure function over
text chunks and a rule set, so it can be extracted into a separate package later.
Rules (RDTI elements, scoring, writing conventions) are configuration data with a YAML
seed, not code. No pgvector in the first version. Design: `docs/RDTI.md`.

## Consequences
Multi-user access, permissions, audit and undo come for free, and the review UI is
built in the existing web app. The roadmap order changes: files and the AI gateway move
ahead of reports/CRM. Whether the module may live in the company system depends on the
IP decision still open in `docs/RDTI.md`; if it must remain personally owned, the engine
and rules move to a separate package licensed to the company.

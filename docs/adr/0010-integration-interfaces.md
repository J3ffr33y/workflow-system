# 0010. Integration interfaces: API tokens, webhooks, external IDs

- Status: proposed
- Date: 2026-11-10

## Context
The roadmap adds email, Xero, shared drive, reports and AI. Each of them either calls
into the system (a script, a sync job, a BI tool) or needs to hear about changes (push
to Teams, rebuild a search index). Until now the only way in was the browser session
cookie with CSRF, and the only way out was in-process event subscribers.

## Decision
1. **Personal API tokens** (`api_tokens`, `Authorization: Bearer flow_pat_…`). A token
   acts as its owner: same `Actor`, same command bus, same permissions, audit origin
   `api`. Only the SHA-256 hash is stored; the value is shown once. Tokens can be
   read-only, expire by default after 90 days, and are revoked when the owner is
   deactivated. Commands marked `session_only` (create token, change / set password,
   rotate webhook secret) refuse token callers, so a leaked token cannot mint more
   tokens or lock its owner out.
2. **Webhooks** (`integrations` module). Superadmins register endpoints with event
   patterns limited to business records (`item.*`, `task.*`, `comment.*`, `client.*`,
   `client_entity.*`, `contact.*`, `board.*`, `file.*` and their member tables). One
   outbox subscriber fans out; each (endpoint, event) has a row in `webhook_deliveries`
   so a failing endpoint is retried without re-sending to healthy ones. Bodies are
   signed: `X-Flow-Signature: t=<unix>,v1=<HMAC-SHA256("<t>.<body>")>`. Quiet changes
   (undo, migration, cascades) are skipped unless the endpoint opts in.
3. **`webhook_deliveries` is queue bookkeeping**, like `event_deliveries` and `job_runs`,
   and is written directly by the subscriber instead of through the command bus. The
   endpoint configuration itself (`webhook_endpoints`) is business data and goes through
   commands with audit.
4. **External IDs for integrations reuse `external_refs`** (ADR-0008): the
   `external_refs.link` command and `GET /api/integrations/external-refs` let any sync
   find "our record for their ID" and back.
5. **Field defaults** (`config.default`) and server-side `required_on_create` for API
   callers, so records created through the API follow the same rules as the New item
   form.

## Consequences
Integrations can be built outside the codebase (scripts, n8n/Power Automate, a Xero
sync) without new endpoints. The webhook secret is stored in clear because it is needed
to sign; database access therefore implies the ability to forge webhook calls, which is
acceptable at this size but should move to an encrypted column if a KMS is introduced.
Token last-use time is not recorded (it would need a write on the read path); review
tokens by creation date and expiry instead.

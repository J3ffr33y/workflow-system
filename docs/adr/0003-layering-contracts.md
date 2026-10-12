# 0003. Layering enforced by import-linter

- Status: accepted
- Date: 2026-10-12

## Decision
`app.api -> app.modules -> app.platform -> app.core`, checked in CI. A second contract
forbids LLM SDK imports outside a future `platform/ai_gateway`.

## Consequences
Rules that are only written down get forgotten; these fail the build instead. Changing a
contract requires its own PR with a reason.

# ADR-0009: Single-user v1 with clean multi-user seams

**Status:** Accepted (2026-07-06)

**Context.** One owner-trader today; possible product later.

**Decision.** No multi-tenant machinery in v1. Auth = single bearer token. But: no global
mutable state in request paths, user-scoped columns where cheap, and secrets/config per
environment — so multi-user is an upgrade, not a rebuild.

**Consequences.** Fast build now; a future auth provider (e.g. Supabase Auth) slots in at
the API boundary.

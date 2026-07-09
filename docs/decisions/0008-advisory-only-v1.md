# ADR-0008: Advisory-only v1; Broker stays a paper stub

**Status:** Accepted (2026-07-06)

**Context.** User wants advisory now, approval-gated auto-execution later ("coming soon").
A software bug must never be able to move money in v1.

**Decision.** v1 uses no exchange keys (or read-only). A `Broker` interface exists from
day one with only a paper implementation. Live execution will later arrive as a new
implementation behind an explicit approval flow (`propose_order` MCP tool), never as
edits to analysis code.

**Consequences.** Execution risk is structurally zero in v1; the future bot is a plug,
not a rewrite.

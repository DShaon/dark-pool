# ADR-0010: DARKPOOL design language

**Status:** Accepted (2026-07-06)

**Context.** The UI must be premium, unique, and consistent regardless of which model
builds any given screen.

**Decision.** Implement `docs/MASTER_PLAN.md` PART C exactly. Organizing rule: market data
is obsidian monochrome with teal/red semantics; **AI judgment is always gold**. Tokens
(C1), Instrument Sans / IBM Plex Mono / Instrument Serif Italic verdicts (C2), signature
animations (C4) within the performance contract (C5). Banned: purple gradients,
glassmorphism, shadows, bounces, spinners.

**Consequences.** Every screen is spec-checkable; motion budget is CI-visible via frame
warnings; design drift is a bug, not taste.

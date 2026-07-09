# ADR-0005: Mandate-based analysts (not generic prompts)

**Status:** Accepted (2026-07-06)

**Context.** N models given the same generic "analyze this" prompt converge on similar
takes — fake debate.

**Decision.** Four fixed seats with role mandates: TREND (best continuation case),
CONTRARIAN (best reversal case), DERIVATIVES (funding/OI/liquidations read), RISK OFFICER
(the case for no trade). Same Market Brief in; disagreement by construction. Which model
fills a seat is config (ADR-0004).

**Consequences.** Divergence is meaningful signal. Seat-level accuracy is tracked in
`model_scores` and feeds CIO weighting.

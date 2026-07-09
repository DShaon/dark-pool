# ADR-0007: Calibrated confidence formula

**Status:** Accepted (2026-07-06)

**Context.** Raw LLM self-reported confidence is uncalibrated decoration.

**Decision.** Published confidence = 0.5 × deterministic checklist score (MTF alignment +
structure state + derivatives confirmation + distance-to-liquidity, computed in code)
+ 0.5 × panel agreement (consensus_state + score-weighted analyst votes). The journal
grades every published confidence against outcomes (Brier score); blend weights get
recalibrated from evidence. Raw LLM confidence is never displayed.

**Consequences.** Confidence becomes a measured quantity with an audit trail; the
calibration curve is a first-class analytics view.

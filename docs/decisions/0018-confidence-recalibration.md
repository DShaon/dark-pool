# ADR-0018 — Confidence recalibration: seat reliability + blend refit from graded outcomes

**Status:** accepted · 2026-07-10 · **authored on Fable** (§F5 — the last reserved item)
**Implements:** ADR-0007's closing clause ("the journal grades every published
confidence against outcomes; blend weights get recalibrated from evidence") and
FR-6's model_scores loop. Extends ADR-0015 (the confidence formula being tuned).

## Context
ADR-0007 fixed the formula (0.5 × checklist + 0.5 × agreement) and promised that
graded outcomes would recalibrate it. Recalibration errors are the quietest kind of
money-risk: a skewed weight doesn't crash anything — it just makes every future
published confidence subtly wrong, compounding as data accumulates. Every rule
below is therefore a deliberate, documented decision; **changing any constant
requires a new ADR, not an edit** (the golden tests enforce this).

## Decisions

### 1. The unit of learning
An `OutcomeRecord`: a **CIO-plan-sourced** trade graded TP or SL, carrying the
published confidence, its two formula halves (checklist, agreement), and the
per-seat votes (`DivergenceReport.votes_by_seat`, added for this). Quick-Read
trades don't qualify — they publish conviction, not the ADR-0007 confidence, so
they have nothing to calibrate. Rolling log capped at 500 (file-backed,
`data/calibration.json`, single-user P1). Ingestion is **idempotent on
(symbol, closed_at)** — a page-reload re-grade must not double-count.

### 2. Seat reliability → weights
* **Scoring:** a directional vote is a hit iff (agreed with the plan AND TP) or
  (dissented AND SL) — the dissenter earns credit when the desk loses.
  **`no_trade` votes are never scored**: an abstention has no counterfactual, and
  inventing one would poison the data.
* **Recency decay:** λ = **0.977 per outcome** (half-life ≈ 30 trades). Count-based,
  not wall-clock — quiet weeks must not erase knowledge.
* **Shrinkage:** accuracy = (hits + 2)/(n + 4) — a Beta(2,2) prior, 4
  pseudo-observations at 50%, so a 2-trade hot streak barely moves anything.
* **Weight = accuracy / 0.5, clamped [0.6, 1.4]:** a cold seat is exactly neutral
  (1.0); a bad seat is dampened but **never silenced** (mandate diversity is the
  design — a "wrong" contrarian still carries disagreement information); a hot
  seat is boosted but capped.
* Weights multiply each seat's conviction inside the agreement share.

### 3. Blend refit (the 0.5/0.5)
Grid-search w ∈ {0.30 … 0.70, step 0.05} minimizing the **recency-decayed Brier
score** of `w·checklist + (1−w)·agreement` against outcomes (TP=1, SL=0), then
**shrink toward 0.5**: `w ← 0.5 + (w_opt − 0.5) · n_eff/(n_eff + 50)`, and
**freeze at exactly 0.5 below 10 effective outcomes**. Triple guard (clamp +
shrink + threshold) because overfitting a dozen trades must never move the
desk's published numbers.

### 4. The hard safety rule
**Learned weights adjust CONFIDENCE only — never direction.** The divergence
plurality is computed from raw convictions, unweighted. If weights fed direction,
a lucky streak would compound into a feedback loop that flips trades. This door
stays closed; reopening it is its own ADR.

### 5. Mechanics
Recalibration is a **pure function recomputed from the full log on every write** —
no incremental state to drift, fully auditable, cheap at the 500-record cap.
`compute_confidence` takes an optional `CalibrationParams`; with none (or nothing
earned yet) it is bit-identical to the original formula and the breakdown says
`calibrated=false`. The published breakdown always records the blend_w and seat
weights actually used (NFR-7). `/plan` reads params fresh per run.
API: `POST /outcomes` (journal reports a graded trade) · `GET /calibration`
(full state: per-seat scores, blend, Brier of blend vs each half alone, and the
win-rate-per-confidence-bucket curve). Frontend: the CIO verdict card gains
"save to journal" (carrying the payload); grading such a trade auto-reports;
the journal's seat leaderboard + calibration curve render LIVE from
`/calibration` once outcomes exist (SAMPLE placeholders until then).

## Consequences
- The loop closes: publish plan → save → grade against real candles → report →
  seat weights + blend shift → next plan's confidence reflects earned trust.
- Everything is honest by construction: uncalibrated plans say so; the curve and
  Brier comparison expose whether the formula's halves are actually predictive.
- 13 golden tests hand-verify the constants (decayed counts, both clamps,
  dissenter credit, the 0.539 shrunk-blend value, curve buckets, idempotency).
  Verified live end-to-end: post → weights 1.2/0.8 (matching hand math) →
  duplicate rejected → journal leaderboard LIVE → store reset clean.
- Known limits, accepted for P1: single-user file store (Postgres later, same
  call sites); per-seat identity is the MANDATE, not the model filling it — if
  the roster swaps a seat's model, its history carries over (revisit when
  model_scores gets per-model granularity); `invalidated` trades never report
  (human judgment, not a price fact).

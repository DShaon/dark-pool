# ADR-0019 — Setup journal loop: real variants, failure post-mortems, CIO feedback

**Status:** accepted · 2026-07-10/11 · **authored on Fable** (the CIO-feedback wiring
and the rejected auto-tuning question are money-risk judgment calls; the variant
math itself is deterministic and mechanical)
**Implements:** FR-4's variant fan (v1 slice) + FR-6's "AI memory" loop, closing the
gap between "here's a setup" and "did it work, and does the desk remember."

## Context
The Trade Setups shelf showed six venue/style cards (SPOT/PERP/MARGIN/GRID/OPTIONS)
with **fake levels scaled off live price** — a design placeholder, never wired to
real data. The owner asked for three things: (1) a "add to journal" button per card,
(2) auto-grading of whether the trade won or lost, (3) a way to record *why* a trade
failed and have the system "auto-improve strategy" from it.

Grading fake levels would teach the system nothing real, so this ADR starts by
making the variants **real**, then builds the learning loop on top.

## Decisions

### 1. Setup variants become deterministic ATR-rule scaffolds (`desk/setups.py`)
Six variants, computed in **pure code from the Market Brief** (no AI): each style
sizes its entry band / stop / targets from its own anchor timeframe's ATR
(scalp→15m, intraday→1h, swing→4h, spot→4h; band/stop/target multipliers are a
hand-verified table, golden-tested). Gating is honest, not decorative:
- Directional variants (scalp/intraday/swing/spot) require a **directional MTF
  bias** (`alignment.bias != "mixed"`) — otherwise `tradeable=false` with the
  reason "the desk stands aside."
- The **grid is the inverse**: it harvests chop, so it's tradeable exactly when
  bias IS mixed.
- **Options stays informational v1** — no held-position tracking yet, so it's
  never `tradeable` and never `gradeable`.
- Missing ATR on a variant's own anchor TF disables only that variant.
These are labeled **"engine rule variants"** in the UI (provenance registry) —
not full analyst plans. `/setups/{symbol}` is a pure GET over the cached brief;
zero new upstream cost.

### 2. The journal loop
Each tradeable + gradeable card (the 4 directional ones) gets "＋ journal." Saving
carries `source: "setup"` + the variant key. The existing P3 auto-grade
(deterministic candle-walk) already handles TP/SL detection — no changes needed
there; it now just also applies to setup-sourced trades.

### 3. Failure post-mortems (`desk/lessons.py`)
A curated, stable-key failure taxonomy (10 tags: against_trend, news_event,
funding_crowded, late_entry, stop_too_tight, target_too_far,
low_liquidity_session, missing_context, bad_signal, other) plus a free-text note
("what info was missing"). Grading SL or invalidated surfaces a "why?" editor
inline in the journal row; saving re-posts under the trade's stable `closedAt`
key, so refining a reason **updates**, never duplicates (idempotent on
symbol+closed_at, same pattern as ADR-0018's outcome store). Wins are recorded
too (tag-less) — win rates must come from the full record, not just losses.

### 4. "Auto-improve strategy" — what it means, and what was REJECTED
Three honest mechanisms, one explicit refusal:
- **(a) Already covered by ADR-0018:** the CIO's seat-trust weights and blend
  already re-fit from graded outcomes.
- **(b) NEW — lessons feed the CIO's next synthesis.** `LessonsStore.cio_payload()`
  aggregates per-variant win rates + top recurring failure causes + recent
  post-mortem notes, and rides the CIO's synthesis input **beside** the brief
  (`payload["lessons"]`) — never inside it, so the brief stays pure market fact.
  The prompt instructs the model to weigh named mistake patterns but never cite
  lessons as `evidence` or use them to justify levels outside the panel's range.
  An empty digest sends nothing (no noise before any data exists).
- **(c) NEW — stats surface where you decide.** Setup cards show a live
  `nW nL · win%` chip per variant (hidden below 3 graded trades — a win rate
  over 1-2 trades is noise, not a signal); the journal gets a "strategy lessons"
  card with the full per-variant table + top failure causes + recent notes.
- **(d) REJECTED — automatically mutating the ATR multipliers** (the band/stop/
  target constants in `desk/setups.py`) from a handful of graded outcomes. This
  is the dishonest half of "auto-improve": silent self-tuning on small samples
  is an overfit factory that compounds quietly, exactly the failure mode
  ADR-0018's blend-freeze-below-10 and clamp rules exist to prevent elsewhere.
  Numbers change via a new ADR (informed by the stats this ADR now surfaces) or
  via P5 backtesting — never silently at runtime.

## Consequences
- The setup shelf went from "sample scaffold" to "real, gradeable, learning
  surface" without inventing a new subsystem — it reuses the existing brief,
  the existing P3 grading endpoint, and the existing CIO synthesis seam.
- 13 new golden tests (160 total green): hand-computed ATR-rule levels for
  long/short/mixed bias, missing-ATR isolation, lesson aggregation (hit
  scoring, win-rate-hidden-below-3, idempotent re-post), and confirmation the
  CIO payload includes/excludes the lessons block correctly.
- Live-verified end-to-end on real data: `/setups/LINKUSDT` returned a real
  directional bias with exact hand-matching levels; saved all 4 variants from
  the live UI; grading SL opened the post-mortem editor; tags + note posted to
  `/lessons` and aggregated correctly; the journal's strategy-lessons card and
  the setup cards' win-rate chips went LIVE.
- Known v1 limits, accepted: options variant needs held-position tracking
  before it can be more than informational; the ATR-rule table is intentionally
  simple (no OB/swing-aware entry snapping yet — a later structure-aware pass).

# ADR-0020 — Walk-forward backtesting + Monte Carlo on setup variants

**Status:** accepted · 2026-07-11 · **authored on Fable** (backtest math is money-risk:
its numbers will inform whether the ATR multiplier table ever changes — ADR-0019 §4
named "P5 backtesting" as one of only two sanctioned evidence sources for that)
**Implements:** the P5 "vectorbt backtesting + Monte Carlo on journaled setups" item —
with one deliberate deviation from the master plan's named library, recorded here.

## Context
The setup shelf's six variants became real, deterministic ATR-rule scaffolds in
ADR-0019, and the journal now grades them live — but live grading accumulates
evidence at the speed the user trades. A backtest replays the same rules over months
of history in minutes, answering "does this variant have an edge at all, and how
sure can we be?" before real money leans on it.

## Decisions

### 1. REJECTED: vectorbt. The backtest replays the PRODUCTION code path.
The master plan (PART D, P5) named vectorbt. Building on it would require
re-expressing the setup logic as vectorized entry/exit signal arrays — **a parallel
reimplementation of the strategy**. Two implementations of the same rules drift, and
then the backtest validates a strategy we don't actually run — the exact
plausible-but-wrong failure mode this project's invariants exist to prevent.
Instead the backtest calls the same functions the live shelf calls:
`analyze_timeframe` (structure/trend/ATR) → `compute_alignment` → `build_variants`
(desk/setups.py, untouched) → an exit walk with `grading.py`'s documented
conservative semantics. Correctness by construction; **zero new dependencies** —
this backend is deliberately pure Python (§F6), so the Monte Carlo uses seeded
`random.Random` (spec-guaranteed identical across platforms — strictly better
for golden tests than a compiled RNG). vectorbt remains a candidate for later
*parameter-sweep* work, which is genuinely vectorizable — see §6.

### 2. Walk-forward simulation (quant/backtest.py — pure, no I/O)
- **Decision cadence: every closed 1h bar** — models "the shelf refreshes hourly."
  Structural, not tunable: changing it changes what is being tested.
- **No lookahead, ever:** a decision at time T sees only candles with
  `close_time ≤ T`, sliced to the same 200-bar window the live composer fetches.
  (Live sees a *forming* bar; the backtest is strictly the more conservative side.)
- **Lean brief:** only 15m/1h/4h are composed — alignment uses exactly those three
  (ADR-0007, unchanged) and every *gradeable* variant anchors on one of them.
  5m/1d, derivatives, sentiment, daily levels are omitted; none of them are inputs
  to `build_variants` for the four directional variants (a parity test asserts
  lean ≡ full on identical candles). Grid/options are not gradeable and sit out.
- **Order model (conservative by rule):** at each decision, any unfilled order is
  cancelled and — if flat and the variant is tradeable — a limit is placed at the
  **worse band edge** (long: `entry_high`; short: `entry_low`). Fills happen at the
  limit price exactly, never better (a gap through the level is not credited).
- **Fill-bar rule:** the bar that fills the entry may still stop the trade out
  (worst case is honored) but may NOT take profit (best case cannot be proven from
  OHLC) — strictly conservative, hand-verifiable.
- **Exit walk on 15m bars:** first touch of TP1 → win; first touch of stop → loss;
  a bar touching BOTH → **stop-first** (grading.py's documented fallback; the live
  grader drills to 1m, a 90-day backtest cannot, so the conservative default IS the
  rule here). Exits fill at the level exactly; slippage is priced separately.
- **One position per variant at a time** — models a trader following the shelf, and
  prevents a single cadence from pyramiding into an unrealistic stack of overlapping
  entries. Trades still open when data ends are **excluded from stats and counted**
  (`n_open_excluded` — silence would overstate certainty).

### 3. Costs are charged, in config (config/backtest.yaml — invariant 6)
Per-side fee bps by venue (PERP 5 · MARGIN 10 · SPOT 10 — Binance taker tiers) plus
flat slippage bps per side (2). Cost drag is converted into R
(`(entry + exit) × per_side_frac / risk`) and subtracted: **every reported R is
net R.** A backtest that ignores costs flatters exactly the highest-frequency
variant (scalp) that costs hurt most.

### 4. Monte Carlo bootstrap (the "is this edge luck?" layer)
Per variant with **≥ 10 closed trades** (below that: skipped with a stated reason —
same freeze-below-N honesty as ADR-0018): resample the net-R sequence with
replacement, 2000 iterations, **seeded RNG (seed 7, in config, reported in the
output)** so runs are reproducible and golden-testable. Published: total-R
percentiles (p5/p25/p50/p75/p95), max-drawdown percentiles (p50/p95), and
**prob_loss** — the share of resampled histories ending ≤ 0. That last number is
the honest headline: a variant can show a positive total R and still carry
prob_loss ≈ 0.4 on a small sample.

### 5. Surface
`POST /backtest/{symbol}?days=` (crypto only — the free forex tier's 800 req/day
cannot feed a backtest; 30 default / 90 max, warmup fetched on top) starts a
background job (one at a time, 409 if busy — CPU-bound work runs off the event
loop via a thread). `GET /backtest/status` polls progress; `GET /backtest/{symbol}`
returns the last stored report (file-backed, gitignored). Every report embeds its
**assumptions block** (fill model, both-touch rule, fees, seed…) — NFR-7 applies to
simulations too: a number nobody can trace is a number nobody should trust.
Frontend: a Backtest card on the journal page (results table + equity curve + MC
intervals + the assumptions, bilingual), provenance kind `engine`.

### 6. Explicit non-goals (v1)
- **No parameter sweeping.** Running 100 multiplier combinations and reporting the
  best is multiple-comparisons overfitting unless done with holdout discipline —
  the same trap ADR-0019 §4 refused at runtime, refused again here at design time.
  v1 backtests the CURRENT table, as published. A sweep with train/test splits is
  future work and its own ADR.
- **No intra-bar path modeling beyond the conservative rules** (no synthetic ticks).
- **No funding-cost modeling for PERP holds** (folded into the flat cost bps for
  now; stated in the assumptions block).

## Consequences
- The ATR multiplier conversation (ADR-0019 §4) now has its sanctioned evidence
  source: per-variant net-R distributions with confidence intervals, instead of
  a handful of live trades.
- All simulation constants (fees, slippage, MC iterations/seed/min-trades) live in
  `config/backtest.yaml` and are pinned by golden tests — changing one is a
  documented money-risk change, not a silent edit.
- Known gap, accepted: results describe the last N days' regime; they do not
  promise the next N. The report says so in `notes`.

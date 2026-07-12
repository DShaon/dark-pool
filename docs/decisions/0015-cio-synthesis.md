# ADR-0015 — CIO synthesis: divergence rules, level guardrails, deterministic floor

**Status:** accepted · 2026-07-10 · **authored on Fable** (§F5 money-risk pass)
**Implements:** §B5 consensus engine · ADR-0006 (headless CIO mode) · ADR-0007
(confidence formula — unchanged, made concrete here). FR-4 scope note: v1 emits
ONE primary intraday plan; the setup-variant fan is a later pass.

## Context
The panel (ADR-0005) produces up to four evidence-locked reads. Turning them into
one accountable TradePlan requires judgment calls that lose money quietly if made
sloppily: what counts as consensus, which numbers the synthesizer may publish, what
confidence means, and what happens when models fail. These are settled here, once.

## Decisions

### 1. Divergence detector (`desk/divergence.py`, pure code)
Signals: direction votes (conviction-weighted) · entry clustering within **1.0 ×
ATR(1h→15m→4h)** (stops 1.5× — mandates trail differently) · conviction spread.
Rules, ordered: **(a)** zero directional votes → plurality `no_trade`, **aligned**
(the desk standing aside IS consensus) — unless < 2 survivors, which is never
consensus (→ split). **(b)** long AND short present → plurality = higher
conviction-weighted side (tie → `no_trade`); **contested** if both sides carry a
conviction ≥ 3 voice, else **split**. **(c)** one direction only → **aligned** iff
≥ 2 seats voted it, ≤ 1 abstention (a no_trade risk officer is mandate-expected),
entries don't *positively* scatter, and agreeing-seat conviction spread ≤ 2; else
split. Missing ATR / < 2 zoned entries → clustering `None`, non-blocking: missing
data must never manufacture dissent. Every classification appends human-readable
`notes` — the audit trail.

### 2. Calibrated confidence (`desk/confidence.py`) — ADR-0007 made concrete
`0.5 × checklist + 0.5 × agreement`, clamped **[0.05, 0.95]** (never certain).
Checklist components (0–1, averaged; **missing data is EXCLUDED, never
zero-filled**): `mtf_alignment` = alignment.score signed by direction;
`structure` = anchor-TF event map (BOS-with 1.0 · CHoCH-with 0.7 · trend-match
0.75 / range 0.5 / oppose 0.25 · CHoCH-against 0.25 · BOS-against 0.0);
`derivatives` = crowding vs the plan (crowded same side = 0.0, opposite extreme =
1.0, neutral 0.7); `liquidity_room` = distance to nearest intact opposing level,
0 at ≤ 0.25 ATR → 1 at ≥ 2 ATR. A `no_trade` plan uses one component:
`mixed_market = 1 − |alignment.score|`. Agreement = 0.5 × state base (aligned
1.0 / split 0.5 / contested 0.2) + 0.5 × conviction-weighted share voting the
plan's direction (abstainers dilute — an uneasy risk officer SHOULD lower it).
Per-seat model_scores weighting is the P3-recalibration seam: all seats weigh 1.0
until the journal has graded outcomes. Raw LLM self-confidence is never an input.

### 3. CIO synthesis guardrails (`desk/cio.py`) — code, not prompt hope
* **Direction asymmetry:** the CIO may take the plurality or STAND ASIDE; it may
  never counter-trade the panel (vetoing out is safe, vetoing in is not).
* **Level provenance:** entry/stop/targets must sit within the agreeing analysts'
  published span **± 0.5 ATR**; geometry enforced (long: stop below zone, targets
  above; short mirrored). The CIO refines the panel's numbers, never invents.
* **R:R recomputed in code** from final levels; model arithmetic never trusted.
  Confidence and sizing computed in code; the model isn't asked for them.
* **Evidence lock** identical to analysts (dot-paths must resolve in the brief).
* Failure ladder: one corrective retry naming the exact violation → then the
  **deterministic floor**: adopt the strongest agreeing seat's coherent levels
  wholesale, stop widened to the panel's most conservative (fixed risk → smallest
  size), rr/sizing/confidence recomputed; if even those levels are geometrically
  incoherent → STAND ASIDE. A ≥ 2-survivor desk therefore ALWAYS yields a plan,
  with `synthesizer="deterministic_fallback"` disclosed.
* **≥ 2 survivors required** for any plan (one voice is not a desk); fewer →
  degraded response, plan null, honest reason.

### 4. Sizing (`desk/sizing.py`)
`position_pct = risk_pct / stop_distance_pct × 100`, Decimal math, capped at
`max_position_pct` (cap reported, never silent). `risk_pct_per_trade` (default
1%) and `max_position_pct` (default 100 = 1× notional) live in Settings/env.
Advisory percentages only (invariant 5).

### 5. Plumbing
`/plan/{symbol}`: rides the desk's 120s cache — the plan cache is keyed by the
desk run's timestamp, so a fresh desk run invalidates it automatically and
`?force` re-synthesizes WITHOUT re-running the panel (no double model spend).
Headless CIO model is `models.yaml: cio` (any OpenAI-dialect model — safe for a
mid-tier seat *because* of the guardrails). The interactive Fable-over-MCP CIO
(ADR-0006) is untouched and remains the premium path.

## Consequences
- Every published number traces: levels → named analyst seats (`built_from`),
  confidence → recorded component breakdown, consensus → notes (NFR-7).
- 25 golden-fixture tests hand-verify the formulas; changing a rule here is a
  money-risk change requiring a new ADR, not a test edit.
- Free-tier field notes (2026-07-10, measured): groq 70B = 100k tokens/day
  (~8 desk runs; the brief is ~10k tokens/call) · groq 8B = 6k TPM, one brief
  never fits · gemini per-model daily quotas · openrouter :free 429s under load.
  Live end-to-end synthesis is quota-gated to ~daily budget; the degradation
  ladder (drop → degrade → deterministic floor) was verified live at every rung.

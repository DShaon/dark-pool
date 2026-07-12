# ADR-0022 — Structure-aware setup variants (entries on real zones)

**Status:** accepted · 2026-07-11 · **authored on Fable** (this changes the
actual entry/stop/target selection — the sharpest money-math in the shelf)
**Reworks:** ADR-0019 §1's directional variant pricing. The gates (mixed-bias
stand-aside, missing-ATR isolation), the grid/options variants, and the
multiplier table itself are all UNCHANGED.

## Context
The owner — the trader this desk serves — reviewed the setup cards and said
they "seem like kidding." He was right, and it was not a style complaint: the
ADR-0019 variants priced everything as `close ± k×ATR`, while the Market Brief
already computed real structure per timeframe (unmitigated order blocks, FVGs,
equal-high/low liquidity clusters, BOS/CHoCH events, premium/discount) that
`desk/setups.py` never read — it consumed exactly two fields (`last_close`,
`atr14`) per anchor TF. Separately, the ADR-0020 backtest had already shown
the 5x scalp variant losing to fees with `prob_loss = 1.0` over 90 BTC days —
concrete evidence the raw-ATR entries carry no edge. No professional enters on
"current price minus a percentage"; they enter where structure says the market
must defend.

## Decisions

### 1. Entries anchor on real zones, hunted within a per-style search radius
New pure module `desk/structure_entry.py`. Per directional variant, on its own
anchor TF (scalp→15m, intraday→1h, swing/spot→4h):
- candidate zones = unmitigated `order_blocks + fvgs` on the trade's side that
  offer a genuine **pullback** (zone fully at/below close for longs, at/above
  for shorts) within `search × ATR` of price. The `search` constants are NEW
  per-style patience horizons in the rule table: **scalp 1.0 · intraday 1.5 ·
  swing 2.5 · spot 3.0** (anchor-TF ATR units).
  **The design draft reused the fallback `band` constants (0.15–0.5) as the
  radius; live measurement REJECTED that** — on a real BTC brief, actual
  unmitigated zones sat 0.37–8.5 ATR behind price while the band radii were
  0.15–0.5 ATR, so the structure path would almost never have fired and the
  rework would have been decorative. Band width (how wide the fallback entry
  band is) and search depth (how far a style hunts for its zone) measure
  different things; conflating them was the draft's error, caught in
  verification. (**Also rejected:** no radius at all / nearest-zone-anywhere —
  a spot card anchored 8% below price is technically honest but stale on
  arrival, and the hourly refresh would pin capital to last week's level.)
- nearest zone wins; exact-distance ties prefer order blocks over FVGs
  (committed orders over inefficiency gaps);
- zones **straddling the current price are excluded on purpose**: a limit at
  the near edge would sit on the wrong side of the market and "fill"
  instantly at a worse-than-market price — a dishonest simulated entry;
- the entry band IS the zone (`entry_low=bottom`, `entry_high=top`). This
  keeps ADR-0020 backtest parity exact with zero backtest code changes: its
  worse-edge fill rule (long fills at `entry_high`) now means "filled at the
  zone's first-touched edge, never deep inside" — the conservative reading.

### 2. Stops sit beyond the genuine invalidation — the FARTHER of two
`stop = zone far edge ∓ 0.10×ATR buffer`, widened to beyond the most recent
opposing swing when that swing is strictly farther. Rationale: if either the
zone or the swing still holds, the thesis is not yet broken — the nearer stop
would exit on a wick that proves nothing. Strictly-farther is also the guard:
a noisy swing on the wrong side of price can never tighten or invalidate the
stop. Same conservative-by-rule posture as ADR-0020's fill/both-touch rules.
`STOP_BUFFER_ATR = 0.10` — small against every style's stop multiple
(0.6–2.0): clears the exact level without changing the style's risk character.

### 3. Targets are real liquidity, subject to a 1.2R floor
TP candidates, nearest first, equal levels preferred at equal distance:
intact `EQH` (long) / `EQL` (short) beyond entry, then opposing unmitigated
zones' **near** edges (never assume price punches through). A structural TP1
must pay `≥ MIN_RR_FLOOR = 1.2` against the REAL stop — set deliberately
below the smallest published ratio (1.5) so it rejects real-but-uneconomic
liquidity without just restating the table. If none qualifies, BOTH targets
come from the published ratio table **rescaled onto the new stop distance**
(`tp = entry ± (tp_mult/stop_mult)×R`), so published R:R ratios hold exactly
even in fallback — new entry with old-stop-distance targets would be
incoherent. Structural targets may be one or two (a second only when a
farther qualifying candidate exists) — one honest target beats a padded pair.

### 4. Confluence is discrete, auditable points — never a blended score
(**Rejected alternative:** a continuous weighted quality score — opaque, not
hand-checkable, violates the traceability standard (NFR-7) that every
published number traces to a named fact.) One point each, with the fired
reason published on the variant (`confluence: list[str]`):
structure-anchored entry · zone sits on an intact same-side EQL/EQH cluster
(±0.15%) · premium/discount favors the direction · zone formed within the
last 20 anchor-TF candles (`FRESHNESS_BARS=20` — a designed judgment call,
stated, not derived) · a same-direction BOS/CHoCH at/after the zone formed.
Tiers: **≥3 high · 2 medium · ≤1 low.** ATR-fallback entries have no zone, so
three of the five points cannot fire — they cap at **medium**: an honest
fallback is never allowed to claim top quality.

### 5. Contract changes are additive; the fallback is a pinned regression
`SetupVariant` gains `entry_kind` ("structure"|"atr_fallback"),
`quality` ("high"|"medium"|"low"|None — None on grid/options/untradeable) and
`confluence` (list of fired reasons), all defaulted — the backtest reads only
the unchanged level fields (verified: `_VariantSim.on_decision`), the
frontend ignores unknown fields until a follow-up surfaces them. The
ATR-fallback path is byte-identical to ADR-0019: the original golden numbers
now serve as the regression pin (`test_long_bias_fallback_golden_levels`).

### 6. Non-goals (v1, stated)
No `daily_levels` (PDH/PDL) in selection — the ADR-0020 lean brief omits them,
and live/backtest parity outranks one more confluence source (future work,
with a backtest-side change). No cross-timeframe confluence (same-TF only).
Grid/options untouched. Frontend display of quality/confluence is a follow-up.

## Consequences
- 14 golden tests (9 new structure cases + the pinned fallback regressions;
  204 total green): full-confluence long (all 5 points, exact stop 98.90 via
  the farther-swing rule, EQH TP1 at 1.67R, opposing-zone TP2 at 3.0R),
  mirrored short with rescaled-fallback targets, 1.2R floor rejection,
  single-target case, zone-vs-swing stop preference, straddling-zone
  exclusion, search-radius boundary (2.90 in / 3.10 out at intraday's 3.00),
  tier boundaries 3/2/1, fallback capped at medium.
- Accepted gap: the ADR-0020 synthetic zigzag fixtures almost certainly never
  form a detectable zone, so the backtest's own tests exercise the fallback
  path only — they exist to prove no-lookahead/lean-parity mechanics, and
  test_setups.py owns the selection math. A hand-built OB candle series for
  an end-to-end structure-path backtest test is flagged future work.
- The real-history backtest re-run (evidence per ADR-0019 §4(d)) is recorded
  in STATUS.md alongside this change; ADR-0020's assumptions block already
  covers the simulation rules that apply unchanged to the new entries.

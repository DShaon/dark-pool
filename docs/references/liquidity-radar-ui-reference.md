# Reference capture — "Liquidity Radar" (waqarzaka.net)

**Purpose:** internal design/feature reference only — captured from the owner's own
paid account via a screen recording he provided, analyzed by extracting still frames
(ffmpeg) and sampling real pixel colors (PIL) rather than eyeballing. Not a spec to
clone verbatim — a menu of ideas and a grounded palette to draw from when/if the
owner asks for specific pieces to be built into DARKPOOL.

**Source:** `https://www.waqarzaka.net/liquidity-radar` · symbol shown: BTCUSDT PERP ·
venue: Binance Futures · capture date: 2026-07-10 · method: 38s screen recording →
51 frames sampled every 0.75s + 2 full-resolution (1920×804) frames for pixel sampling.

---

## 1. Product concept

A single-symbol, real-time **order-flow X-ray** — not a chart-first tool. No candle
chart appears anywhere in the recording. Instead: live order book, a scrolling
order-flow event log, and several derived "manipulation/liquidity" signals
(spoofing probability, sweep detection, squeeze risk), refreshed continuously —
price, funding, OI, and every gauge visibly tick between frames.

## 2. Structure — one page, 4 tabs

Top nav, flat segmented buttons (**no sliding-pill animation** — active tab just
swaps to a lighter background instantly, unlike DARKPOOL's `SegTabs`):

`RADAR` · `ADVANCED` · `ORDER EVENTS` · `ALERTS (n)`

Header bar, left to right: logo (orange rounded-square "B" mark) + "LIQUIDITY RADAR"
wordmark + `BTCUSDT PERP · BINANCE FUTURES` subtitle → tabs (centered) → a live stat
strip on the right: green pulsing `LIVE` dot, `OI`, `FR` (funding, colored by sign),
`SPR` (spread), `TRD`, ticking UTC clock.

---

## 3. Pixel-verified color palette

Sampled directly from two lossless PNG frames via PIL (not estimated). Fill colors
(borders, dots, icons, large areas) are high-confidence — box-searched for the purest
pixel in a small region. Small anti-aliased text glyphs are lower-confidence
(noted below); at 1920×804 a single character stroke is 1–2px, so exact hex on tiny
text is approximate.

| Role | Hex | RGB | Confidence | Notes |
|---|---|---|---|---|
| Page background | `#0b0b15` | 11,11,21 | high | near-black, faint blue-violet tint |
| Header/panel bg | `#101220` | 16,18,32 | high | marginally lighter than page bg |
| Card hairline border | `#0e0e17` | 14,14,23 | medium | extremely subtle — cards read as "one shade of black" more than DARKPOOL's visible hairlines |
| Bull/buy/green accent | `#56f6a0`–`#71f39e` | ~86-113,220-246,136-160 | high | one consistent bright mint-green family used for: bid prices, CVD line, LIVE dot, "weak bullish sweep" alert border |
| Bear/sell red (order book) | `#d21822` | 210,24,34 | high | strong, fully-saturated red — ask prices |
| Bear/alert rose-red | `#e03b63` | 224,59,99 | high | a *different*, more magenta-leaning red used for alert-log left borders (bearish sweep) — they use two distinct reds for two distinct contexts |
| Warning/orange (spoofing, targets) | `#e3a03f`–`#df8e3d` | ~223-227,142-160,61-63 | high | logo icon + "possible spoofing" alert border + likely-target tag color |
| Bell/gold icon | `#eacf65` | 234,207,101 | high | **notably close to DARKPOOL's own `--ai-gold` (#E8C574)** — worth knowing if we ever reuse gold-adjacent tones |
| Teal/cyan accent | `#6ae0d4` | 106,224,212 | high | checkbox-checked fill; also the radar/spider-chart stroke color in the earlier frame pass |
| Info-icon blue-lavender | `#7c94e0`–`#93ccc9` | varies | low-medium | the small `(?)` tooltip triggers next to card titles; exact hue uncertain at this res |
| Alert-card title text | `#e8e4fc` (≈ off-white) | 232,228,252 | low | anti-aliased against dark bg; reads as near-white with a faint lavender cast, not pure `#fff` |
| Chat widget indigo (3rd-party) | `#4141e6` | 65,65,230 | high | "Need Help?" chip — Intercom-style widget, not site's own design system |
| Chat bubble purple (3rd-party) | `#7f4de5` | 127,77,229 | high | separate bottom-left chat widget (different vendor) — also not part of the core design |

**Read:** the palette is genuinely close in spirit to DARKPOOL's obsidian + teal/red
semantics — but they use **green/red/orange for everything**, including the
"AI-ish" detection scores (spoofing %, sweep confidence), with no separate color
reserved for "this is a judgment call, not a fact." DARKPOOL's gold-only-for-AI rule
(ADR-0010) is a real differentiator, not something to give up if any of these features
get built.

## 4. Layout observations

- Cards: small rounded corners (~8–10px), 1px near-invisible hairline border, **no drop
  shadow** — consistent with DARKPOOL's own "no shadows" rule.
- Numbers are tabular/monospaced throughout (prices, sizes, scores) — same convention
  DARKPOOL already follows.
- Labels are small, uppercase, letter-tracked — again matches DARKPOOL's `micro-label`
  convention already in place.
- Grid: a 3-up row (Liquidity Magnet / Likely Target / Market Strength), then mixed
  2-up rows for the rest; right rail is a fixed-width column (radar chart, spoofing,
  funding/OI) beside a wider left column.
- Two third-party support-chat widgets floating bottom-left and bottom-right — generic
  SaaS boilerplate, not a UI idea worth carrying over.

## 5. Motion & interaction (inferred from frame deltas — I sampled stills, not real
   playback, so treat timing/easing as approximate)

- Numbers/gauges update live in place (no obvious transition animation, they just
  jump to the new value each tick).
- Order-book rows visibly reflow every ~1s as depth changes.
- The "possible spoofing" probability renders as a small scrolling bar-strip —
  reads like a rolling history, not a single static bar.
- Alert Log: new alerts appear to **prepend to the top**, pushing older ones down;
  the tab's badge count climbed live during the recording (1 → 5).
- Tab switch = instant background swap, not a sliding indicator.
- Colored **left-border strip by type** is the recurring "at-a-glance" motif — used on
  both the Active Spoof Watch cards and every Alert Log entry. DARKPOOL already does
  this exact pattern (WatchlistRail active tile, CIOVerdict) — worth extending
  consistently to Desk Tape / scanner feed entries.

---

## 6. Trade-related concepts observed — mark what you want built later

Not yet decided to build any of these — flagging them here so you can check off
which ones matter for DARKPOOL. Each line notes roughly what real data it would need.

- [ ] **Order book depth panel** (asks/bids, live, size + $ depth per level) —
      Binance's public `/depth` stream; keyless, adapter-friendly (invariant 1).
      Most legitimate/highest-value pickup — real exchange data, not a "derived signal."
- [ ] **Active walls / large resting orders** table (≥N BTC within X% of price) —
      derived from the same depth stream, no new data source.
- [ ] **Liquidation map** (estimated forced-close levels) — Binance's public
      `forceOrder` stream; was still "Loading…" in their own UI during the whole clip,
      so it may be a slow/expensive computation on their end too.
- [ ] **CVD (cumulative volume delta)** chart — derivable from trade-stream buy/sell
      volume; would sit naturally next to DARKPOOL's existing indicators.
- [ ] **Volume profile w/ point of control** — standard TA construct, computable from
      the candles DARKPOOL already fetches.
- [ ] **Liquidity sweep detection + confidence score** (e.g. "Strong Bullish Sweep,
      65/100") — conceptually close to what DARKPOOL's structure/liquidity engine
      already flags (equal-highs/lows sweeps); could likely be expressed with the
      existing engine rather than a new subsystem.
- [ ] **"Likely target" / liquidity magnet** ($ level + score + type tag like "Stop
      Hunt Zone") — a scored version of DARKPOOL's existing PDH/PDL/PWH/PWL +
      order-block levels; mostly a presentation/scoring layer on data we already have.
- [ ] **Market Strength gauge** (0–100 circular dial, WEAK/MODERATE/STRONG) — reads
      like a rebrand of a trend-strength composite; DARKPOOL's alignment score is a
      conceptual cousin already.
- [ ] **Trap & Squeeze Risk meters** (Bull Trap / Bear Trap / Short Squeeze / Long
      Squeeze, 0–100 each) — would need a defined formula; not obviously backed by a
      single clean data source, more of a derived heuristic.
- [ ] **Possible Spoofing detector** (probability score + the specific canceled order)
      — needs raw order-add/cancel event tracking from the depth stream at high
      frequency; the most technically demanding item here.
- [ ] **Large Order Events live log** (APPEAR/INCREASE/PARTIAL_FILL/FULL_FILL/CANCEL
      feed) — same raw depth-diff tracking as spoofing detection; a shared
      prerequisite for both.
- [ ] **Alert Settings with inline thresholds** (checkboxes showing "≥55", "≥70" etc.
      right in the label) — a UI pattern more than a data feature; cheap to adopt if
      any of the above land.
- [ ] **Market Bias bar** (single gradient bar, live BUY%/SELL% split) — could be a
      simple restyle of existing long/short-leaning signals (funding + L/S ratio +
      alignment) into one bar.

## 7. Explicitly not worth carrying over

- The two third-party chat widgets (Intercom-style + a second bubble) — generic,
  unrelated to trading UI.
- Their single shared red/green/orange system for both "facts" and "AI-ish scores" —
  DARKPOOL's gold-reserved-for-judgment rule is a deliberate improvement, not
  something to match.

---

*Temporary frames used for this capture were deleted from scratch space after
analysis; nothing from the source account is stored in this repo beyond the
descriptions and pixel values above.*

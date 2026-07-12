# ADR-0017 — Chart plan overlay, AI scenario path, signal jump-to-chart, source badges

**Status:** accepted · 2026-07-10 · **authored on Fable** (the scenario path is an
LLM boundary touching invariant 7; its rules are settled here — the build is Opus work)

## Context
Owner requests: (a) chart buttons that draw a chosen plan's entry/SL/TP plus the
"future move"; (b) a switch to an "AI-predicted price path"; (c) the Signals strip
should list where liquidity is waiting and clicking should show it on the chart;
(d) FVG/OB toggle buttons + a refresh button; (e) a ⓘ source badge on every card
showing where its data comes from. Invariant 7 forbids AI-invented numbers — an AI
freehand price forecast is banned. The compromise below was accepted by the owner.

## Decisions

### 1. Plan overlay (deterministic — no AI)
A chart toolbar button with a per-click source picker: **Quick Read / CIO plan /
any setup variant**. Drawing (lightweight-charts price lines + a future-timestamped
line series): entry zone box (hi/teal), SL line (bear), TP1–3 lines (bull, R:R
labels), and the **planned path** — a code-drawn polyline `entry_mid → TP1 → TP2`
spread over the next ~12 future bars. Every value comes verbatim from the chosen
plan object. Direction-aware; no plan available → the picker entry is disabled with
the reason.

### 2. AI scenario path (the toggle) — sequencing, never pricing
The "AI-predicted path" NEVER invents a price. Contract:
- New endpoint `GET /scenario/{symbol}` → `ScenarioPath`:
  `waypoints: [{level_ref, label?}] (2–6)` + `narrative ≤ 60 words (EN+BN)` +
  `evidence` (standard lock). `level_ref` is a dot-path that must resolve to an
  EXISTING price field in the brief or active plan (entry_zone.low, targets[1].price,
  daily_levels[0].price, an OB top…). Unresolvable ref → one corrective retry →
  toggle shows "unavailable". Same one-retry-then-drop as every LLM boundary.
- Code resolves each ref to its real price, assigns evenly-spaced FUTURE bar offsets,
  and draws a **dashed GOLD** polyline (AI-judgment color, C-rules) with waypoint
  markers. Badge, always visible while on: **"AI scenario · দৃশ্যকল্প — sequence
  opinion, not a forecast."** It is never rendered as candles.
- So: the AI's only degree of freedom is WHICH real levels, in WHAT order — the
  invariant-7-compliant meaning of "predicted path".

### 3. Signals → liquidity map (deterministic)
The Signal Readout gains a "liquidity waiting" list: every **intact** daily/equal
level (PDH/PDL/PWH/PWL/EQH/EQL) with side and distance in ATR from last close —
data already in the brief, zero new computation. Clicking a row highlights that
level on the chart (temporary bright price line + flash, per C-motion rules).

### 4. Toolbar toggles
FVG and OB buttons draw the brief's zone rectangles for the active timeframe
(closes the long-deferred "chart zone rectangles" item); a refresh button forces
klines + brief refetch. All overlays are client-side draws over data already
fetched — no new upstream load.

### 5. Source badges (ⓘ) — provenance registry
A small `SourceBadge` on EVERY data-bearing card/section. Content comes from one
frontend registry (single file) mapping surface → provenance text, three kinds:
- **Vendor:** e.g. "Binance spot REST · 45s poll + live WebSocket relay" ·
  "Twelve Data REST (forex) · 60s poll, no volume" · "alternative.me Fear & Greed".
- **Deterministic:** "Computed by the quant engine from Binance candles — swings,
  BOS/CHoCH, OB/FVG, RSI/EMA/ATR. No AI involved."
- **AI:** dynamic — names the actual `model_id`/`synthesizer` from the payload +
  "evidence-locked against the Market Brief; numbers guard-railed in code."
  AI-sourced cards state it explicitly; the gold color already signals it.
Bilingual (EN + short Bangla line), rendered via the existing Term-style portal
tooltip. Every new surface MUST register a provenance entry (checklist item).

## Consequences
The owner can verify any number's origin in one click; "predicted" visuals stay
honest (sequence opinion over real levels, loudly labeled); liquidity targets and
zones become visible on the chart without new upstream cost.

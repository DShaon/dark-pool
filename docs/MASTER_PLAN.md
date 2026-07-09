# AI Trading Intelligence Desk — Master Plan
### Codename: **DARKPOOL** · Authored end-to-end by Claude Fable 5

> Greenfield project at `E:\AI Trade` (currently empty). No code until this plan is approved.
> This document is the single source of truth: SRS → Architecture → Design → Roadmap →
> Fable Rails. It is written so that **any executing model (Opus 4.8 / Sonnet 5) builds at
> Fable-designed quality** — every hard decision is made here, once, and encoded as rules,
> schemas, prompts, and checklists (PART F). Executing models build; they do not re-decide.

---

## 0. Context

The user is shifting his career toward trading — crypto (full Binance ecosystem) first,
forex second. He wants an **institutional-grade AI trading intelligence platform**: not a
signal bot, but a desk — real-time professional data, a panel of AI analysts that genuinely
disagree by design, and Claude acting as **Chief Investment Officer** issuing one
high-conviction, fully-reasoned, risk-managed trade plan per asset. Decision quality is the
product; risk is managed intelligently, never preached.

### Locked decisions (from research + user Q&A — do not reopen; see ADRs, §F2)
| Decision | Choice |
|---|---|
| First asset class | **Crypto (Binance)**, forex in Phase 4 |
| Primary timeframe | **Intraday/day trading** first; all setup variants still generated |
| Stack | **Python 3.12 + FastAPI** backend · **Next.js 15 + TypeScript** frontend |
| Deployment | Cloud: **Oracle Always-Free ARM VM** (24/7 backend) + **Vercel** (frontend) + **Supabase** Postgres + **Upstash** Redis — $0 during build |
| Budget | **Bootstrap $0–50/mo**, free-first everywhere |
| Execution | **Advisory only in v1** (read-only/no keys); `Broker` abstraction stubbed now → approval-gated execution later ("coming soon") |
| Users | **Single-user** now; clean seams for multi-user later |
| Monitoring | On-demand analysis + background watchlist scanning, with a **Manual/Active mode toggle** |
| CIO model | **Fable 5 premium interactive CIO** via Claude Code + MCP (subscription-powered); **Opus 4.8 fallback**; headless synthesizer = any API model via config |

### Reality anchors (agreed framing)
- "100 traders debating" = mandate-differentiated LLM analysts + programmatic divergence
  detection + Claude synthesis. Powerful, but orchestrated API calls — cost/latency scale
  with model count, hence two tiers: **Quick Read** (1 model, seconds, ~$0) and **Full
  Desk** (panel + CIO, ~10–40s, ~$0.02–0.10/run on the cheap roster).
- **"Insider activity" feeds do not legally exist for retail.** What is real and legal:
  on-chain whale tracking (Arkham free tier), COT reports, ETF flows (Farside/SoSoValue).
  The system labels these truthfully.
- X/Twitter API is economically unviable post-2026 pricing; sentiment comes from Reddit
  (free tier), Telegram Bot API, GDELT news tone (free, commercial-safe), Fear & Greed.
- TradingView sells no data API — we use its free **Lightweight Charts** library for
  rendering and Binance et al. for data. No ToS-risk scrapers, ever.

---

# PART A — SOFTWARE REQUIREMENTS SPECIFICATION

## A1. Purpose & scope
For any supported asset (e.g. `BTCUSDT`), produce an institutional-grade, multi-analyst,
fully-reasoned **TradePlan** in seconds; monitor a watchlist and fire smart alerts; journal
every call; grade itself and learn which analysts to trust.

**In scope v1:** Binance spot + USDⓈ-M perpetuals · intraday focus · advisory only ·
mandate-based consensus engine · SMC + TA + derivatives + sentiment + macro context ·
watchlist/alerts · journal/analytics · premium web UI.
**Out of scope v1 (planned):** execution, forex, options/gamma, multi-user, mobile-native,
paid on-chain attribution.

## A2. Constraints
One trader (the owner), moderate trading literacy. Free-tier infra (ARM CPU, 500MB DB,
LLM free-tier daily caps: OpenRouter 50–1000 req/day, Groq ~1k/day, Gemini Flash 1.5k/day).
Binance public data needs **no API key** (6000 wt/min spot, 2400 wt/min futures). Single
developer; Windows dev machine, Linux ARM deploy (see §F6).

## A3. Functional requirements

**FR-1 Data ingestion** — Binance REST+WS (OHLCV 1m–1w, depth, trades, funding, OI,
long/short ratio, liquidation stream); context adapters: alternative.me F&G, DeFiLlama
stablecoins/TVL, FRED macro, GDELT news tone, Finnhub economic calendar. Canonical
normalization; Redis cache with per-source TTL; token-bucket rate limiting + backoff;
WS collectors only for watchlist symbols.

**FR-2 Quant engine (deterministic, pre-LLM)** — computed in Python so models reason over
facts: EMA stack, RSI, MACD, ATR, Bollinger, VWAP, volume profile, swing structure, S/R
clustering; **SMC:** BOS/CHoCH, order blocks, FVGs, liquidity pools (equal highs/lows,
PDH/PDL/PWH/PWL), premium/discount, sweep detection (adapt `smartmoneyconcepts` lib);
**derivatives read:** funding regime, OI-vs-price divergence, L/S skew, liquidation
magnets; **multi-timeframe alignment** across 15m/1h/4h (intraday default) → alignment
score. Output = one compact JSON **Market Brief**, the shared input to every analyst.

**FR-3 Consensus engine ("the Desk")** — see §B5 for full design.
Analysts with **mandates** (Trend / Contrarian / Derivatives / Risk Officer) → programmatic
**divergence detector** → optional red-team pass → **CIO synthesis** (dual-mode: interactive
Fable-via-MCP, or headless API model) → calibrated confidence (§B5). Strict Pydantic
schemas at every boundary; a failing analyst is dropped, never blocks the run. Two cost
tiers: Quick Read (default) and Full Desk (button).

**FR-4 TradePlan output** — direction · entry zone(s) + confirmation conditions · SL ·
TP1–3 with R:R · position-size % (risk-based) · probability + calibrated confidence ·
consensus state · thesis ("why this exists") · failure mode ("why it fails") · alternative
scenario · invalidation level/condition · setup variants: conservative / aggressive /
scalp / intraday / swing / position. Plain language throughout.

**FR-5 Watchlist & alerts** — add/favorite/categorize; **Active mode** (interval scans +
WS triggers) vs **Manual mode** (on-demand only) toggle; alert rules: structure break,
liquidity sweep, funding extreme, OI spike, approach of fresh OB/FVG, F&G extreme;
delivery in-app + browser push (Telegram later).

**FR-6 Journal, grading & AI memory** — every run persisted (inputs, all analyst outputs,
final plan, cost, latency); user logs actual trades + outcomes; auto-grade plans (TP/SL/
invalidated) → per-mandate-seat and per-model accuracy → **model_scores** feed CIO
weighting; analytics: win-rate, avg R, expectancy, calibration curve (Brier), model
leaderboard.

**FR-7 Web UI** — per PART C design language: command-palette asset search → analysis
stage; watchlist rail; Desk Verdict card + Consensus Constellation; interactive chart with
SMC overlays + Depth Fog; multi-timeframe strip; journal & analytics views; settings
(roster, mode, risk %, spend caps).

## A4. Non-functional requirements
- **NFR-1 Performance:** Quick Read < 4s · Full Desk < 40s · cached reads < 300ms · UI
  budget per §C6 (60fps, tick→paint < 50ms, TTI < 2s).
- **NFR-2 Security:** secrets server-side only; read-only or no Binance keys in v1; all
  third-party calls proxied; single-user bearer auth; strict output-schema validation;
  spend caps enforced server-side.
- **NFR-3 Reliability:** graceful degradation — missing source/model = flagged gap, never
  a failed run; retries with backoff; health endpoint; WS auto-reconnect.
- **NFR-4 Cost control:** hard monthly + per-run LLM caps; free models default; Claude
  only at CIO; cache-first; visible spend meter in the status line.
- **NFR-5/6 Maintainability & extensibility:** modular monolith; typed both sides; every
  external thing a plug (§B8); execution/forex/multi-user are designed seams.
- **NFR-7 Explainability:** every number in a TradePlan traces to a Market Brief field or
  a named analyst's cited evidence — enforced by schema (§F4), not by promise.

## A5. Data & model sources (v1 = all free)
| Source | Data | Cost/limits |
|---|---|---|
| Binance REST+WS | OHLCV, depth, funding, OI, L/S, liquidations | Free; 6000/2400 wt/min |
| alternative.me | Fear & Greed | Free; 60 req/min |
| DeFiLlama | stablecoin/TVL flows | Free; effectively unlimited |
| FRED | CPI, rates, GDP series | Free key |
| GDELT | news tone, 15-min updates | Free, commercial-safe |
| Finnhub (free) | economic calendar | 60 calls/min |
| Deribit (P5) | options/IV/Greeks | Free |
| CFTC COT (P4) | positioning, weekly | Free |
**Deferred paid tiers (user's call later):** Coinglass $79–299/mo (cross-exchange
liquidations/OI) · Glassnode $79+/CryptoQuant (on-chain flows) · Nansen/Arkham (whale
labels; Arkham API $999/mo) · Twelve Data $66–191 or Polygon (forex) · TradingEconomics
(quote-only). **DXY:** computed synthetically from the 6 constituent pairs.
**LLMs:** OpenRouter (`:free` + cheap DeepSeek/Qwen), Groq (fast Llama/Qwen), Google AI
Studio (Gemini Flash free), optional local Ollama — all through **LiteLLM**, all config.
Full Desk cost: **~$0.02–0.10/run** cheap roster; ~$0.40–0.50 all-frontier (avoid).

---

# PART B — ARCHITECTURE

## B1. Topology
```
        Browser ── Next.js 15 (Vercel) ── HTTPS/WS ──┐        Claude Code (you + Fable)
                                                      │              │ MCP (stdio/SSE)
   ┌──────────────────────────────────────────────────▼──────────────▼─────────────┐
   │ FastAPI backend — Oracle Always-Free ARM VM (24/7)                             │
   │  adapters/ ─▶ ingestion ─▶ quant engine ─▶ consensus engine ─▶ persistence     │
   │  APScheduler + WS collectors ─▶ alert engine        MCP server (FastMCP)       │
   │  Redis (Upstash): cache, rate limits    Postgres (Supabase): runs/journal/etc. │
   └────────────────────────────────────────────────────────────────────────────────┘
        │ rate-limited outbound                    │ LiteLLM (server-side keys)
   Binance · DeFiLlama · FRED · GDELT · Finnhub   OpenRouter · Groq · Google · Anthropic
```

## B2. Components
**adapters/** one class per source, uniform `DataProvider` interface, own limiter ·
**ingestion** orchestrates + normalizes + caches · **quant** pure functions → Market Brief
(fully unit-testable) · **consensus** mandate prompts + divergence + CIO, all via LiteLLM ·
**alerts** APScheduler jobs + WS triggers, honors mode toggle · **persistence** Postgres
durable / Redis hot · **api** REST + WS for UI, bearer auth · **mcp** FastMCP server
exposing desk tools · **broker** stub interface (paper) — the future execution seam.

## B3. Stack rationale (settled — ADR-0001)
Python owns quant/trading (ccxt, pandas, pandas-ta, smartmoneyconcepts, vectorbt, LiteLLM);
rebuilding these in JS costs months. FastAPI is async — right for many concurrent
data/model calls. Next.js/TS is the best tool for the premium UI and the user's strength.
Two languages, one clean REST/WS contract, typed on both sides.

## B4. Data model (Postgres)
`assets` · `watchlist` · `market_snapshots` (cached briefs) · `analysis_runs` (full I/O of
every desk run + cost) · `trade_plans` · `journal_trades` · `model_scores` (per seat ×
model accuracy + calibration) · `alerts` · `settings`. Bulk candles are **not** stored
(fetched+cached) to respect the 500MB free tier.

## B5. The Consensus Engine (the crown jewel)
```
Market Brief ─┬─▶ TREND analyst        best continuation case      ─┐
              ├─▶ CONTRARIAN           best reversal case           ─┤ AnalystThesis
              ├─▶ DERIVATIVES          funding/OI/liquidation read  ─┤ JSON (§F4)
              └─▶ RISK OFFICER         the case for NO trade        ─┘
                        │
        ┌───────────────▼────────────────────────────┐
        │ Divergence detector (pure code):            │
        │ direction agreement · level clustering      │
        │ (entries/SL within ATR bands) · conviction  │
        │ spread → consensus_state ∈                  │
        │ {aligned, split, contested}                 │
        └───────────────┬────────────────────────────┘
                        ▼
        ┌────────────────────────────────────────────┐
        │ CIO synthesis — dual mode:                  │
        │  • INTERACTIVE: Claude Code (Fable 5) over  │
        │    MCP — reads debate, verifies evidence,   │
        │    acts (save/journal/re-run/backtest)      │
        │  • HEADLESS: any API model via LiteLLM for  │
        │    background runs & alerts                 │
        │ weighs seats by model_scores · resolves     │
        │ conflicts · emits TradePlan                 │
        └───────────────┬────────────────────────────┘
                        ▼
          persist → journal → grade later → update model_scores → recalibrate
```
- **Mandate diversity > model diversity.** Same brief, four different jobs — disagreement
  by construction. Which model fills which seat is `models.yaml` config.
- **Calibrated confidence = 0.5 × deterministic checklist** (MTF alignment + structure
  state + derivatives confirmation + distance-to-liquidity, computed in code) **+ 0.5 ×
  panel agreement** (consensus_state + score-weighted votes). Journal computes Brier
  scores; blend weights recalibrate. Raw LLM self-confidence is never shown.
- **Evidence lock:** every analyst claim must reference Market Brief fields (§F4);
  citations of nonexistent fields are rejected in code. Hallucination dies at the schema.
- **MCP tools:** `get_market_brief(symbol,tf)` · `run_analysis(symbol,tier)` ·
  `get_analyst_debate(run_id)` · `save_trade_plan(...)` · `journal_add(...)` ·
  `get_performance_stats()` · `run_backtest(...)` (P5) · `propose_order(...)` (future,
  approval-gated). This is also the seam where the future execution bot lives: Claude
  proposes → you approve → an MCP tool executes.

## B6. Model tiering (verified mid-2026)
Fable 5 tops finance/trading-reasoning benchmarks and hard coding; it is 2× Opus pricing
($10/$50 per MTok) and on Pro is available up to a share of weekly limits. **Use Fable as
interactive CIO via Claude Code (subscription, not metered) and for money-risk logic while
building; Opus 4.8 is the always-available fallback.** Switching Fable↔Opus breaks
nothing: models are config/menu choices; code and stored data are model-agnostic. Note:
Fable's thinking blocks don't replay to other models mid-conversation — irrelevant here,
every desk run is fresh.

## B7. Security model
No/read-only exchange keys in v1 · all secrets server-side · single-user bearer token ·
every third-party call proxied · schema validation on all model output · server-enforced
spend caps · no execution code paths.

## B8. Pluggability (the standing principle)
**(a) Data:** new source = one adapter class + one `providers.yaml` entry — nothing else
changes. Coinglass/Glassnode/Alpaca/anything drop in identically, whenever chosen.
**(b) Models:** roster + synthesizer in `models.yaml` via LiteLLM (100+ providers incl.
local Ollama) — swap/add models with zero code change.
**(c) CIO:** interactive (MCP/Claude Code) and headless synthesizers are interchangeable;
the future execution layer plugs into the same MCP surface behind explicit approval.

---

# PART C — DESIGN LANGUAGE: **DARKPOOL**

*The market as a living depth-field.* One rule organizes everything: **market data is cool
obsidian monochrome with teal/red semantics; the AI's judgment is always gold.** At a
glance you always know what is fact and what is opinion. Institutional noir — luxury-watch
restraint, zero gamer-RGB, zero generic-AI aesthetic.

## C1. Tokens
```
--bg-abyss:  #07090D   app background        --bull:    #2DD4BF
--bg-panel:  #0D1117   panels                --bear:    #F87171
--bg-raised: #131A23   hover/raised          --warn:    #F5B94A
--line-hair: #1C2532   1px hairlines         --ai-gold: #E8C574  (AI voice ONLY)
--text-hi:   #E9EEF4   --text-mid: #93A0B4   --pulse:   #7DD3FC  (live-data sweep ONLY)
```
**Banned:** purple gradients, glassmorphism, drop shadows, bouncing easings, spinners.

## C2. Typography
UI: **Instrument Sans** (400/500/600). All numerics: **IBM Plex Mono, tabular-nums** —
prices always align. **The Verdict word** ("LONG" / "SHORT" / "STAND ASIDE") is the one
emotional moment: **Instrument Serif Italic, gold, clamp(48–96px)** — a giant italic serif
verdict on obsidian; no trading product looks like this.

## C3. Structure
4px baseline grid, Bloomberg-adjacent density. Panels: 1px hairline, 2px radius
(instrument-like, near-square); elevation = background step + hairline brightening, never
shadow. Shell: left rail watchlist (280px) · center stage chart · right Desk panel (360px)
· top command bar · bottom **status line** (WS latency, per-panel data freshness, monthly
LLM spend meter). `Ctrl+K` command palette is the primary navigation — type `BTCUSDT`
anywhere → full analysis.

## C4. Signature animations (each unique AND functional; all interruptible)
1. **Verdict Reveal** *(~900ms, once per Full Desk run)* — the four mandate chips flare in
   sequence (80ms apart); each fires a 2px light-mote along a bézier into the confidence
   arc; the arc **fills like poured metal** to the calibrated %, hue blended
   bull-teal↔bear-red by probability; the serif verdict word blooms from letter-spacing
   0.3em→0.02em. Click skips; replayable from the run log.
2. **Consensus Constellation** — the four mandates as nodes on a diamond; agreement draws
   solid gold edges, dissent draws dashed dim edges; the glyph breathes ±2% over 4s.
   Aligned/split/contested readable in half a second. Static SVG under reduced-motion.
3. **Depth Fog** — a canvas layer under price rendering liquidation clusters/book density
   as horizontal luminous strata drifting ~1px/s; brightness = density. The market's
   liquidity literally glows beneath the candles.
4. **Pressure Ripple** — each tick emits a 12px radial ripple from the changed digit,
   amplitude ∝ trade size. Replaces vulgar full-cell green/red flashing.
5. **Odometer prices** — digits roll vertically (120ms, transform-only); old digit exits
   upward on an uptick, downward on a downtick — direction is *felt* before it's read.
6. **Scan-line freshness** — new WS data sweeps the panel once with a 1px cyan line
   (300ms). No spinners exist; stale panels dim after 30s of silence instead.
7. **Palette summon** — on Ctrl+K the stage recedes 12px in Z with 4% dim (parallax);
   the palette expands from a hairline into a field (180ms).
8. **Alert bloom** — an amber hairline traces the affected panel's perimeter once, then
   settles into a corner badge. Urgent, never modal.

## C5. Performance contract (the other meaning of "performative")
DOM animates `transform`/`opacity` only; Fog/Ripple/Constellation live on **one** shared
rAF canvas layer; series decimation in a Web Worker. Budgets: **60fps** (frames >16ms log
dev warnings) · WS tick→paint **<50ms** · route TTI **<2s** · Lighthouse ≥90. Global
**Focus Mode** kills all non-essential motion; `prefers-reduced-motion` honored — every
signature has a static equivalent. Libraries: TradingView Lightweight Charts + custom
overlay canvas; Framer Motion for DOM micro-transitions only; no heavy animation libs.

## C6a. Amendments from user reference boards (ADR-0011, 2026-07-06)
User-taste study (5 reference dashboards) folded in: **glow discipline** (live data may
glow — gradient chart fills, bloom on strokes, luminous nodes; chrome never glows);
**Desk Pipeline Map** — the consensus run as a live node graph (Brief → 4 mandate nodes →
divergence → CIO; gold edges = agree, dashed = dissent, red node = risk veto), absorbing
the Constellation as its compact state; **hero tiles** (max one flooded teal/red signal
tile per view, glowing area chart behind numerals); **Desk Tape** (streaming mono event
log, mandate-colored entities); **card radius 12px** (supersedes 2px); **arc dials**
(F&G, amber needle) and **sparkline watchlist tiles**. Purple/blue neon explicitly
rejected — palette discipline and the C5 performance contract remain binding.

## C6. Voice
The desk speaks like a head trader — terse, definite, first-person-plural: *"Asia lows
swept into 4H demand. We want longs only above reclaim of 61,240."* AI text renders gold
or neutral, never bull/bear-colored — judgment never masquerades as data.

---

# PART D — ROADMAP

**P0 — Foundation.** Monorepo (`/backend`, `/frontend`), `CLAUDE.md` + ADRs (§F1–F2),
env/secrets, Supabase+Upstash wired, Binance adapter end-to-end, deploy both tiers, CI
(GitHub Actions, Linux). *Exit:* live URL shows real BTC price served by the backend.

**P1 — Crypto Intraday Advisory MVP (the core loop).** Full ingestion (Binance + F&G +
FRED/GDELT/Finnhub) → quant/SMC engine + golden-fixture tests → Quick Read (1 model) →
DARKPOOL shell: palette search, chart + SMC overlays, TradePlan card → watchlist +
manual journal. *Exit:* search `BTCUSDT` → reasoned intraday plan with every FR-4 field,
numbers traceable to the brief; saved to journal.

**P2 — The Desk.** Mandate analysts via LiteLLM → divergence detector → red-team →
**MCP server + Claude Code interactive CIO (Fable)** + headless synthesizer → Verdict
Reveal + Consensus Constellation UI → cost caps + spend meter. *Exit:* Full Desk run under
cap with ≥3 surviving analysts and a synthesized TradePlan; Claude Code connects over MCP,
reads the debate, issues the final call; a malformed analyst is dropped gracefully.

**P3 — Monitoring, alerts, learning.** Active/Manual toggle → scanner + WS triggers →
alert rules + browser push → outcome grading → model_scores + confidence recalibration →
analytics dashboard (leaderboard, calibration curve). *Exit:* leave it running, receive a
real alert; grade a closed plan; watch a seat's weight change.

**P4 — Forex + macro.** OANDA/Twelve Data adapter (same interface), synthetic DXY, COT,
calendar-aware analysis (pre-news risk flag), correlation engine. *Exit:* `EURUSD` parity
with crypto analysis.

**P5 — Advanced.** vectorbt backtesting + Monte Carlo on journaled setups · Deribit
options/IV · paid data tiers as chosen · **approval-gated execution** through
`propose_order` MCP flow · multi-user hardening.

---

# PART E — WHAT I NEED FROM YOU + COSTS

**Accounts (all free):** GitHub · Oracle Cloud Always-Free · Vercel · Supabase · Upstash.
**Free API keys:** FRED · Finnhub · OpenRouter · Groq · Google AI Studio. (Binance public
data needs none.)
**Claude:** interactive CIO runs through **Claude Code on your subscription — no extra
cost**. Optional ~$5–10 Anthropic API credit only if/when you want Claude as the
*headless* synthesizer too (a free model stands in until then).
**Costs:** build ≈ **$0** · run (bootstrap) **$0–50/mo** — Full Desk ≈ 2–10¢, light daily
use stays in budget · later pro tiers ($150–500/mo: Coinglass, on-chain, forex data,
frontier breadth) only on your explicit call.

---

# PART F — FABLE RAILS (how cheaper models execute at Fable level)

Honest mechanism: switching models transfers **encoded judgment**, not intelligence. All
judgment is encoded below; Opus/Sonnet run on rails.

## F1. Project `CLAUDE.md` (written in P0 — standing orders, auto-loaded every session)
**Invariants:** (1) all external I/O through `backend/adapters/` — no HTTP elsewhere;
(2) every LLM boundary Pydantic-validated — one retry, then drop, never hand-patch;
(3) `Decimal` for money math, UTC everywhere; (4) secrets never in frontend/git/logs;
(5) no live-execution paths in v1 — `Broker` stays paper; (6) config over code (YAML);
(7) **deterministic before generative** — an LLM may only cite numbers that exist in the
Market Brief. **Process:** follow ADRs — changes need a new ADR, not silent divergence;
ambiguity → ask, never improvise architecture; done = typed + validated + tested +
error-paths + docstring. **Design:** implement PART C exactly — tokens, motion budget,
banned list; no invented styles.

## F2. ADR log (`docs/decisions/`, written in P0)
0001 stack · 0002 hosting · 0003 adapter pattern · 0004 LiteLLM config roster ·
0005 mandate analysts · 0006 dual-mode CIO via MCP · 0007 calibrated confidence formula ·
0008 advisory-only v1 / broker stub · 0009 single-user v1 · 0010 DARKPOOL design tokens.

## F3. Prompts are versioned artifacts
`prompts/trend.md · contrarian.md · derivatives.md · risk_officer.md · red_team.md ·
cio_synthesis.md` — each beside its I/O schema. The desk's intelligence lives in
prompt+schema+brief, so mid-tier analyst models still produce institutional-shaped output.
Prompt edits are reviewed git diffs, not vibes.

## F4. Core contracts
**AnalystThesis** (exact shape, enforced):
```json
{ "mandate": "trend|contrarian|derivatives|risk", "model_id": "str",
  "direction": "long|short|no_trade", "conviction": 1-5,
  "entry_zone": {"low": 0, "high": 0}, "stop_loss": 0,
  "targets": [{"price": 0, "rr": 0}], "thesis": "<=120 words",
  "failure_mode": "str", "invalidation": {"price": 0, "condition": "str"},
  "evidence": ["brief.field.refs"] }
```
`evidence` is the anti-hallucination lock: cite a field that doesn't exist → rejected in
code. **TradePlan** = FR-4 fields verbatim, stored untouched, graded as published.

## F5. Session protocol + Fable-reserved work
Every build session: read `CLAUDE.md` → relevant ADRs → phase checklist → work top-down →
escalate ambiguity as a question. **Fable-only:** consensus/CIO logic, SMC algorithm
correctness, sizing/risk math, grading/calibration/backtest math — anything where subtle
error costs money. Opus/Sonnet: UI components, CRUD, adapters, wiring.

## F6. Windows note
Dev on Windows 11, deploy Linux ARM — dependencies chosen pure-Python (`pandas-ta`, not
TA-Lib) so both behave identically; CI runs tests on Linux to catch drift pre-deploy.

---

# VERIFICATION (per phase, cumulative)
- **P0:** deployed `/health` + `/price/BTCUSDT` return real data; CI green on Linux.
- **P1:** three assets searched → every FR-4 field present; spot-check numbers trace to
  brief fields; golden-fixture quant tests pass.
- **P2:** Full Desk under cost cap; ≥3 theses + divergence verdict + synthesized plan;
  Claude Code drives the CIO over MCP end-to-end; injected malformed analyst is dropped;
  Verdict Reveal + Constellation render within motion budget.
- **P3:** synthetic + real alert fire in Active mode and not in Manual; a graded plan
  moves model_scores; calibration curve renders.
- **Always:** Fable Rails audit — no adapter bypass, all boundaries validated, every
  published confidence traces to the §B5 formula; UI frames >16ms logged and addressed.

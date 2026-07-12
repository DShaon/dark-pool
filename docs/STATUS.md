# DARKPOOL — Build Status

> Update this file at the end of every working session.

## Current phase: **P4 — Forex + macro** (started 2026-07-09)
> P1–P3 core loops complete; carryover items (Fable-reserved CIO/recalibration,
> deferred context adapters, deploy) are tracked in their own sections below.

### P1 checklist
- [x] Design amendments from user reference boards (ADR-0011, MASTER_PLAN §C6a)
- [x] Quant/SMC engine: swings, BOS/CHoCH, order blocks, FVGs, liquidity (PDH/PDL/PWH/PWL,
      EQH/EQL with sweep states), premium/discount, indicators (EMA/RSI/MACD/ATR/BB/VWAP)
- [x] Context adapters: Binance futures (funding/OI/L-S), alternative.me F&G
- [x] Market Brief schema (v1.0, evidence-ref stable paths) + composer + `/brief/{symbol}`
- [x] Golden-fixture tests — 20 passing (incl. hand-verified BOS→CHoCH sequence)
- [x] Live verification: real BTCUSDT brief (structure, zones, funding, F&G) 2026-07-06
- [x] Analysis view: lightweight-charts candles + liquidity price lines + event markers,
      alignment hero tile, structure/derivatives/sentiment (arc dial)/zones rail — responsive
- [x] Premium design pass (2026-07-06, Fable): layered atmosphere (ambience + grid +
      vignette), machined gradient-hairline cards, HUD corner ticks, Geist Mono display
      numerals with odometer digit-roll, segmented TF control with sliding indicator,
      instrument-grade F&G dial (tick ring, gapped arcs, eased needle), hero sheen sweep,
      staggered card entrances, live pulse dots, ticking UTC clock, dot-leader zone rows,
      machined scrollbars. All CSS motion, transform/opacity only (C5 contract).
      Fix: chart mount is now absolute-positioned (percentage-height chain gave a 3px canvas).
- [x] Design surfaces complete (2026-07-07, Fable): **Desk Verdict** card (gold AI layer —
      mandate chips flare 80ms apart, confidence arc pours to calibrated %, serif verdict
      letters converge from tracked-out via per-letter transform, dot-leader plan rows,
      C6-voice thesis, replay control) · **Desk Pipeline Map** (4 mandate nodes on a
      diamond, solid-gold agreement edges vs dashed-dim dissent, ±1.5% breathe) ·
      **Desk Tape** (streaming semantic event log, entries slide in) · **Watchlist rail**
      (sparkline tiles on LIVE 1h klines, 24h change, click-to-retarget) · **Ctrl+K
      command palette** (stage recedes 4% + dims, panel expands from hairline, keyboard
      nav, free-typed symbols). AI output is placeholder marked with DEMO tags —
      Opus swaps in the real desk (P2) without touching the design.
      Fixes: verdict card was flex-crushed to 1px (overflow-hidden → min-content 0;
      rail children now shrink-0, rail scrolls instead) · demo plan now rescales with
      the live price on symbol switch · rail hardened with overflow-anchor:none.
      Verified: tsc clean, palette open→select→retarget→close, all endpoints 200.
- [x] Trade Setups shelf (2026-07-07, Fable): horizontal blotter under the chart — one
      card per Binance venue/style (FR-4 variants): SPOT swing accumulate · PERP 3×
      intraday · PERP 5× scalp · MARGIN 2× swing · OPTIONS covered call · GRID BOT range
      harvest. Each card: venue + leverage chip, semantic direction badge, gold strategy
      name, dot-leader entry/stop/target rows, 5-dot risk gauge, one-line edge. DEMO
      data scaled off live price; P2 replaces with real TradePlan variants.
      Verified at 1680×950: 6 cards render, chart canvases size correctly, no console
      errors, desk fits viewport without page scroll.
- [x] **Design phase COMPLETE** (2026-07-07, Fable): all FR-7 surfaces now exist as
      design shells. New this pass — **Journal & grading page** (`/journal`: summary
      tiles, trade log table, gold seat-leaderboard with weight bars, SVG calibration
      curve vs perfect-diagonal) · **Settings page** (`/settings`: Manual/Active mode
      toggle, risk-% preset chips, LLM spend meter, gold model roster, provider status
      list, config-over-code note) · **Alert Bloom** (C4 #8: amber SVG perimeter trace
      on warn/bear tape events, settles into corner badge count) · **Desk nav**
      (desk/journal/settings) + shared Clock/SiteHeader components.
      **Responsive pass**: mobile stacks chart → AI rail → board rail (order utils);
      board rail hidden only in the lg–xl band; header wraps (symbol form gets its own
      row, ⌘K hidden on touch); ticker scales 4xl→5xl; footers/tables wrap or scroll
      inside their cards. Verified via Haiku subagent at 1680×950 and 375×812 across
      all 3 routes: zero horizontal overflow, no hydration errors, no collapsed cards;
      tsc clean. Journal/settings values are DEMO-tagged; real wiring lands P1–P3.
      Still P2-scheduled by design: Depth Fog, Pressure Ripple, OB/FVG chart rectangles
      (one shared overlay canvas), Verdict Reveal on real Full-Desk runs.
- [x] **Quick Read LIVE** (2026-07-07, Fable): first real AI pass over the Market Brief.
      User provided Groq + Gemini + OpenRouter keys (backend/.env, gitignored).
      Built: `core/llm.py` OpenAI-compat gateway (ADR-0012 — LiteLLM deferred to P2,
      same YAML shape) · `config/models.yaml` roster (config over code) ·
      `models/quickread.py` QuickRead schema with **evidence lock** (dot-path resolver;
      citing a nonexistent brief field fails validation in code) · versioned prompt
      `prompts/quick_read.md` v1 · `desk/quick_read.py` service (one corrective retry,
      then drop — degraded response, never a 500) · `/quickread/{symbol}` (60s cache,
      `?force=true` re-run) · 7 new unit tests (27 total green). Fixed in review: path
      regex rejected digit-leading keys ("1h", "15m") — caught by the new tests.
      Live verified: groq/llama-3.3-70b returned a valid long read on BTCUSDT with 6
      evidence refs all resolving (incl. `swings[7].price`). Provider health: groq OK,
      gemini OK, openrouter key valid but free model upstream-rate-limited at test time.
      Frontend: DeskVerdict card now renders the real read (LIVE tag, model id,
      conviction arc, evidence-verified line) with demo fallback + ⟳ force re-run.
      Also fixed: desk viewport lock now applies only ≥1024×920px — short laptop
      screens (Windows 125–150% scaling) scroll normally instead of clipping the
      shelf/footer (root cause of the reported scroll issue).
- [x] **Bilingual Bengali layer + Dhaka time + watchlist persistence** (2026-07-07):
      Noto Sans Bengali font · central glossary `src/lib/glossary.ts` (30+ entries:
      OB/FVG/BOS/CHoCH/PDH/PDL/PWH/PWL/EQH/EQL/funding/OI/L-S/F&G/premium-discount/
      RR/conviction/evidence/venues…) · `<Term>` tooltip component — dotted underline,
      hover/tap reveals English term + Bengali name + Bengali explanation (opacity/
      transform only; `below`/`edge` variants keep tips in-viewport) · Bengali subtitles
      (`.bn-sub`) on every card header, setup card, and page title · all displayed times
      now Asia/Dhaka via `src/lib/time.ts` (storage stays UTC — invariant 3) ·
      watchlist add/remove with localStorage persistence (`dp:watchlist`, max 8, never
      empty; server-side persistence moves to DB later).
      Haiku-verified: 16 bn-subs, 56 terms, ঢাকা clock ticking, tooltips hidden-by-
      default with bilingual content, DOGE add survives reload, no hydration errors.
- [x] **UX polish pass — font, contrast, tooltip, Bengali depth, chart** (2026-07-08,
      from owner review). **Typography (ADR-0013):** Space Grotesk replaces Instrument
      Sans (brand/futuristic, still calm); numerics stay mono, verdict word stays serif.
      **Contrast:** `--text-mid`→#aeb9cb, `--text-dim`→#7c8698; trade-plan labels
      (entry/stop/tp/conv) + setup edge lines promoted dim→mid (were too faint).
      **Tooltip root-cause fix:** `<Term>` now renders its tip in a `<body>` portal at
      position:fixed, JS-clamped to the viewport — it can no longer be clipped by the
      rail's `overflow-y-auto` or a transformed ancestor (the reported cut-off tip).
      **Header truncation fix:** every card header stacks the Bengali subtitle UNDER the
      English label (no more `truncate` → "বিশ্লেষকদের ঐক…" renders whole).
      **Bengali depth:** whole glossary rewritten in warm native Bangla (senior-trader
      voice, fuller "why it matters"); added direction/trend/bias/signal terms so hover
      now explains bullish/bearish/long/short/mixed. Desk Verdict thesis, Desk Tape
      events, and every Setup edge carry a Bengali line; CONV is hover-explained.
      **Live AI Bangla:** QuickRead schema+prompt gained `thesis_bn`/`failure_mode_bn`
      (optional → never blocks a read); model stays groq/llama (reliable) — Gemini Flash
      gives cleaner Bangla but its free quota was exhausted and 2.5-flash truncates on
      thinking tokens (both documented in models.yaml).
      **DEMO clarity:** bare "DEMO" replaced by a hover-explained `SampleTag`
      (নমুনা · SAMPLE) that says, in Bengali, what sample data is and when P2 wires real.
      **Chart:** 5m + 1d added (brief now computes 5m/15m/1h/4h/1d; alignment score
      still intraday-core 15m/1h/4h so the money signal is unchanged) + EMA20/50 lines +
      volume histogram + legend; new **Signal Readout** strip (trend/RSI/EMA-stack/VWAP/
      ATR/nearest-liquidity — deterministic, bilingual). **Watchlist:** real visible
      "যোগ add" button + auto-USDT suffix.
      Verified: 27 backend tests green, tsc clean, brief=5 tfs & alignment=3 tfs live,
      live QuickRead returns Bengali. Haiku-verified 11/12 (12th a test-artifact — it
      clicked the header submit; add-button confirmed working here + persists).
- [x] **Journal wired + display type refresh + setups restacked** (2026-07-08, owner
      review). **Journal is now real:** `src/lib/journal.ts` (localStorage `dp:journal`,
      single-user) · a "＋ save to journal / জার্নালে যোগ" button on the Desk Verdict saves
      a live read as an OPEN trade · the journal page reads real trades, grades them
      (tp/sl/invalidated/reopen), deletes, and computes stats LIVE (win rate, avg R,
      total R, open count) — TP ⇒ planned R:R to TP1, SL ⇒ −1R, others ungraded; empty
      state when nothing saved. Seat leaderboard + calibration stay SAMPLE (P3 model_scores).
      **Typography (extends ADR-0013):** all italics dropped — Instrument Serif removed
      entirely. Verdict word, alignment bias, page titles, setup names now BOLD Space
      Grotesk, larger, upright (owner disliked the italic serif). **Trade Setups
      restacked:** was a horizontal scroll blotter → now a vertical stack of full-width
      tiles ("serially down") that fills the column under the (fixed-height) chart and
      scrolls internally; chart went from flex-1+max-h to a fixed `clamp(360,50vh,560)`
      so setups get the leftover space and the chart never balloons in fullscreen.
      Verified: tsc clean; journal seed→render→grade(SL)→stats recompute (100%→50% win,
      +1.80R→+0.40R avg)→persist confirmed; Haiku 7/7 (no italics, verdict weight 700,
      6 full-width stacked tiles, chart 475px, empty-state + Bengali on journal, no
      mobile overflow).
- [ ] Chart zone rectangles (OB/FVG) via overlay canvas — scheduled with P2 Depth Fog
- [ ] GDELT/FRED/Finnhub context adapters (FRED+Finnhub need free user keys)

## Current phase started: **P2 — The Desk** (analyst panel; backend engine done)

### P2 checklist
- [x] **Analyst panel backend** (2026-07-08, Opus scaffolding per §F5 split). The
      Full Desk fans the Market Brief out to 4 mandate seats — TREND / CONTRARIAN /
      DERIVATIVES / RISK (ADR-0005: same brief, four jobs) — IN PARALLEL. Each seat is
      a `QuickReadService` with its own mandate prompt, so every thesis inherits the
      schema + **evidence lock** + one-retry-then-drop. `models/analyst.py` (AnalystThesis
      wraps QuickRead + mandate + model_id; DeskPanelResponse) · `desk/analysts.py`
      (parallel `AnalystPanel`, order-stable, drop-on-failure) · versioned prompts
      `prompts/{trend,contrarian,derivatives,risk_officer}.md` (bilingual thesis_bn) ·
      `config/models.yaml` analyst roster spread across providers (one daily limit can't
      sink the panel) · `/desk/{symbol}` endpoint (120s cache, `?force=true`; degrades to
      status=degraded when < min_survivors, never 500s) · 4 new tests (31 total green:
      all-survive-in-order, drop-failing-seat, per-seat evidence lock, accessors).
      Live: the endpoint correctly fanned out 4 parallel calls and, with every free
      provider rate-limited today (groq TPD 100k exhausted from testing, gemini quota,
      openrouter upstream 429), returned status=degraded / 0 survivors with a clear
      reason — no crash. A ≥3-survivor run needs fresh free-tier quota (resets daily).
- [x] **Analyst panel frontend** (2026-07-08). `fetchDesk` + types · **Full Desk overlay**
      (`FullDeskPanel`) triggered from the Consensus card's "Full Desk →" button: renders
      each surviving analyst as a gold card (mandate + role EN/BN, model_id, direction word,
      conviction, entry/stop/tp, thesis EN+BN, evidence count), the direction tally, dropped
      seats (rate-limited chips), degraded/empty states, and an explicit **"CIO verdict ·
      pending (Fable)"** placeholder — the synthesis is never faked. **Consensus Constellation
      now real:** `PipelineMap` takes the panel and colours nodes gold when they share the
      plurality read, dashes dissent, hollows dropped seats; centre prints the plurality
      direction + count (raw tally, not a verdict) with a LIVE badge. Esc/×/backdrop close.
      Verified (mocked /desk, live is quota-limited): tsc clean; overlay opens with 4
      bilingual cards, tally LONG 2, CIO-pending-Fable chip, constellation LONG · 2/4 · LIVE;
      no console errors; Haiku screenshots — premium desktop, single-column mobile, no overflow.
- [x] **CIO consensus engine — the Fable pass** (2026-07-10, **built on Fable 5**
      per §F5; ADR-0015 records every rule). The desk now issues ONE call.
      `desk/divergence.py` — pure-code consensus_state (aligned/split/contested):
      conviction-weighted votes, entry clustering within 1.0×ATR(1h) (stops 1.5×),
      ordered rules with an auditable `notes` trail; all-stand-aside IS consensus;
      one survivor never is; missing ATR can't manufacture dissent.
      `desk/confidence.py` — ADR-0007 exactly: 0.5×deterministic checklist
      (mtf_alignment, structure-event map, funding-crowding, liquidity-room in ATR
      units; missing components EXCLUDED, never zero-filled) + 0.5×agreement
      (state base + conviction-weighted share; abstainers dilute). Clamped
      [0.05,0.95]; full component breakdown published (NFR-7); LLM self-confidence
      never an input. model_scores seat-weighting left as the P3-recalibration seam.
      `desk/sizing.py` — Decimal risk sizing (risk_pct/stop_distance, capped,
      cap reported); risk_pct_per_trade + max_position_pct in Settings.
      `desk/cio.py` — headless CIO (ADR-0006) with CODE guardrails: may take the
      plurality or STAND ASIDE, never counter-trade the panel; levels must sit
      inside the agreeing analysts' published span ±0.5 ATR with enforced geometry;
      R:R recomputed in code; evidence-locked; one corrective retry naming the
      violation → deterministic fallback (strongest agreeing seat's levels, stop
      widened to panel-most-conservative) → incoherent levels → STAND ASIDE. A
      ≥2-survivor desk ALWAYS yields a plan; <2 degrades honestly.
      `models/tradeplan.py` + `/plan/{symbol}` (plan cache keyed by desk-run
      timestamp — ?force re-synthesizes without re-running the panel, no double
      spend) + `prompts/cio_synthesis.md` v1 + `models.yaml: cio` block.
      **Frontend:** Full Desk overlay's "CIO verdict · pending (Fable)" replaced
      by the real verdict card — direction word, consensus chip, calibrated
      confidence with facts/desk split, entry/stop/TPs with R:R, size, confirmation
      triggers, invalidation, thesis EN/BN, kills-it/alt lines, built_from +
      evidence provenance. New CONFIDENCE glossary entry (native Bangla).
      **25 new tests (119 total green)** — golden fixtures with hand-computed
      expected values (documented in comments as money-risk constants): divergence
      8 states, confidence 4 exact-value cases, sizing 4, CIO 7 (rr/sizing
      recompute, counter-trade rejection+retry, invented-levels rejection,
      double-failure fallback math, LLM-error floor, no_trade forcing, incoherent
      →stand-aside), /plan route 2.
      **Live verification:** every rung of the degradation ladder exercised on real
      data (0 and 1 survivors → honest degraded envelopes; a surviving seat
      produced a valid evidence-locked read; no 500s anywhere). Full ≥2-survivor
      live synthesis is quota-gated: this session's testing exhausted every free
      tier's DAILY budget (measured + documented in models.yaml: groq 70B 100k
      tokens/day ≈ 8 desk runs; groq 8B 6k TPM never fits the ~10k-token brief;
      gemini per-model daily; openrouter :free 429). Quotas reset daily — first
      fresh run lights it up end-to-end. Config restored to the standing spread.
- [x] **MCP server** (2026-07-08, ADR-0006). `app/mcp/server.py` — a FastMCP stdio
      server (separate process, own adapters + desk) exposing 6 tools: `desk_health`,
      `get_market_brief`, `quick_read`, `run_full_desk` (the debate — 4 theses for the
      CIO to synthesize), `save_trade_plan`, `list_trade_plans`. CIO synthesis stays the
      caller's judgment (Fable §F5) — the server serves facts + records the decision,
      never fabricates a verdict. File-backed `PlanStore` (`app/desk/plan_store.py`,
      `backend/data/` gitignored) as the P1 stand-in for Postgres `trade_plans`; keys
      read from `.env`, never from `.mcp.json` (invariant 4). Connection config at repo
      root `.mcp.json` + guide `docs/mcp.md`. `mcp>=1.2` added to requirements (pure
      wheels, §F6 parity holds). 6 new tests (37 total green: store add/list/filter/
      limit/validation + all 6 tools registered). Live-smoked: desk_health, real
      get_market_brief off Binance (5 tfs), save→list roundtrip, bad-direction rejected.
      Connecting from Claude Code + a live CIO run are the user's to do interactively.

## Current phase started: **P3 — Monitoring, alerts, learning**

### P3 checklist
- [x] **Alert engine + live Desk Tape** (2026-07-08, FR-5). `app/monitor/alerts.py` —
      pure, deterministic rules over one Market Brief (no AI, no network): structure
      break (BOS=bull/bear tone, CHoCH=warn), liquidity sweep (daily + equal levels),
      funding extreme, OI spike, price-near-fresh-zone (unmitigated OB/FVG), sentiment
      extreme. Thresholds in `config/alerts.yaml` (config over code, invariant 6) via
      `AlertThresholds`. `models/alerts.py` (AlertEvent — bilingual, semantic tone) ·
      `/alerts/{symbol}` endpoint (20s cache). 5 new tests (42 total green: rich-brief
      trips every rule, quiet-brief is silent, CHoCH tone, config-driven OI threshold,
      mitigated zones excluded). **Desk Tape is now LIVE** — polls `/alerts`, renders
      real bilingual conditions (was simulated data), fires the Alert Bloom only on
      a NEWLY-appearing warn/bear condition (dedup via a seen-set, reset on symbol
      switch so the initial snapshot never blooms). Live-verified on real BTCUSDT data:
      caught a genuine 1h BOS ▼, 4h CHoCH ▼, and Extreme Fear (20), all bilingual.
      Next in FR-5: the background scanner (Active mode) that diffs this feed over
      time + browser push — this endpoint is the point-in-time layer it will build on.
- [x] **Background scanner + real Manual/Active mode** (2026-07-08, FR-5). Manual
      mode (default) is a true no-op — Active is opt-in, never a surprise (ADR-0008
      spirit). `app/monitor/state.py`: `ModeStore` / `WatchlistStore` (mirrors the
      frontend's localStorage board — single-user P1, browser owns the canonical
      list, server keeps a copy so scanning works with no tab open; validates,
      dedupes, uppercases, caps at 20) / `FeedStore` (rolling cross-symbol alert
      log, cooldown-based dedup — same condition suppressed 1h, not forever, so a
      genuine recurrence still surfaces). `app/monitor/scanner.py` — `Scanner.tick()`
      runs `scan_brief` over the whole watchlist when active; a failing symbol is
      skipped, never aborts the tick (NFR-3). Wired via **APScheduler**
      (`AsyncIOScheduler`, pure-Python, §F6 parity holds) in `main.py`'s lifespan,
      `scan_interval_seconds` config (default 60s), `max_instances=1` so a slow tick
      can't overlap itself. New `/monitor/{mode,watchlist,feed}` routes
      (`app/api/routes_monitor.py`). 21 new tests (63 total green): mode/watchlist/
      feed store roundtrips + cooldown dedup + cap, scanner mode-gating + per-symbol
      failure isolation + repeat-tick dedup, route validation.
      **Frontend wired for real:** Settings' Manual/Active toggle now calls
      `/monitor/mode` (optimistic UI, reverts on failure) — no longer decorative;
      `WatchlistRail` pushes its board to `/monitor/watchlist` on load and on every
      add/remove (best-effort, desk still works if the backend is briefly down);
      the desk footer shows a live `scan: active/manual` indicator polling
      `/monitor/mode`. Removed the page-level "DEMO" tag on Settings (misleading
      now that mode is real).
      Live-verified end-to-end on real market data (not mocked): set Active +
      watchlist via the API, ran the scanner directly against the SAME state files
      the live server uses → 8 real bilingual alerts recorded across BTCUSDT/
      ETHUSDT (structure breaks, zone proximity, sentiment extreme). Then verified
      the actual UI loop: toggled Active in Settings → confirmed via API it
      persisted → confirmed the desk footer picked it up. Reset to manual afterward
      (opt-in stays the user's call). No console errors.
      Not built (explicitly out of scope for this pass): browser push (needs a
      service worker + Push API + VAPID keys — a self-contained follow-up) and a
      dedicated "alerts across your whole watchlist" panel (the `/monitor/feed`
      endpoint is ready for it whenever that UI is wanted).
- [x] **Outcome grading** (2026-07-08, FR-6 — deliberately split from calibration; see
      below). "Did this trade hit target or stop" is mostly deterministic candle-walk,
      so it was built on Opus; only the *recalibration formula* stays Fable-reserved.
      `app/quant/grading.py` — pure `grade_candles(candles, direction, stop, target)`:
      walks candles in time order, grades "tp"/"sl" at the first bar reaching either
      level, "open" if neither yet. The one real ambiguity — a single bar's range
      containing BOTH levels (common on volatile crypto) — is resolved by drilling
      into finer candles for just that bar's window via an injected async callback;
      if still ambiguous even at 1m, falls back to a documented, industry-standard
      conservative default (assume stop-first — the same assumption backtesting
      frameworks use, since assuming the better outcome would overstate performance).
      `app/quant/grading_service.py` wires this to real data: 15m primary window from
      `since`, 1m drill-down on an ambiguous bar (added `start_time`/`end_time` support
      to `BinanceAdapter.get_klines`, backward-compatible). `/grade/{symbol}` route
      (`app/api/routes_grading.py`) — pure read/compute, writes nothing server-side.
      16 new tests (78 total green): clean tp/sl/open, short-direction mirroring,
      ambiguous-resolved-by-finer-data, ambiguous-still-ambiguous→conservative,
      resolver-unavailable→conservative, service wiring, route validation, adapter
      startTime/endTime forwarding.
      **Frontend:** the journal auto-grades every OPEN trade once on page load
      (`fetchGrade` per trade, applies via the existing `setOutcome`) — manual
      tp/sl/invalidated buttons stay as an override; "invalidated" is never set
      automatically since that's a judgment call ("the setup broke down"), not a
      price fact. A quiet "checking…" label shows while a check is in flight.
      Live-verified against REAL Binance history (not mocked): constructed a known
      reachable-target/unreachable-stop window → correctly graded "tp"; reachable-
      stop/unreachable-target → correctly graded "sl"; a since-now window → correctly
      "open". Then verified the frontend: seeded an open trade with the same known-tp
      levels, loaded `/journal`, confirmed it auto-flipped to "tp" in both localStorage
      and on screen. No console errors.
- [x] **Real-time WebSocket prices** (2026-07-08, from owner report: "too delayed, by
      the second?"). Root cause was architectural, not Binance being slow: the desk
      REST-polled every 15s, so that interval WAS the visible lag. Fix follows the
      master plan's own design (FR-1/B2: "WS collectors" are backend-side, invariant 1:
      all external I/O through adapters) rather than a quick client-side patch —
      considered and rejected a direct browser→Binance connection for exactly that
      reason. `app/adapters/binance_ws.py` — `BinanceStreamHub`: ONE upstream
      connection to Binance's combined-stream endpoint, shared across however many
      browser tabs are watching; dynamic SUBSCRIBE/UNSUBSCRIBE (no reconnect needed
      just to change symbol/timeframe); reconnects with full re-subscribe on any drop
      (idle timeout, Binance's 24h forced close, network blip); each local subscriber
      gets a capped queue (32) that drops the stale tick rather than ever blocking.
      `/ws/kline/{symbol}/{interval}` browser-facing route (`app/api/routes_ws.py`) —
      auth mirrors the REST bearer check but via a query param (a browser `WebSocket`
      can't set custom headers on the handshake). Added `start_time`/`end_time` to
      `BinanceAdapter.get_klines` (also reused by grading, above). 6 new tests (84
      total green): kline parsing matches the REST shape exactly, subscribe/dispatch/
      unsubscribe registry, queue-cap dropping, multi-subscriber fan-out — the
      reconnect loop itself does real I/O and is proven by the live smoke tests below,
      not unit-tested.
      **Frontend:** `useLiveKline(symbol, interval)` hook — opens/reconnects the WS,
      exposes `{liveTick, connected}`. `PriceChart` gained a `liveTick` prop with its
      OWN cheap `.update()` effect (candle + last EMA point + volume), kept separate
      from the full `setData()` reload path so a live tick never triggers a full chart
      reflow (recomputing EMA over ~300 closes every tick is trivial CPU work; the
      chart-library-side full-series repaint is what's expensive — this session's
      earlier scroll-perf fix made that distinction matter). Home() derives the ticker
      price/direction from `liveTick` (falling back to the REST array), appends a new
      bar into `candles` only on an actual bar rollover (comparing `open_time`), and
      slowed the REST kline poll from 15s→45s since it's now a resync safety net, not
      the primary path. A small live-dot next to the symbol label reflects the actual
      WS connection state.
      Live-verified end to end (not mocked): a raw script against Binance directly
      confirmed the exact message shape; a script against OUR OWN running server's new
      `/ws/kline/BTCUSDT/1m` endpoint confirmed the full hub+route pipeline (ticks with
      moving closes and increasing volume); in the browser, sampled the displayed price
      twice 4 seconds apart and it had already changed (62,117.40→62,117.41) — well
      under the old 15s poll, let alone the new 45s one; switching symbol (BTC→ETH tile)
      correctly closed the old stream and reconnected to the new one (ticker updated to
      ETHUSDT's real price, `wsConnected` stayed true). No console errors.
      Scope boundary noted at the time (closed same day, below): the watchlist rail
      still REST-polled every 60s.
- [x] **Live prices on the watchlist too** (2026-07-08, closing the scope boundary
      above — owner asked for live price "everywhere"). `WatchlistRail` split into a
      new `WatchlistTile` child component so each symbol gets its OWN stable
      `useLiveKline` call (rules of hooks: the board's symbol list can change, but
      each mounted tile's hook count never does). Confirms the hub design was already
      right for this: if a watchlist symbol matches the main chart's symbol+interval,
      `BinanceStreamHub` serves both from the SAME upstream Binance subscription —
      no extra cost. REST still refreshes the 24h sparkline shape every 60s; each
      tile's live tick moves its price, its 24h change% (recomputed from the live
      close against the REST-fetched first point), and the sparkline's last point in
      between polls — a stated approximation (not tracking the exact hour boundary
      per tile, unlike the main chart) since the next 60s poll rebuilds the array
      fresh and self-corrects around any rollover.
      Live-verified: sampled a watchlist tile's own price (ETHUSDT, not the main
      ticker) twice 4 seconds apart — it had already moved (1,739.53→1,739.49), well
      under the 60s poll. All 5 default tiles render valid sparklines; no console
      errors with 6 concurrent WebSocket connections open (main chart + 5 tiles).
      `SetupShelf` and `DeskVerdict` already inherit live pricing for free — both
      read `lastClose`, which already preferred `liveTick` from the earlier change.
- [x] **Confidence recalibration — the final Fable pass** (2026-07-10, **built on
      Fable 5**; ADR-0018 records every constant). The learning loop closes: graded
      CIO-plan outcomes now feed back into the confidence formula.
      `desk/calibration.py` — pure recompute-from-log engine + idempotent file store:
      seat reliability (hit = agreed∧TP or dissented∧SL; no_trade NEVER scored — an
      abstention has no counterfactual), recency decay λ=0.977/outcome (half-life
      ~30 trades, count-based so quiet weeks don't erase knowledge), Beta(2,2)
      shrinkage, weights = acc/0.5 clamped **[0.6, 1.4]** (bad seats dampened never
      silenced, hot seats capped); blend refit by grid-searched recency-decayed
      Brier over w∈[0.30,0.70], shrunk toward 0.5 by n_eff/(n_eff+50), **frozen at
      0.5 below 10 effective outcomes**; win-rate-per-confidence-bucket curve.
      **Hard rule: weights adjust CONFIDENCE only, never direction** (plurality
      stays unweighted — no lucky-streak feedback loops).
      Wiring: `DivergenceReport.votes_by_seat` (per-seat provenance on every plan),
      `compute_confidence(…, calibration)` (None → bit-identical original formula,
      `calibrated=false` said honestly), threaded through CIO synthesize/fallback,
      `/plan` reads params fresh per run; `POST /outcomes` (idempotent on
      symbol+closed_at) + `GET /calibration`.
      **Frontend:** CIO verdict card gains "save to journal · জার্নালে যোগ" carrying
      the calibration payload (confidence halves + seat votes); grading such a trade
      auto-reports to /outcomes (calPosted flag + server idempotency = never
      double-counted); journal's seat leaderboard + calibration curve now render
      **LIVE** from /calibration (weights ×, acc%, eff_n, blend split, Brier) with
      SAMPLE placeholders until outcomes exist; verdict footer states
      calibrated-vs-uncalibrated explicitly.
      **13 golden tests (147 total green)** — hand-computed constants ARE the
      contract: decayed eff_n 2.9315, both clamps, dissenter credit 1.2/0.8, n_eff
      12.0879, shrunk blend 0.539, curve buckets, idempotency, and
      calibration=None ≡ old golden values (0.85 unchanged).
      Live-verified end-to-end: POST outcome → GET shows trend ×1.2 / contrarian
      ×0.8 (matches hand math) → duplicate rejected → journal leaderboard flipped
      to LIVE·1 with real weights + frozen-blend note → test data removed, store
      verified back to neutral. tsc clean, console clean.
      **§F5 Fable-reserved list: COMPLETE** — every money-risk module (divergence,
      confidence, sizing, CIO guardrails, recalibration) was built on Fable with
      golden-fixture contracts.
- [x] **Setup journal loop — real variants, post-mortems, CIO feedback**
      (2026-07-10/11, ADR-0019; Fable for the feedback wiring + the
      auto-tuning refusal, mechanical ATR math itself is deterministic).
      Closed the gap between "here's a setup" and "did it work, does the desk
      remember." `desk/setups.py` — the Trade Setups shelf's six cards are now
      **deterministic ATR-rule variants** computed from the brief (no AI,
      golden-tested), replacing the old fake-price-scaled placeholders: each
      style sizes entry/stop/targets from its OWN anchor timeframe's ATR
      (scalp→15m, intraday→1h, swing/spot→4h); directional variants need a
      directional MTF bias (else "the desk stands aside"); the **grid is the
      inverse** — tradeable exactly when bias IS mixed (chop harvest); options
      stays informational v1 (no held-position tracking yet). Untradeable
      variants say WHY, never show fake numbers. `/setups/{symbol}` — pure GET
      over the cached brief, zero new upstream cost.
      `desk/lessons.py` — the failure post-mortem system: a 10-tag curated
      taxonomy (late_entry, news_event, missing_context, stop_too_tight, etc.)
      + free-text "what was missing," idempotent on (symbol, closed_at) so
      refining a reason UPDATES not duplicates. Win-rate-per-variant
      aggregation hides below 3 graded trades (2-trade win rates are noise,
      not signal). `POST/GET /lessons`, `GET /lessons/tags`.
      **The CIO now reads its own history:** `cio_payload()` (per-variant win
      rates + top recurring failure causes + recent post-mortem notes) rides
      the synthesis input BESIDE the brief (never inside it — the brief stays
      pure market fact); `cio_synthesis.md` v2 instructs the model to weigh
      named mistakes but never cite lessons as evidence or use them to justify
      levels outside the panel's range. Empty digest sends nothing (no noise
      pre-data).
      **Explicitly REJECTED (ADR-0019 §4):** automatically mutating the ATR
      rule multipliers from graded outcomes — the dishonest half of
      "auto-improve," an overfit factory on small samples. Numbers change via
      a new ADR informed by the now-surfaced stats, or P5 backtesting — never
      silently at runtime.
      **Frontend:** `SetupShelf` rebuilt on `/setups` — real levels, a per-card
      win-rate chip (`nW nL · win%`) once graded history exists, "＋ journal"
      on the 4 gradeable directional cards. Journal page: inline "why?"
      post-mortem editor appears on SL/invalidated rows (tag chips + note,
      500-char, feeds the CIO on save); new "strategy lessons" card
      (per-variant record, top failure causes, recent notes) goes LIVE once
      any outcomes exist.
      **13 new golden tests (160 total green):** hand-computed ATR levels for
      long/short/mixed bias (band/stop/target multiplier table verified
      exactly, incl. the 2.67R swing case), missing-ATR isolates only that
      variant, lesson hit-scoring + idempotent re-post + win-rate-hidden-
      below-3, CIO payload present/absent correctly.
      Live-verified end-to-end on real data: `/setups/LINKUSDT` returned a
      genuine long bias with hand-matching levels (other symbols sat mixed at
      test time — confirmed the gate, not a bug); saved all 4 directional
      variants from the live UI; graded SL opened the post-mortem editor;
      tags+note posted and aggregated correctly; setup win-rate chips and the
      journal's strategy-lessons card confirmed LIVE. tsc clean, console
      clean, backend 160/160.

### Interrupt fix (2026-07-08): desk-wide scroll performance
User reported the whole desk scrolling slowly. Root-caused two real issues (not
guessed): (1) `body` used `background-attachment: fixed` with 3 radial-gradients +
a repeating 44px grid pattern — a well-known scroll-jank antipattern, since a
fixed-attachment background on a *scrolling* element forces the browser to repaint
that complex background on every scroll frame instead of compositing it once.
Fixed by moving the exact same background onto a dedicated `body::before` at
`position: fixed` — a real fixed layer the browser composites independently and
never repaints on scroll (visually identical). (2) `Home()` re-rendered its entire
tree every 15s (klines poll) / 30s (brief poll), reconciling `WatchlistRail`,
`DeskTape`, and `PipelineMap` even though their own props hadn't changed — wrapped
all three (+ `Clock`, `DeskNav`) in `React.memo`. (3) `Term`'s tooltip-tracking
scroll listener fired ungated on every raw scroll event; rAF-throttled to one
measure per frame. Verified with real frame-timing (`performance.now()` during a
programmatic scroll), not screenshots: **16ms avg frame time, 0 tasks over 50ms**,
on both a plain page and the busy desk view — was the target of the complaint.

## Current phase started: **P4 — Forex + macro**

### P4 checklist
- [x] **Forex asset class + CRYPTO⇄FOREX toggle** (2026-07-09, ADR-0014). The engine is
      asset-agnostic, so forex runs on the SAME quant/SMC pipeline as crypto — the work
      was a data source + a dispatch seam + a free-tier budget, not new analysis.
      **Backend:** `app/markets.py` — `asset_class(symbol)` (forex iff two 3-letter ISO
      codes from USD/EUR/GBP/JPY/AUD/NZD/CAD/CHF, else crypto), `is_forex`,
      `to_twelvedata_symbol`. `adapters/twelvedata.py` — `TwelveDataAdapter` in the same
      `DataProvider`/`Candle` shape as Binance (ADR-0003): reverses Twelve Data's
      newest-first values, `volume=0` (forex is decentralized → VWAP correctly `None`,
      no invented number, invariant 7), parses both intraday and date-only daily
      timestamps, maps errors (their HTTP-200 `status:error` envelope) to `AdapterError`.
      `quant/brief.py` gained `_compose_forex` (OHLCV via the forex adapter → same engine;
      derivatives/sentiment `None`; honest `gaps` for derivatives / F&G / volume /
      DXY-COT-sessions). `/klines` routes forex symbols to `app.state.forex` with
      `FOREX_INTERVALS`. `config.py`: `twelve_data_api_key` (default `demo`),
      `default_forex_watchlist`.
      **Frontend:** `MarketToggle` — a two-segment sliding-pill CRYPTO⇄FOREX switch
      (same motion vocabulary as the TF tabs; crypto glows cyan, forex amber; transform/
      opacity only, C5). `page.tsx`: `assetClass` state, `switchAsset` (persists
      `dp:assetClass`, restores per-class last symbol — BTCUSDT / EURUSD — resets TF to
      1h), the ticker source label (`spot · binance` vs `spot · twelve data`, ws-pulse vs
      warn dot), symbol placeholder. `useLiveKline` gained an `enabled` flag — **off for
      forex** (no free real-time forex WS; REST is the source). `WatchlistRail` now takes
      an `assetClass` prop: independent per-class boards (`dp:watchlist:{class}`),
      forex `EUR/USD` formatting, forex 6-letter add validation, live tick disabled for
      forex tiles; the parent remounts it via `key={assetClass}` so state never leaks
      across classes. Derivatives + Fear&Greed cards render a clean bilingual "n/a" state
      on forex instead of "calibrating…".
      **Free-tier budget fix (root cause, not a patch).** Twelve Data free = **8 req/min
      AND 800/day**; the crypto-tuned polling generated ~17 req/min, so the shared token
      bucket queued unboundedly and even EURUSD hung for minutes. Fixed by making forex a
      slow lane sized to the budget: asset-class-aware backend TTLs (forex brief 180s,
      klines 90s), slower frontend polls (forex chart 60s, brief 180s, watchlist 300s),
      and a capacity-8 bucket burst so a cold load resolves the brief up front instead of
      starving behind ambient watchlist tiles. Result: cold brief ≈ 2s (full bucket),
      warm ≈ 0.2s (cached) — was a multi-minute hang.
      10 new tests (94 total green): Twelve Data parse/reverse/zero-volume/slash-symbol/
      error-envelope/interval-map/date-only-daily; forex composer full-SMC-no-derivatives
      + no-adapter-raises. Live-verified against real EUR/USD (not mocked): `/brief/EURUSD`
      returns all 5 timeframes, structure/OBs/FVGs/RSI/alignment + 4 daily levels, with
      derivatives/sentiment cleanly `null` and VWAP off; direct Twelve Data call 0.74s;
      cold USDJPY brief with a full bucket 1.89s. In the browser: CRYPTO→FOREX loads
      EURUSD in ~1s, source label flips to "twelve data", derivatives shows "forex spot
      has no perps", F&G shows "crypto-only index", watchlist shows EUR/USD·GBP/USD·
      USD/JPY·AUD/USD; switching back to crypto restores Binance data with no forex
      copy leaking through; tsc clean, backend tests green, console clean on fresh load.
      **Demo-key reality (documented in ADR-0014):** the built-in `demo` key serves only
      EUR/USD + USD/JPY; other pairs 502 until the user sets a free `TWELVE_DATA_API_KEY`
      (graceful — tiles show placeholders). Free forex is for intermittent analysis, not
      24/7 streaming (800/day).
- [x] **Model Desk — user-managed roster** (2026-07-10, ADR-0016; Opus on rails).
      Add any OpenAI-compatible provider (free or paid) + key from Settings and
      assign any model to any of the 7 roles (quick_read/trend/contrarian/
      derivatives/risk/cio/scenario) — no YAML/env editing. Backend: `desk/roster.py`
      `RosterStore` (gitignored `data/roster.json`, atomic) OVERLAYS models.yaml;
      `factory.py` refactored to `effective_providers`/`effective_roles` +
      `rebuild_desk` (services swap in place, no restart). `/models/*` routes:
      roster (keys MASKED `····last4`, env keys shown as "env"), test (1-token live
      probe), provider add/delete (delete refused while a role uses it), role
      set/delete (→ falls back to YAML). **Keys never leave the server unmasked,
      never logged** (invariant 4). **Validate-before-save**: a bad key/model/URL is
      caught with its reason, never persisted ("without facing any error" — verified
      live: unreachable URL → 400 with the transport error, no crash). Frontend:
      `ModelDesk` in Settings — role matrix (ready dot, source badge, inline edit +
      reset-to-default) + provider cards (masked key, delete) + add-provider form
      (base-URL presets + test). 15 new tests. Verified live: all 7 roles render,
      env keys masked, add rejects bad providers gracefully.
- [x] **Chart toolbar + overlays** (2026-07-10, ADR-0017 §1/§4). `ChartStage`
      wraps the chart with a toolbar: **plan picker** (per-click Quick Read / CIO
      plan) draws entry box + SL/TP price lines with R:R labels + a future path
      (entry→TP1→TP2 over ~12 bars); **OB / FVG** toggles draw the brief's zone
      bands for the active TF (closes the long-deferred chart-zones item);
      **refresh** forces klines+brief refetch. All client-side draws over
      already-fetched data — no upstream cost. Levels use teal/red semantics (not
      gold — gold is AI-only). Verified: OB toggles on/off, plan picker opens.
- [x] **AI scenario path** (2026-07-10, ADR-0017 §2). The "predicted path" toggle,
      built honest: the model NEVER invents a price — it only picks WHICH real,
      already-computed brief/plan levels price visits and in what ORDER (each
      `level_ref` is a dot-path resolved to a real price in code; unresolvable →
      one retry → unavailable). Backend: `models/scenario.py`, `desk/scenario.py`,
      `prompts/scenario.md`, `/scenario/{symbol}` (degrades, never 500s — verified
      live: quota-exhausted → clean `unavailable` envelope), `models.yaml scenario`
      block (roster-overridable). Frontend: chart toggle draws the resolved
      waypoints as a **dashed GOLD** polyline over future bars with a permanent
      "sequence opinion, not a forecast · দৃশ্যকল্প" badge. Never candles. 4 tests.
- [x] **Signals liquidity map** (2026-07-10, ADR-0017 §3). The chart toolbar's
      "◆ liq" dropdown lists every INTACT daily/equal level (PDH/PDL/PWH/PWL/EQH/
      EQL) with side + distance% (data already in the brief); clicking one flashes
      a bright price line on the chart that auto-dims after ~6s.
- [x] **Source badges everywhere** (2026-07-10, ADR-0017 §5). A `SourceBadge` ⓘ on
      every data-bearing card — click/hover shows exactly where that data came from
      (vendor / deterministic engine / AI-with-model-id), bilingual, colour-coded
      by kind (dim vendor · teal engine · gold AI). One `lib/provenance.ts` registry
      (16 surfaces). Placed on ticker, chart, signals, structure, derivatives, F&G,
      alignment, zones, quick-read (with model_id), CIO verdict + Full Desk (with
      synthesizer), tape, setups, watchlist, journal. Verified: 11 badges on the
      main page, tooltips render, console clean.
- [ ] Deferred P4 (stated, not silent): synthetic DXY (from the 6 constituent pairs),
      COT positioning, economic calendar + pre-news risk flag, correlation engine, forex
      real-time stream (no free source — revisit with a paid tier).
- [ ] **Fable-reserved (§F5):** CIO synthesis into one TradePlan + the confidence-
      recalibration formula (ADR-0007) still deliberately unbuilt on Opus — carried over
      from P2/P3, unchanged by this phase.

## Current phase started: **P5 — Advanced**

### P5 checklist
- [x] **Walk-forward backtesting + Monte Carlo** (2026-07-11, **built on Fable**;
      ADR-0020 records every rule — its numbers are the sanctioned evidence for
      ever changing ADR-0019's ATR multiplier table).
      **Deliberate deviation from the master plan, recorded in the ADR:** vectorbt
      was REJECTED — it would require re-expressing the setup logic as vectorized
      signal arrays, a parallel reimplementation that drifts from the strategy we
      actually run. Instead `quant/backtest.py` replays the PRODUCTION pipeline
      (`analyze_timeframe` → `compute_alignment` → `build_variants`, untouched)
      over historical Binance candles. Zero new dependencies — the backend stays
      pure Python (§F6), so the Monte Carlo uses seeded `random.Random`
      (spec-identical across platforms — strictly better for golden tests).
      **Conservative by rule** (every rule ships in the report's `assumptions`
      block — NFR-7 applies to simulations): decisions only on CLOSED 1h bars,
      200-bar visibility window (no lookahead, bisect-sliced); limit entry at the
      WORSE band edge, never a better fill; the fill bar may stop the trade out
      but may NOT take profit; an exit bar touching both levels = stop
      (grading.py's fallback); every R NET of per-side fees+slippage
      (config/backtest.yaml: PERP 5 / MARGIN 10 / SPOT 10 bps + 2 slippage —
      pinned by golden tests); one position per variant; still-open trades
      excluded and counted. Monte Carlo (2000 resamples, seed 7): total-R
      percentiles, drawdown percentiles, and **prob_loss** — the share of
      resampled histories ending ≤ 0; skipped with a stated reason under 10
      trades (ADR-0018's freeze-below-N honesty).
      **Surface:** `POST /backtest/{symbol}?days=` (30 default / 90 max, crypto
      only — free forex tier can't feed it) runs as a background job off the
      event loop (asyncio.to_thread; one at a time, honest 409); `GET
      /backtest/status` (progress), `GET /backtest/{symbol}` (stored report,
      `data/backtests.json`). Frontend: `BacktestPanel` on the journal page —
      symbol + 30/60/90d picker, progress bar, per-variant table (nW nL, win%,
      avg/total R, max DD, equity sparkline, MC p5…p95 + P(loss)), collapsible
      assumptions list, provenance badge (engine kind, bilingual).
      **17 new golden tests (177 total green):** hand-computed fill/exit/net-R
      (incl. the exact fee-drag arithmetic), fill-bar rules, both-touch=stop,
      pending-replacement + no-pyramiding, open-at-end exclusion, stats
      (PF/DD/consec), seeded MC pinned exactly, no-lookahead boundary,
      lean-brief ≡ full-brief parity for the 4 gradeable variants, synthetic
      end-to-end (48 decisions), insufficient-history ValueError, store
      roundtrip+eviction, route flow (202/400 forex/400 cap/409 busy/404).
      **Live-verified on real data:** a 30d BTCUSDT run (720 decisions) and a
      90d run (2160 decisions) both completed against real Binance history;
      a stored trade's cost math hand-verified to the fourth decimal
      (risk 132.20, cost_r 0.7586, net 0.4637). Live verification also CAUGHT
      a real bug pre-docs: Binance snaps startTime to its candle grid, eating
      one warmup bar on unaligned windows (199 < 200) — fixed with +2-bar fetch
      padding. **First real finding (the feature working as intended):** over
      the last 90 BTC days, the 5x scalp variant is uneconomical under taker
      fees — cost drag 0.7–2R per trade vs a 0.675-ATR(15m) risk distance,
      P(loss) 100%; spot/swing sit near break-even with wide MC intervals.
      That is evidence for the ADR-0019 multiplier conversation, not a reason
      to silently retune (the sweep stays refused — ADR-0020 §6).
- [x] **Approval-gated paper execution** (2026-07-11, **built on Fable**;
      ADR-0021 — fulfills ADR-0008's `propose_order` promise). The
      load-bearing design decision: **the gate is STRUCTURAL, not procedural.**
      The MCP surface (what an AI drives) gains `propose_order` +
      `list_proposals` + `get_paper_account` — and has NO approve capability
      at all; approve/reject/close exist only as authenticated `/broker`
      routes serving the web UI. A capability an agent does not have cannot
      be prompt-injected away. A dedicated test
      (`test_mcp_surface_has_no_approval_capability`) fails the build if any
      approval-adjacent tool ever appears on the AI surface.
      `app/broker/` — the ADR-0008 `Broker` interface with exactly ONE
      implementation: `PaperBroker` (simulated balance, REAL Binance prices,
      zero exchange keys — invariant 5 as code). Proposals are complete order
      intents (schema-enforced coherent geometry: stop on the losing side,
      TP1 on the winning side; risk ≤ 5%); TTL 6h; every lifecycle transition
      appends an audit event. **Approval fills at the LIVE price** (what
      really happens when a human clicks late), behind guardrails that refuse
      loudly: market at/through the stop → proposal expired ("the plan is
      dead"); live price outside entry zone ±0.5% → refused, stays pending;
      open position on the symbol → never stacked. Sizing = ADR-0015
      `position_size()` on realized balance; taker fee (10bps) + slippage
      (2bps) charged BOTH ways (config/broker.yaml, golden-pinned). Positions
      close deterministically via the P3 candle-walk grader on a 60s
      scheduler tick; manual close fills at live price with slippage against
      the trader. `data/paper_broker.json` shared by HTTP app + MCP server so
      an AI proposal appears in the UI for the owner's click.
      **Frontend:** `PaperDeskPanel` on the journal page — account strip
      (equity/balance/unrealized/realized), pending proposals with the
      APPROVE/REJECT buttons (gold "AI PROPOSED" chip on MCP-sourced ones),
      open positions with deterministic-close note, recent closed with
      realized R; refusal reasons surface inline. CIO verdict card gains
      "◇ propose · paper desk" (creates a PENDING proposal — approving stays
      on the journal page). Provenance entry `paper` (engine kind, bilingual).
      **18 new golden tests (195 total green):** hand-computed fill/close
      money math (balance 10000 → fee 5 → tp close 10139.85 / sl close
      9890.10, ±R exact), slippage 100→100.02 exact, all three refusal
      guardrails, expiry, reject/wrong-state/404, monitor skip-on-failure,
      account view + pricing gaps, reset, full route flow, and the gate test.
      **Live-verified on real BTC:** propose → approve filled at 64232.834
      (= live 64220 × 1.0002 slippage exactly; position 49.52% from 1% risk
      over the 2.02% stop distance; fee 4.95) → manual close −11.88 USDT
      (honest round-trip costs, −0.12R) → far-away proposal refused with the
      stated drift reason and left pending → account arithmetic consistent
      (9988.12) → paper store reset clean. UI verified live: panel renders
      account/pending/closed, approve/reject buttons work, console clean,
      tsc clean.
      **Exchange-feel + funds + manual orders (2026-07-12, Opus; owner
      request):** open positions reskinned as real order tickets — live mark
      price (pulse-cyan), unrealized PnL as USD · % · R, and a stop↔target
      rail with an entry tick + live mark marker (direction-agnostic SL/TP
      end labels). Positions poll every 6s while any is open (30s idle) so
      PnL actually ticks. New `POST /broker/deposit` (bookkeeping, not risk
      math — a fat-finger cap only; amount≤0 → 422, over-cap → 400) with an
      add-funds control (quick chips + custom). Manual "＋ new order" form
      places a limit at the user's own price via the SAME `propose` endpoint
      + approval gate — a single-price band, geometry echoed client-side for
      an instant reason. **Deliberately NOT auto-fill-on-touch:** a manual
      order still rests as a pending proposal you approve (auto-fill would
      bypass the ADR-0021 gate — flagged as a separate, deliberate change).
      Per-position live PnL reuses ONE shared `_unrealized()` helper that
      `account()` also sums, so the aggregate and per-position views can't
      drift (golden-tested). **15 new backend tests (210 total green):**
      live-position mark/PnL/R exact, pricing-gap leaves fields None,
      per-position sum ≡ account aggregate, deposit success/cap/non-positive,
      route enrichment + deposit flow. Live-verified end to end: deposit
      9957→14957, manual ETHUSDT order placed at 1800 and shown pending as
      MANUAL, BTC position PnL ticked −0.99R→−1.84 live as price moved,
      console clean, tsc clean, paper store reset after.
      **Order types + auto-fill + leverage (2026-07-12, Opus/Fable-fallback;
      ADR-0023; owner chose the "no liquidation" scope):** the desk now trades
      like a real terminal for the mechanics that can't mislead. `order_type`
      market|limit: **market** fills at once at live (POST /broker/market);
      **limit** RESTS and **auto-fills when price touches it** — fixing the
      old "outside the entry zone" refusal. The gate holds exactly (ADR-0021
      §1 preserved): auto-fill runs ONLY for owner-placed (`source=ui`) limit
      orders; an **AI-proposed limit NEVER auto-fills** (enforced in the
      monitor, dedicated test). Leverage 1–20 + spot/futures: leverage raises
      the notional cap to `max_position_pct × lev` and sets `margin_used =
      notional/lev` — but **risk stays risk% of balance, so loss-at-stop is
      leverage-independent** (why the no-liq scope is safe); spot forces 1x;
      **liquidation deliberately NOT modeled** (a wrong liq price misleads —
      deferred to its own Fable ADR, stated on the card). One shared
      `_open_position()` for approve/market/auto-fill so the three entry paths
      can't drift. **10 new golden tests (219 total green):** leverage margin +
      raised cap, spot-forces-1x, market immediate fill, limit auto-fill on
      touch long/short at the limit price (no slippage/maker), AI-limit never
      auto-fills (the gate), loss-at-stop unchanged by leverage, gap-through-
      stop expiry. Frontend: manual form gains market/limit + spot/futures +
      leverage chips (entry hidden for market); position ticket shows the
      `perp N×` badge + margin used; equity/balance bold + green/red vs start.
      **Live-verified:** market perp 5× filled (margin = notional/5 exact);
      a resting limit auto-filled via the REAL 60s scheduler at exactly the
      limit price; UI perp order rendered the leverage badge + margin + live
      PnL ticking; a real client bug (market nominal-entry == target) was
      caught by the backend geometry validator and fixed (midpoint). tsc +
      console clean, paper store reset after.
- [x] **Structure-aware setup variants** (2026-07-11, **built on Fable**;
      ADR-0022 — triggered by the owner's direct critique that the ATR-only
      cards "seem like kidding," plus ADR-0020's scalp-fee evidence).
      `desk/structure_entry.py` (new, pure): the 4 directional variants now
      hunt a real unmitigated order block / FVG on their own anchor TF within
      a per-style **search radius** (scalp 1.0 · intraday 1.5 · swing 2.5 ·
      spot 3.0 anchor-TF ATRs); the entry band IS the zone (preserves
      ADR-0020's worse-edge fill semantics exactly — zero backtest code
      changes); stops sit beyond the FARTHER of zone-edge and last opposing
      swing (+0.10 ATR buffer); targets are real liquidity (intact EQH/EQL,
      then opposing-zone near edges) behind a 1.2R floor, else the published
      ratio table rescaled onto the real stop; discrete 5-point confluence
      scoring (each point a named brief fact, published as `confluence[]`)
      with quality tiers ≥3 high / 2 medium / ≤1 low — ATR-fallback entries
      cap at medium by construction. Fallback path is byte-identical ADR-0019
      math, pinned by the original golden numbers as regression tests.
      `SetupVariant` gains `entry_kind` / `quality` / `confluence` (additive).
      **Live verification CAUGHT a design flaw pre-ship:** the draft reused
      the fallback `band` constants as the search radius; measured against a
      real BTC brief, actual zones sat 0.37–8.5 ATR behind price vs radii of
      0.15–0.5 ATR — the structure path would never have fired. Fixed with
      the dedicated per-style search constants (recorded as a REJECTED
      alternative in the ADR). After the fix, live across 4 symbols: BTC
      scalp anchored the actual fresh 15m FVG, ETH ran 3 structure-anchored
      cards, LINK intraday anchored a 1h FVG, DOGE honestly fell back
      everywhere — the selector discriminates, it doesn't decorate.
      **14 golden tests (204 total green)**, all hand-computed (stop 98.90
      via farther-swing, EQH TP1 1.67R, 1.2R floor rejection, radius boundary
      2.90-in/3.10-out, tiers 3/2/1, straddle exclusion, fallback-cap).
      **Backtest re-run (the ADR-0019 §4(d) evidence stream), BTCUSDT 90d,
      old ATR-only → new structure-aware:** scalp n 744→337, total −713R→−304R
      (junk trades halved, still P(loss)=1.0 — the fee wall is the style's
      stop-vs-cost ratio, not the entry); intraday n 248→109, −74R→−39R
      (P(loss)≈1.0); **swing 53→7 trades, −10.7R→+1.5R; spot 28→5, −1.5R→+1.6R
      — both flipped positive, and the system itself refuses to over-claim
      (MC skipped below 10 trades).** 30d run consistent. Standing evidence
      for a future ADR on the scalp variant's economics (retire or re-price);
      per ADR-0019 §4 it will NOT be silently retuned.
      **Frontend surfacing (2026-07-11, same day, Opus):** the shelf now
      renders it — a semantic quality chip (high=teal/medium=amber/low=dim,
      bilingual), a "◆ structure-anchored" vs "ATR rule · no zone in range"
      line, and the checkmarked confluence reasons per card; `SetupVariant`
      TS type + the `setups` provenance tooltip updated (was still describing
      ATR-only — caught by the owner). tsc clean, console clean, live-verified
      on ETHUSDT (4 structure cards: 3 high, 1 medium). Engine facts stay
      teal/amber — never gold (gold is AI-only, ADR-0010).
- [ ] Remaining P5 (unstarted): Deribit options/IV, paid data tiers,
      multi-user hardening, live-broker implementation (its own ADR, behind
      the SAME gate). Deferred P4 items unchanged (DXY, COT, calendar,
      correlation). NEW candidate from ADR-0022 evidence: a scalp-variant
      economics ADR (fee wall proven under two different entry logics).

## Previous phase: **P0 — Foundation** (complete locally; deploys pending accounts)

### P0 checklist
- [x] Repo scaffold: CLAUDE.md, ADRs 0001–0010, .gitignore, README
- [x] Master plan copied to `docs/MASTER_PLAN.md`
- [x] Backend skeleton: FastAPI app, config, cache (memory/Upstash), rate limiter, Binance adapter
- [x] Routes: `/health`, `/price/{symbol}`, `/klines/{symbol}` (bearer auth when API_TOKEN set)
- [x] Backend tests green locally (9 passed)
- [x] Local verification: real BTC price + klines served from live Binance (2026-07-06)
- [x] Frontend: Next.js 16 + DARKPOOL tokens/fonts + live BTC price page (builds clean)
- [x] CI workflow written (`.github/workflows/ci.yml`) — runs on first GitHub push
- [ ] Deploy: Oracle VM (backend) + Vercel (frontend) — **needs user accounts, see below**
- [ ] First git commit + push — awaiting user's GitHub repo

### Blocked on user
- Accounts (all free): GitHub · Oracle Cloud Always-Free · Vercel · Supabase · Upstash
- Free API keys (P1): FRED · Finnhub · OpenRouter · Groq · Google AI Studio

## Phase history
- 2026-07-06 — Plan approved (`docs/MASTER_PLAN.md`). P0 started. Python 3.12 installed
  via winget (was missing). Node 24 / npm 11 / git present.

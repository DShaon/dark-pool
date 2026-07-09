# DARKPOOL — Build Status

> Update this file at the end of every working session.

## Current phase: **P1 — Crypto Intraday Advisory MVP** (in progress)

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
- [ ] **Fable-reserved (§F5, money-risk):** divergence detector → consensus_state
      (aligned/split/contested via ATR-band level clustering), CIO synthesis into ONE
      TradePlan, calibrated-confidence formula (0.5 deterministic checklist + 0.5 panel
      agreement, ADR-0007), position sizing. Deliberately NOT built on Opus.
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
- [ ] **Fable-reserved (§F5):** the confidence-recalibration FORMULA — how graded
      outcomes feed back into model_scores and blend with the deterministic checklist
      (ADR-0007), Brier-score bucketing, recency/decay weighting, small-sample
      overfit guards. This is the part where a wrong judgment call is quiet and
      compounding (every future confidence number would be subtly off), unlike
      grading above — deliberately not built on a lighter model.

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

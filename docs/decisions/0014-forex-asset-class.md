# ADR-0014 — Forex asset class: Twelve Data source + free-tier budget model

**Status:** accepted · 2026-07-09
**Implements:** MASTER_PLAN PART D · P4 ("Forex + macro"). Extends ADR-0003 (adapter
pattern) and ADR-0009 (single-user v1). No change to the quant engine or the Market
Brief contract — forex runs on the *same* deterministic engine as crypto.

## Context
P4 adds forex (`EURUSD`, `GBPUSD`, …) alongside crypto. The engine (SMC / structure /
TA / multi-timeframe alignment) is asset-agnostic — it operates on `Candle`s, not on
"crypto". The open questions were: (1) where forex OHLCV comes from, (2) how the rest of
the system tells a forex symbol from a crypto one, and (3) how to live inside forex's
free-tier API budget without the desk feeling broken.

Crypto uses Binance: no key, effectively unlimited public data, a real-time WS. Forex has
no equivalent free firehose. The chosen source, **Twelve Data**, has a hard **8 requests/
minute AND 800 requests/day** free ceiling (one free lifetime key), and its built-in
`demo` key serves only a couple of pairs (EUR/USD, USD/JPY). The crypto UI was tuned for
Binance cadences (15–45s polls, a WS tick stream); pointed at Twelve Data unchanged, a
single forex view generated ~17 req/min against the 8/min cap, so the shared token-bucket
queue grew without bound and even a working pair hung for minutes.

## Decision
- **Source = Twelve Data adapter** (`adapters/twelvedata.py`), same `DataProvider` /
  `Candle` shape as Binance (ADR-0003). Forex is decentralized so there is **no
  consolidated volume** → `volume = Decimal("0")` (the engine's VWAP correctly reports
  `None`; no fake number is invented — invariant 7). Newest-first values are reversed to
  oldest-first; daily bars arrive date-only and are parsed to UTC midnight.
- **Asset-class dispatch = `app/markets.py`.** `asset_class(symbol)` returns `"forex"`
  iff the symbol is exactly two 3-letter ISO codes from a fixed set
  (`USD/EUR/GBP/JPY/AUD/NZD/CAD/CHF`), else `"crypto"`. One pure function; the composer,
  the `/klines` route, and the WS route all branch on it. Adding an asset class later =
  extend this function + add an adapter, nothing else.
- **No derivatives / no Fear & Greed for forex.** Those are crypto-only; on the forex
  path they are `None` and become honest `gaps` entries, never failures (NFR-3). The UI
  renders a plain "n/a — forex spot has no perps" / "crypto-only index" state.
- **Free-tier budget model (the load-bearing decision).** Forex is treated as a **slow
  lane**, sized to fit 8/min:
  - Backend caches are asset-class-aware: forex brief TTL **180s** (a cold compose costs
    5 timeframe calls), forex klines TTL **90s** — vs 30s / 10s for crypto.
  - Frontend polls forex slower: chart **60s**, brief **180s** (aligned to the cache),
    watchlist tiles **300s** (ambient sparklines). Crypto keeps its WS + fast polls.
  - The Twelve Data token bucket bursts a **full minute (capacity 8)** so a cold desk
    load fires the brief's calls up front instead of starving behind ambient watchlist
    tiles; the 0.13/s refill still holds the long-run average at 8/min.
  - Forex has **no real-time WS** (`useLiveKline` is disabled for it) — none is free.

## Consequences
- `EURUSD` reaches full parity with crypto analysis: same 5 timeframes, structure, order
  blocks, FVGs, PDH/PDL/PWH/PWL, alignment — verified live. Cold brief ≈ 2s (full
  bucket), warm ≈ 0.2s (cached).
- **Free-tier forex is for intermittent analysis, not 24/7 streaming.** 800/day means a
  continuously-open forex desk exhausts the daily budget in a few hours; the API then
  returns errors, which degrade gracefully (tiles show placeholders, cards show
  "calibrating…"). Paid Twelve Data / Polygon (MASTER_PLAN, deferred) removes this.
- **The `demo` key only serves EUR/USD + USD/JPY.** Other pairs 502 until the user sets a
  free `TWELVE_DATA_API_KEY` — handled gracefully, and the forex default board leads with
  EUR/USD so the out-of-box experience works.
- Deferred to later P4 (stated, not silent): synthetic DXY, COT positioning, economic
  calendar / pre-news risk flag, correlation engine, forex real-time stream.

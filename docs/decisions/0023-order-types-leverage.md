# ADR-0023 — Order types, resting-limit auto-fill, leverage/margin (no liquidation)

**Status:** accepted · 2026-07-12 · built on Opus as the Fable fallback, on the
rails (golden-tested money math) — the owner explicitly chose the "no
liquidation" scope, which keeps this bounded and safe for the fallback tier.
**Extends:** ADR-0021 (paper broker + approval gate). Adds exchange-style order
mechanics the owner asked for after using the paper desk.

## Context
The paper desk (ADR-0021) filled only via a human approval click, at market,
within a tolerance band. Two real frictions surfaced in use:
1. A limit placed away from price could never fill — approval refused it
   ("outside the entry zone") because price hadn't arrived yet. The owner
   wants a real **resting limit** that fills itself when price touches.
2. No leverage / margin / order-type / spot-vs-futures — it didn't feel like a
   real terminal.

The owner chose (via an explicit prompt) **leverage + margin WITHOUT
liquidation**: real liquidation math is exchange-specific and dangerous if even
slightly wrong (a bad liq price teaches bad instincts), so it stays deferred to
its own careful Fable ADR. Everything here is bounded money-math — leverage
cannot increase the loss-at-stop — which is why it is safe on the fallback tier.

## Decisions

### 1. Order types: `market` and `limit`
`ProposalIn`/`OrderProposal` gain `order_type: "market" | "limit" | None`.
- **None** — legacy proposal (setup cards, CIO/MCP). Unchanged: rests pending,
  needs the approval click, fills at market within tolerance. Back-compat.
- **market** (manual form) — fills IMMEDIATELY at the live price on placement
  (slippage against the trader). No pending state.
- **limit** (manual form) — rests at the user's price and **auto-fills when
  price touches it** (see §2). Fills AT the limit price, no slippage (maker).

`order_type` is set only by the manual order form, so its presence cleanly
distinguishes an owner-placed order from a forwarded engine/AI suggestion —
no need to overload `source`.

### 2. Resting-limit auto-fill — and why it does NOT weaken the gate
The scheduler tick (which already closes positions) now also OPENS a position
from a resting limit when price crosses it: long fills when `live <= limit`,
short when `live >= limit`. **Guardrail that preserves ADR-0021 §1:** auto-fill
runs ONLY for `order_type == "limit" AND source == "ui"`. An **AI-proposed
(`source == "mcp"`) order NEVER auto-fills** — it always requires the human
approval click, enforced in the monitor and covered by a dedicated test.

The reasoning: the gate exists so an AI cannot cause a fill without a human
act. A limit order the **owner placed themselves** already *is* that human act —
the commitment happened at placement. So resting + auto-filling it is not the
AI self-executing; it is the owner's own order working. The gate's purpose is
intact: no AI-authored order moves even paper money without a human.

A resting limit still honors the proposal TTL (expires unfilled after
`proposal_ttl_hours`) — a GTD order, not GTC.

### 3. Leverage + margin — bounded, cannot increase risk
Per-order `leverage: int` (1..`max_leverage`, config, default 20) and
`market_type: "spot" | "perp"`. Spot forces leverage 1.
- Sizing stays **risk-first** (ADR-0015): `qty` follows from `risk_pct` of
  balance and the stop distance. **Leverage does NOT change qty or the
  loss-at-stop** — a 1% risk is 1% of balance at 1x or 20x. This is the whole
  reason the "no liquidation" version is safe: the only bounded loss
  (stop-out) is leverage-independent.
- Leverage's two real effects, both modeled: it **raises the notional cap**
  from `max_position_pct` to `max_position_pct × leverage` (so a tight-stop
  setup isn't clipped), and it sets **margin used = notional / leverage**
  (the cash locked), stored and displayed on the position.
- **Not modeled (accepted, stated):** liquidation. Between entry and stop a
  levered position's unrealized loss can transiently exceed its margin; the
  deterministic stop-close still exits at the stop, so REALIZED loss stays
  ~risk% and the account cannot silently blow up. The missing liq price is the
  one thing leverage really adds that we omit — the owner accepted this; a
  real liquidation model is a future Fable ADR.

### 4. Shared fill path
`approve` (market-at-live), `place_market_order` (market-at-live on placement),
and the monitor's limit auto-fill all route through one `_open_position(state,
proposal, fill_price, apply_slippage)` — sizing/leverage/margin/fee computed in
ONE place so the three entry paths cannot drift. Same discipline as ADR-0021's
shared close and the live-PnL `_unrealized` helper.

## Consequences
- The paper desk now behaves like a real terminal for the mechanics that
  can't mislead: market/limit orders, resting limits that fill on touch,
  leverage with visible margin — while the one genuinely dangerous number
  (liquidation) is honestly absent, not faked.
- New golden tests pin: leverage margin + raised cap, spot forces 1x, market
  immediate fill, limit auto-fill on touch (long/short) at the limit price,
  AI-proposed limits never auto-fill (the gate), and loss-at-stop unchanged by
  leverage. Full suite stays green.
- The approval gate (ADR-0021 §1) is refined, not removed: its invariant —
  "no AI-authored order fills without a human act" — still holds exactly.

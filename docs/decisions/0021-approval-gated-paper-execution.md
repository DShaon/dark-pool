# ADR-0021 — Approval-gated paper execution (`propose_order`)

**Status:** accepted · 2026-07-11 · **authored on Fable** (execution is the
sharpest money-risk seam in the system — the design here decides whether the
future live bot can ever act without a human)
**Implements:** the P5 "approval-gated execution" item; fulfills ADR-0008's
promise ("live execution will later arrive… behind an explicit approval flow
(`propose_order` MCP tool), never as edits to analysis code").

## Context
The desk advises; it does not trade (invariant 5). The master plan's endgame
is Claude-proposes → human-approves → broker-executes. Building the *seam* now
— with a paper broker only — means the approval workflow, sizing, guardrails,
and audit trail are proven long before any real key exists. A future live
broker is then a new `Broker` implementation behind the SAME gate, plus its
own ADR — never a change to this flow.

## Decisions

### 1. The gate is STRUCTURAL, not procedural
The MCP server — the surface an AI drives — gets `propose_order`,
`list_proposals`, and `get_paper_account`. **It has no approve tool, by
design.** Approve/reject/close exist only as authenticated HTTP routes serving
the web UI. An AI cannot approve its own proposal because no approval
capability exists on any surface an AI touches; the gate cannot be
prompt-injected, misconfigured, or "helpfully" automated away. This is the
load-bearing decision of this ADR: a rule an agent must *choose* to follow is
advice; a capability an agent does not *have* is a gate.

### 2. Paper only (invariant 5, restated as code)
`app/broker/` holds the `Broker` interface with exactly one implementation:
`PaperBroker` — simulated balance, real Binance prices, zero exchange keys.
No code path in this repo can place a real order. A live implementation is a
future ADR with its own risk review.

### 3. Proposal lifecycle (every transition audited)
```
pending ──approve (UI)──▶ filled ──stop/target/manual──▶ closed
   │──reject (UI)──▶ rejected
   │──TTL lapses──▶ expired        (lazily evaluated on read/approve)
```
- A proposal is a COMPLETE order intent: symbol, direction (long|short only),
  entry zone, stop, ≥1 target, optional risk %, thesis, source. Incomplete
  intents are rejected at the schema — an approver must see exactly what will
  happen.
- TTL default 6h (config): an intraday plan approved a day later is a
  different trade. Expired proposals cannot be approved.
- Every transition appends an audit event (who/what/when/detail). NFR-7
  applies to money most of all.

### 4. Approval fills honestly, or refuses loudly
Approval triggers a market fill at the LIVE price — not the proposed entry —
because that is what really happens when a human clicks minutes later. Two
guardrails run first, both refusals stated in the audit trail:
- **Already invalid:** live price at-or-beyond the proposed stop → refused
  (the plan is already dead; approving it would knowingly enter a lost trade).
- **Entry drift:** live price outside the entry zone stretched by
  `entry_tolerance_pct` (default 0.5%) → refused, proposal STAYS pending —
  price may come back; the human may re-try approval while it lives.
Fills charge taker fee + slippage against the trader (config bps); exits
charge them again. Paper PnL that ignores costs is flattery, not simulation
(same reasoning as ADR-0020 §3).

### 5. Sizing is the desk's own math
Quantity = equity × `position_size()` (ADR-0015, unchanged) from the
proposal's risk % (default from settings) and its stop distance, capped as
ever. The paper account starts at a configured balance (default 10,000 USDT).
One open position per symbol (config) — approving into an existing position
is refused, not stacked.

### 6. Positions close deterministically
A scheduler tick (60s) runs the SAME candle-walk grader that grades journal
trades (P3): first touch of stop → closed at stop; first touch of TP1 →
closed at TP1 (full exit at TP1, v1 — partials later); the walk's documented
conservative both-touch rule applies. Manual close fills at live price.
No AI anywhere in the execution layer.

### 7. Non-goals (v1)
No live keys, no partial fills/TP ladders, no funding accrual on paper perps
(flat costs absorb it approximately — stated), no order books/depth modeling,
no multi-account. Each is future work, most behind the live-broker ADR.

## Consequences
- The full propose → human-approve → execute → monitor → close loop exists
  and is testable today, with structurally zero execution risk.
- The CIO (interactive via MCP, or the headless verdict card in the UI) can
  now END its analysis with a concrete, sized, audited order intent — and
  still cannot move even paper money without the owner's click.
- The paper account becomes a second honest evidence stream (alongside the
  journal and ADR-0020 backtests) for whether the desk's calls make money
  after costs.

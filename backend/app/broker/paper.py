"""PaperBroker (P5 · ADR-0021) — simulated balance, real prices, zero keys.

The only Broker implementation in v1 (invariant 5). Approval fills at the
LIVE Binance price — not the proposed entry — because that is what really
happens when a human clicks minutes after the AI proposed. Guardrails refuse
loudly instead of filling badly:

  * market already at/through the stop  -> proposal EXPIRED ("plan is dead")
  * live price outside entry zone ± tol -> refused, proposal STAYS pending
  * an open position on the symbol      -> refused, never stacked

Costs are charged both ways (taker fee + slippage against the trader) — paper
PnL that ignores costs is flattery, not simulation (ADR-0020 §3 reasoning).
Positions close deterministically via the P3 candle-walk grader; no AI
anywhere in this layer. Every transition appends an audit event.

Sizing note: quantity comes from `position_size()` (ADR-0015) applied to the
account's REALIZED balance — unrealized PnL is not collateral here (the
conservative reading; stated, not silent).
"""

import asyncio
import contextlib
import json
import os
import tempfile
import uuid
from datetime import datetime, timedelta, timezone
from decimal import ROUND_DOWN, ROUND_HALF_UP, Decimal
from pathlib import Path

import yaml
from pydantic import BaseModel

from app.adapters.base import AdapterError
from app.adapters.binance import BinanceAdapter
from app.broker.base import Broker
from app.desk.sizing import position_size
from app.markets import is_forex
from app.models.broker import (
    Actor,
    AuditEvent,
    BrokerState,
    CloseReason,
    OrderProposal,
    PaperAccountView,
    PaperPosition,
    ProposalIn,
)
from app.quant.grading_service import GradingService

_BPS = Decimal(10_000)
_PCT = Decimal(100)
_PRICE_Q = Decimal("0.00000001")
_QTY_Q = Decimal("0.00000001")
_USD_Q = Decimal("0.00000001")


class BrokerConfig(BaseModel):
    starting_balance: Decimal = Decimal("10000")
    fee_bps_per_side: float = 10.0
    slippage_bps_per_side: float = 2.0
    entry_tolerance_pct: Decimal = Decimal("0.5")
    proposal_ttl_hours: int = 6
    max_open_per_symbol: int = 1
    monitor_interval_seconds: int = 60
    # A fat-finger guard, not a risk limit — this is paper money (owner
    # request, 2026-07-12). One deposit call adds at most this much.
    max_deposit_per_request: Decimal = Decimal("1000000")
    # Max leverage on a futures (perp) paper order (ADR-0023). Raises the
    # notional cap to max_position_pct × leverage; spot is always 1x.
    max_leverage: int = 20


def load_broker_config(path: str | Path) -> BrokerConfig:
    p = Path(path)
    if not p.exists():
        return BrokerConfig()
    data = yaml.safe_load(p.read_text(encoding="utf-8")) or {}
    return BrokerConfig(**data)


class BrokerStateError(Exception):
    """Wrong lifecycle state for the requested transition (route -> 409)."""


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _event(actor: Actor, action: str, detail: str | None = None) -> AuditEvent:
    return AuditEvent(at=_now(), actor=actor, action=action, detail=detail)


def _unrealized(pos: PaperPosition, mark: Decimal) -> tuple[Decimal, float | None]:
    """The ONE unrealized-PnL formula, shared by account() (aggregate) and
    positions_live() (per-position) — same math, computed once, so the two
    views can never silently drift apart. Gross of exit costs (the exit fee
    isn't paid until the position actually closes)."""
    moved = mark - pos.entry_price if pos.direction == "long" else pos.entry_price - mark
    pnl = (moved * pos.qty).quantize(_USD_Q, rounding=ROUND_HALF_UP)
    risk_amount = (abs(pos.entry_price - pos.stop) * pos.qty).quantize(
        _USD_Q, rounding=ROUND_HALF_UP
    )
    r = round(float(pnl / risk_amount), 4) if risk_amount > 0 else None
    return pnl, r


class PaperBroker(Broker):
    kind = "paper"

    def __init__(
        self,
        path: Path,
        config: BrokerConfig,
        spot: BinanceAdapter,
        grading: GradingService,
        risk_pct_default: Decimal,
        max_position_pct: Decimal,
    ) -> None:
        self._path = path
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._config = config
        self._spot = spot
        self._grading = grading
        self._risk_default = risk_pct_default
        self._max_position_pct = max_position_pct
        self._lock = asyncio.Lock()
        self._fee = Decimal(str(config.fee_bps_per_side)) / _BPS
        self._slip = Decimal(str(config.slippage_bps_per_side)) / _BPS

    @property
    def config(self) -> BrokerConfig:
        return self._config

    # ── persistence (atomic, same pattern as every other store) ──

    def _load(self) -> BrokerState:
        if not self._path.exists():
            return BrokerState(balance=self._config.starting_balance)
        try:
            raw = json.loads(self._path.read_text(encoding="utf-8"))
            return BrokerState.model_validate(raw)
        except (json.JSONDecodeError, OSError, ValueError):
            # A corrupt paper store must not brick the app — but never
            # silently: the fresh state is auditable in the first event.
            state = BrokerState(balance=self._config.starting_balance)
            return state

    def _save(self, state: BrokerState) -> None:
        fd, tmp = tempfile.mkstemp(dir=str(self._path.parent), suffix=".tmp")
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                f.write(state.model_dump_json())
            os.replace(tmp, self._path)
        except BaseException:
            with contextlib.suppress(OSError):
                os.unlink(tmp)
            raise

    def _expire_stale(self, state: BrokerState) -> None:
        now = _now()
        for p in state.proposals:
            if p.status == "pending" and now > p.expires_at:
                p.status = "expired"
                p.audit.append(_event("system", "expired", "TTL lapsed unapproved"))

    # ── proposals ──

    def _build_proposal(self, intent: ProposalIn, source: Actor) -> OrderProposal:
        symbol = intent.symbol.strip().upper()
        if is_forex(symbol):
            raise ValueError("paper trading is crypto-only in v1 (no live forex feed)")
        if intent.leverage > self._config.max_leverage:
            raise ValueError(f"leverage capped at {self._config.max_leverage}x")
        now = _now()
        return OrderProposal(
            id=uuid.uuid4().hex[:10],
            symbol=symbol,
            direction=intent.direction,
            entry_low=intent.entry_low,
            entry_high=intent.entry_high,
            stop=intent.stop,
            targets=intent.targets,
            risk_pct=intent.risk_pct if intent.risk_pct is not None else self._risk_default,
            thesis=intent.thesis,
            source=source,
            status="pending",
            created_at=now,
            expires_at=now + timedelta(hours=self._config.proposal_ttl_hours),
            order_type=intent.order_type,
            market_type=intent.market_type,
            leverage=intent.leverage,
            audit=[_event(source, "proposed", f"expires {self._config.proposal_ttl_hours}h")],
        )

    def propose(self, intent: ProposalIn, source: Actor) -> OrderProposal:
        """Rest a proposal (legacy None, or a limit that will auto-fill on
        touch). Market orders never come here — they go to place_market_order
        so they fill at once."""
        state = self._load()
        self._expire_stale(state)
        proposal = self._build_proposal(intent, source)
        state.proposals.append(proposal)
        self._save(state)
        return proposal

    def list_proposals(self, status: str | None = None) -> list[OrderProposal]:
        state = self._load()
        self._expire_stale(state)
        self._save(state)
        out = [p for p in state.proposals if status is None or p.status == status]
        return sorted(out, key=lambda p: p.created_at, reverse=True)

    def reject(self, proposal_id: str) -> OrderProposal:
        state = self._load()
        self._expire_stale(state)
        p = self._find_proposal(state, proposal_id)
        if p.status != "pending":
            raise BrokerStateError(f"proposal is {p.status}, not pending")
        p.status = "rejected"
        p.audit.append(_event("ui", "rejected"))
        self._save(state)
        return p

    # ── the shared fill (approve · market · limit auto-fill all route here) ──

    def _has_open(self, state: BrokerState, symbol: str) -> bool:
        n = sum(1 for x in state.positions if x.status == "open" and x.symbol == symbol)
        return n >= self._config.max_open_per_symbol

    def _open_position(
        self,
        state: BrokerState,
        p: OrderProposal,
        fill_price: Decimal,
        apply_slippage: bool,
        actor: Actor,
    ) -> PaperPosition:
        """ONE fill path (ADR-0023 §4): sizing, leverage, margin, fee computed
        here for every entry so the three callers can't drift. `fill_price` is
        live (market) or the limit price (resting); slippage is charged only on
        a market taker fill, never on a resting maker fill."""
        if apply_slippage:
            slip_sign = 1 if p.direction == "long" else -1
            entry_eff = (fill_price * (1 + slip_sign * self._slip)).quantize(
                _PRICE_Q, rounding=ROUND_HALF_UP
            )
        else:
            entry_eff = fill_price.quantize(_PRICE_Q, rounding=ROUND_HALF_UP)

        lev = max(1, p.leverage)
        # Leverage raises the notional cap; risk (risk_pct of balance) is
        # unchanged, so loss-at-stop is leverage-independent (ADR-0023 §3).
        eff_max = self._max_position_pct * Decimal(lev)
        sizing = position_size(
            entry=entry_eff, stop=p.stop, risk_pct=p.risk_pct, max_position_pct=eff_max
        )
        notional = (
            state.balance * Decimal(str(sizing.position_pct)) / _PCT
        ).quantize(_USD_Q, rounding=ROUND_DOWN)
        qty = (notional / entry_eff).quantize(_QTY_Q, rounding=ROUND_DOWN)
        if qty <= 0:
            raise BrokerStateError("account balance too small to open any position")
        notional = (qty * entry_eff).quantize(_USD_Q, rounding=ROUND_HALF_UP)
        # margin <= balance by construction (position_pct is capped at
        # 100×lev, so notional/lev <= balance).
        margin = (notional / Decimal(lev)).quantize(_USD_Q, rounding=ROUND_HALF_UP)
        entry_fee = (notional * self._fee).quantize(_USD_Q, rounding=ROUND_HALF_UP)
        state.balance -= entry_fee

        position = PaperPosition(
            id=uuid.uuid4().hex[:10],
            proposal_id=p.id,
            symbol=p.symbol,
            direction=p.direction,
            qty=qty,
            entry_price=entry_eff,
            stop=p.stop,
            target=p.targets[0],
            notional_entry=notional,
            fees_paid=entry_fee,
            risk_pct=p.risk_pct,
            position_pct=Decimal(str(sizing.position_pct)),
            market_type=p.market_type,
            leverage=lev,
            margin_used=margin,
            status="open",
            opened_at=_now(),
            audit=[_event(
                actor, "filled",
                f"{p.market_type} {lev}x @ {format(entry_eff, 'f')} · qty "
                f"{format(qty, 'f')} · margin {format(margin, 'f')} · fee {format(entry_fee, 'f')}",
            )],
        )
        p.status = "filled"
        p.position_id = position.id
        state.positions.append(position)
        return position

    async def place_market_order(self, intent: ProposalIn) -> dict:
        """Manual MARKET order: fills at once at the live price (owner-placed,
        ADR-0023). Same shape as approve()'s result. Refuses (loudly) only on
        an existing position or a live price already through the stop."""
        async with self._lock:
            state = self._load()
            self._expire_stale(state)
            p = self._build_proposal(intent, source="ui")
            state.proposals.append(p)
            if self._has_open(state, p.symbol):
                p.status = "rejected"
                reason = f"an open paper position already exists on {p.symbol} — not stacking"
                p.audit.append(_event("ui", "market_refused", reason))
                self._save(state)
                return {"approved": False, "reason": reason, "proposal": p, "position": None}
            live = (await self._spot.get_ticker(p.symbol)).price
            dead = live <= p.stop if p.direction == "long" else live >= p.stop
            if dead:
                p.status = "rejected"
                reason = (
                    f"market {format(live, 'f')} is already at/through the stop "
                    f"{format(p.stop, 'f')} — refusing to open a dead trade"
                )
                p.audit.append(_event("ui", "market_refused", reason))
                self._save(state)
                return {"approved": False, "reason": reason, "proposal": p, "position": None}
            pos = self._open_position(state, p, live, apply_slippage=True, actor="ui")
            p.audit.append(_event("ui", "approved", f"market fill -> position {pos.id}"))
            self._save(state)
            return {"approved": True, "reason": None, "proposal": p, "position": pos}

    # ── the approval fill (only reachable through the authenticated UI route) ──

    async def approve(self, proposal_id: str) -> dict:
        """Returns {"approved": bool, "reason": str|None, "proposal": ...,
        "position": ...|None}. Refusals are results, not errors — the human
        sees WHY and the proposal's audit trail records it."""
        async with self._lock:
            state = self._load()
            self._expire_stale(state)
            p = self._find_proposal(state, proposal_id)
            if p.status != "pending":
                raise BrokerStateError(f"proposal is {p.status}, not pending")

            if self._has_open(state, p.symbol):
                reason = f"an open paper position already exists on {p.symbol} — not stacking"
                p.audit.append(_event("ui", "approve_refused", reason))
                self._save(state)
                return {"approved": False, "reason": reason, "proposal": p, "position": None}

            live = (await self._spot.get_ticker(p.symbol)).price

            dead = live <= p.stop if p.direction == "long" else live >= p.stop
            if dead:
                p.status = "expired"
                reason = (
                    f"invalidated: market ({format(live, 'f')}) already at/through the "
                    f"stop ({format(p.stop, 'f')}) — the plan is dead"
                )
                p.audit.append(_event("ui", "approve_refused", reason))
                self._save(state)
                return {"approved": False, "reason": reason, "proposal": p, "position": None}

            tol = self._config.entry_tolerance_pct / _PCT
            zone_lo = p.entry_low * (1 - tol)
            zone_hi = p.entry_high * (1 + tol)
            if not (zone_lo <= live <= zone_hi):
                reason = (
                    f"live price {format(live, 'f')} is outside the entry zone "
                    f"{format(p.entry_low, 'f')}–{format(p.entry_high, 'f')} "
                    f"±{self._config.entry_tolerance_pct}% — still pending, try again "
                    "if price returns"
                )
                p.audit.append(_event("ui", "approve_refused", reason))
                self._save(state)
                return {"approved": False, "reason": reason, "proposal": p, "position": None}

            pos = self._open_position(state, p, live, apply_slippage=True, actor="ui")
            p.audit.append(_event("ui", "approved", f"filled as position {pos.id}"))
            self._save(state)
            return {"approved": True, "reason": None, "proposal": p, "position": pos}

    # ── positions ──

    def positions(self, status: str | None = None) -> list[PaperPosition]:
        state = self._load()
        out = [x for x in state.positions if status is None or x.status == status]
        return sorted(out, key=lambda x: x.opened_at, reverse=True)

    async def positions_live(self, status: str | None = None) -> list[PaperPosition]:
        """Same list as `positions()`, but every OPEN position is enriched
        with a fresh mark price + unrealized PnL/R (the exact formula
        `account()` already sums — factored into `_unrealized` so the two
        views can't drift). One ticker fetch per unique open symbol, not per
        position. A pricing gap leaves those three fields None — never a
        guessed number."""
        out = self.positions(status)
        symbols = {x.symbol for x in out if x.status == "open"}
        marks: dict[str, Decimal] = {}
        for sym in symbols:
            try:
                marks[sym] = (await self._spot.get_ticker(sym)).price
            except AdapterError:
                continue
        for pos in out:
            if pos.status != "open":
                continue
            mark = marks.get(pos.symbol)
            if mark is None:
                continue
            pos.mark_price = mark
            pos.unrealized_pnl, pos.unrealized_r = _unrealized(pos, mark)
        return out

    async def close_position(self, position_id: str) -> PaperPosition:
        """Manual close: fills at the live price with slippage against the
        trader (a market exit, honestly priced)."""
        async with self._lock:
            state = self._load()
            pos = self._find_position(state, position_id)
            if pos.status != "open":
                raise BrokerStateError("position is already closed")
            live = (await self._spot.get_ticker(pos.symbol)).price
            slip_sign = -1 if pos.direction == "long" else 1  # exit crosses the spread
            exit_eff = (live * (1 + slip_sign * self._slip)).quantize(
                _PRICE_Q, rounding=ROUND_HALF_UP
            )
            self._close_at(state, pos, exit_eff, "manual", "ui")
            self._save(state)
            return pos

    def _close_at(
        self,
        state: BrokerState,
        pos: PaperPosition,
        exit_price: Decimal,
        reason: CloseReason,
        actor: Actor,
    ) -> None:
        exit_notional = (pos.qty * exit_price).quantize(_USD_Q, rounding=ROUND_HALF_UP)
        exit_fee = (exit_notional * self._fee).quantize(_USD_Q, rounding=ROUND_HALF_UP)
        moved = (
            exit_price - pos.entry_price
            if pos.direction == "long"
            else pos.entry_price - exit_price
        )
        pnl_gross = (moved * pos.qty).quantize(_USD_Q, rounding=ROUND_HALF_UP)
        entry_fee = pos.fees_paid  # only the entry fee has been paid so far
        state.balance += pnl_gross - exit_fee

        risk_amount = (abs(pos.entry_price - pos.stop) * pos.qty).quantize(
            _USD_Q, rounding=ROUND_HALF_UP
        )
        realized = pnl_gross - entry_fee - exit_fee
        pos.status = "closed"
        pos.closed_at = _now()
        pos.exit_price = exit_price
        pos.exit_reason = reason
        pos.fees_paid = entry_fee + exit_fee
        pos.realized_pnl = realized
        pos.realized_r = (
            round(float(realized / risk_amount), 4) if risk_amount > 0 else None
        )
        pos.audit.append(_event(
            actor, "closed",
            f"{reason} @ {format(exit_price, 'f')} · pnl {format(realized, 'f')} "
            f"({pos.realized_r}R) · exit fee {format(exit_fee, 'f')}",
        ))

    def _limit_price(self, p: OrderProposal) -> Decimal:
        """The resting limit's trigger price — the band collapses to one price
        for a manual limit; use the worse edge for safety if it doesn't."""
        return p.entry_high if p.direction == "long" else p.entry_low

    async def monitor_tick(self) -> int:
        """One scheduler tick (ADR-0021 close + ADR-0023 auto-fill): closes
        open positions at stop/target via the P3 candle-walk grader, then
        auto-fills resting OWNER-placed limit orders whose price has been
        touched. AI-proposed orders NEVER auto-fill — the gate holds. A failing
        symbol is skipped, never aborts the tick (NFR-3). Returns how many
        state changes occurred (closes + fills)."""
        async with self._lock:
            state = self._load()
            self._expire_stale(state)
            changes = 0

            # 1. closes (existing behavior)
            for pos in [x for x in state.positions if x.status == "open"]:
                try:
                    outcome = await self._grading.grade(
                        pos.symbol, pos.direction, pos.stop, pos.target, pos.opened_at
                    )
                except AdapterError:
                    continue
                if outcome.outcome == "tp":
                    self._close_at(state, pos, pos.target, "tp", "system")
                    changes += 1
                elif outcome.outcome == "sl":
                    self._close_at(state, pos, pos.stop, "sl", "system")
                    changes += 1

            # 2. resting-limit auto-fill — owner-placed limits only (the gate:
            #    an AI-proposed order can never auto-fill).
            resting = [
                p for p in state.proposals
                if p.status == "pending" and p.order_type == "limit" and p.source == "ui"
            ]
            price_cache: dict[str, Decimal] = {}
            for p in resting:
                if self._has_open(state, p.symbol):
                    continue  # one position per symbol — leave it resting
                live = price_cache.get(p.symbol)
                if live is None:
                    try:
                        live = (await self._spot.get_ticker(p.symbol)).price
                    except AdapterError:
                        continue
                    price_cache[p.symbol] = live
                # a dead plan (price already through the stop) expires unfilled
                dead = live <= p.stop if p.direction == "long" else live >= p.stop
                if dead:
                    p.status = "expired"
                    p.audit.append(_event("system", "expired", "price reached the stop before the entry"))
                    changes += 1
                    continue
                limit = self._limit_price(p)
                touched = live <= limit if p.direction == "long" else live >= limit
                if touched:
                    pos = self._open_position(state, p, limit, apply_slippage=False, actor="system")
                    p.audit.append(_event("system", "auto_filled", f"limit touched -> position {pos.id}"))
                    changes += 1

            if changes:
                self._save(state)
            return changes

    # ── account ──

    async def account(self) -> PaperAccountView:
        state = self._load()
        self._expire_stale(state)
        self._save(state)
        open_positions = [x for x in state.positions if x.status == "open"]
        closed_positions = [x for x in state.positions if x.status == "closed"]
        unrealized = Decimal(0)
        gaps: list[str] = []
        for pos in open_positions:
            try:
                live = (await self._spot.get_ticker(pos.symbol)).price
            except AdapterError:
                gaps.append(pos.symbol)
                continue
            pnl, _ = _unrealized(pos, live)
            unrealized += pnl
        realized_total = sum(
            (x.realized_pnl for x in closed_positions if x.realized_pnl is not None),
            Decimal(0),
        )
        cents = Decimal("0.01")  # USD display precision; the store keeps 8dp

        def _c(v: Decimal) -> Decimal:
            return v.quantize(cents, rounding=ROUND_HALF_UP)

        return PaperAccountView(
            starting_balance=_c(self._config.starting_balance),
            balance=_c(state.balance),
            equity=_c(state.balance + unrealized),
            unrealized_pnl=_c(unrealized),
            realized_pnl_total=_c(realized_total),
            n_open=len(open_positions),
            n_closed=len(closed_positions),
            n_pending=sum(1 for p in state.proposals if p.status == "pending"),
            priced_at=_now(),
            pricing_gaps=gaps,
        )

    def reset(self) -> None:
        """Wipe the paper account back to the configured starting balance.
        UI-only, explicit — paper money, real discipline."""
        self._save(BrokerState(balance=self._config.starting_balance))

    def deposit(self, amount: Decimal) -> Decimal:
        """Top up the paper balance (owner request, 2026-07-12). Bookkeeping,
        not a sizing/risk decision — the cap only catches a fat-fingered
        amount. Returns the new balance."""
        if amount <= 0:
            raise ValueError("deposit amount must be positive")
        if amount > self._config.max_deposit_per_request:
            raise ValueError(
                f"deposit capped at {format(self._config.max_deposit_per_request, 'f')} "
                "per request"
            )
        state = self._load()
        state.balance += amount
        self._save(state)
        return state.balance

    # ── lookups ──

    @staticmethod
    def _find_proposal(state: BrokerState, pid: str) -> OrderProposal:
        for p in state.proposals:
            if p.id == pid:
                return p
        raise KeyError(f"no proposal {pid}")

    @staticmethod
    def _find_position(state: BrokerState, pid: str) -> PaperPosition:
        for x in state.positions:
            if x.id == pid:
                return x
        raise KeyError(f"no position {pid}")


__all__ = ["PaperBroker", "BrokerConfig", "BrokerStateError", "load_broker_config"]

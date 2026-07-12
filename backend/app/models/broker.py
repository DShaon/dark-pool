"""Paper broker contracts (P5 · ADR-0021).

A proposal is a COMPLETE order intent — the approver must see exactly what
will happen, so the schema enforces coherent geometry (stop on the losing
side, first target on the winning side) at validation time, not at fill time.
Money fields are Decimal serialized as strings via format(v, "f") (invariant 3;
never scientific notation); timestamps UTC. Every lifecycle transition appends
an `AuditEvent` (NFR-7 — money most of all).
"""

from datetime import datetime
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, Field, field_serializer, model_validator

ProposalStatus = Literal["pending", "filled", "rejected", "expired"]
CloseReason = Literal["tp", "sl", "manual"]
Actor = Literal["mcp", "ui", "system"]
OrderType = Literal["market", "limit"]
MarketType = Literal["spot", "perp"]


def _f(v: Decimal | None) -> str | None:
    return None if v is None else format(v, "f")


class AuditEvent(BaseModel):
    at: datetime
    actor: Actor
    action: str
    detail: str | None = None


class ProposalIn(BaseModel):
    """What a proposer (CIO over MCP, or the UI) submits. Direction is long or
    short only — 'no_trade' is advice, not an order."""

    symbol: str
    direction: Literal["long", "short"]
    entry_low: Decimal
    entry_high: Decimal
    stop: Decimal
    targets: list[Decimal] = Field(min_length=1, max_length=3)
    risk_pct: Decimal | None = None  # None -> settings default
    thesis: str = Field(min_length=1, max_length=600)
    # ADR-0023 — set only by the manual order form; None keeps the legacy
    # approval flow (setup cards, CIO/MCP). "market" fills now; "limit" rests
    # and auto-fills on touch (owner-placed only).
    order_type: OrderType | None = None
    market_type: MarketType = "spot"
    leverage: int = Field(default=1, ge=1, le=125)

    @model_validator(mode="after")
    def _coherent_geometry(self) -> "ProposalIn":
        if self.entry_low > self.entry_high:
            raise ValueError("entry_low must be <= entry_high")
        if any(v <= 0 for v in (self.entry_low, self.entry_high, self.stop, *self.targets)):
            raise ValueError("all price levels must be positive")
        if self.risk_pct is not None and not (0 < self.risk_pct <= 5):
            raise ValueError("risk_pct must be in (0, 5] — the desk never risks more")
        if self.market_type == "spot" and self.leverage != 1:
            raise ValueError("spot orders are always 1x — no leverage")
        if self.direction == "long":
            if not self.stop < self.entry_low:
                raise ValueError("long: stop must sit below the entry zone")
            if not self.targets[0] > self.entry_high:
                raise ValueError("long: first target must sit above the entry zone")
        else:
            if not self.stop > self.entry_high:
                raise ValueError("short: stop must sit above the entry zone")
            if not self.targets[0] < self.entry_low:
                raise ValueError("short: first target must sit below the entry zone")
        return self


class OrderProposal(BaseModel):
    id: str
    symbol: str
    direction: Literal["long", "short"]
    entry_low: Decimal
    entry_high: Decimal
    stop: Decimal
    targets: list[Decimal]
    risk_pct: Decimal
    thesis: str
    source: Actor  # who proposed: "mcp" (the AI CIO) or "ui" (the owner)
    status: ProposalStatus
    created_at: datetime
    expires_at: datetime
    position_id: str | None = None  # set when filled
    order_type: OrderType | None = None  # ADR-0023
    market_type: MarketType = "spot"
    leverage: int = 1
    audit: list[AuditEvent] = Field(default_factory=list)

    @field_serializer("entry_low", "entry_high", "stop", "risk_pct")
    def _ser(self, v: Decimal) -> str:
        return format(v, "f")

    @field_serializer("targets")
    def _ser_targets(self, v: list[Decimal]) -> list[str]:
        return [format(t, "f") for t in v]


class PaperPosition(BaseModel):
    id: str
    proposal_id: str
    symbol: str
    direction: Literal["long", "short"]
    qty: Decimal  # base asset quantity
    entry_price: Decimal  # effective (slippage applied)
    stop: Decimal
    target: Decimal  # TP1 — full exit at TP1 in v1
    notional_entry: Decimal  # entry_price × qty
    fees_paid: Decimal  # cumulative entry + exit fees
    risk_pct: Decimal
    position_pct: Decimal
    # ADR-0023: leverage/margin (no liquidation). margin_used = notional / lev.
    market_type: MarketType = "spot"
    leverage: int = 1
    margin_used: Decimal = Decimal(0)
    status: Literal["open", "closed"]
    opened_at: datetime
    closed_at: datetime | None = None
    exit_price: Decimal | None = None
    exit_reason: CloseReason | None = None
    realized_pnl: Decimal | None = None  # net of all fees
    realized_r: float | None = None  # net PnL / amount risked at entry
    # Live-quoted (owner request, 2026-07-12) — populated only when the
    # route enriches an OPEN position with a fresh ticker; None on closed
    # positions (which have realized_pnl/realized_r instead) and None if the
    # ticker fetch failed (a pricing gap, never a guessed number).
    mark_price: Decimal | None = None
    unrealized_pnl: Decimal | None = None  # gross of exit costs — exit isn't paid yet
    unrealized_r: float | None = None
    audit: list[AuditEvent] = Field(default_factory=list)

    @field_serializer(
        "qty", "entry_price", "stop", "target", "notional_entry",
        "fees_paid", "risk_pct", "position_pct", "margin_used",
    )
    def _ser(self, v: Decimal) -> str:
        return format(v, "f")

    @field_serializer("exit_price", "realized_pnl", "mark_price", "unrealized_pnl")
    def _ser_opt(self, v: Decimal | None) -> str | None:
        return _f(v)


class DepositIn(BaseModel):
    """Top up the paper balance — bookkeeping, not risk math (owner request,
    2026-07-12): no position sizing, no fill logic, no pricing formula. The
    server-side cap (BrokerConfig.max_deposit_per_request) exists only to
    catch a fat-fingered amount, not to gate a real financial decision."""

    amount: Decimal

    @model_validator(mode="after")
    def _positive(self) -> "DepositIn":
        if self.amount <= 0:
            raise ValueError("deposit amount must be positive")
        return self


class PaperAccountView(BaseModel):
    starting_balance: Decimal
    balance: Decimal  # realized cash
    equity: Decimal  # balance + unrealized on open positions (live prices)
    unrealized_pnl: Decimal
    realized_pnl_total: Decimal
    n_open: int
    n_closed: int
    n_pending: int
    priced_at: datetime
    pricing_gaps: list[str] = Field(default_factory=list)  # symbols we couldn't price

    @field_serializer(
        "starting_balance", "balance", "equity", "unrealized_pnl", "realized_pnl_total"
    )
    def _ser(self, v: Decimal) -> str:
        return format(v, "f")


class BrokerState(BaseModel):
    """The persisted whole (file store; Postgres later)."""

    balance: Decimal
    proposals: list[OrderProposal] = Field(default_factory=list)
    positions: list[PaperPosition] = Field(default_factory=list)

    @field_serializer("balance")
    def _ser(self, v: Decimal) -> str:
        return format(v, "f")


__all__ = [
    "AuditEvent",
    "ProposalIn",
    "OrderProposal",
    "PaperPosition",
    "PaperAccountView",
    "BrokerState",
    "DepositIn",
    "ProposalStatus",
    "CloseReason",
    "Actor",
    "OrderType",
    "MarketType",
]

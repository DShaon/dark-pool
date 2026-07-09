"""Market structure: trend state and BOS / CHoCH events.

Chronological walk over candles. Swings register only at their confirmation
index (no lookahead). A close above the most recent confirmed-and-unbroken
swing high is a bullish break: BOS if the trend was already bullish (or unset),
CHoCH if it flips a bearish trend. Mirror for lows. After a break, that side's
reference is cleared — a new pivot must form before another event can fire on
that side, so one impulse never spams repeated events.
"""

from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from typing import Literal

from app.models.market import Candle
from app.quant.swings import Swing, detect_swings

Trend = Literal["bullish", "bearish", "range"]
EventKind = Literal["BOS", "CHoCH"]


@dataclass(frozen=True)
class StructureEvent:
    index: int
    time: datetime
    kind: EventKind
    direction: Literal["bullish", "bearish"]
    broken_level: Decimal


@dataclass(frozen=True)
class StructureState:
    trend: Trend
    events: tuple[StructureEvent, ...]

    @property
    def last_event(self) -> StructureEvent | None:
        return self.events[-1] if self.events else None


def analyze_structure(candles: list[Candle], swing_k: int = 2) -> StructureState:
    swings = detect_swings(candles, k=swing_k)
    confirmed_at: dict[int, list[Swing]] = defaultdict(list)
    for s in swings:
        confirmed_at[s.confirm_index].append(s)

    trend: Trend = "range"
    ref_high: Swing | None = None
    ref_low: Swing | None = None
    events: list[StructureEvent] = []

    for i, candle in enumerate(candles):
        for s in confirmed_at.get(i, ()):
            if s.kind == "high":
                ref_high = s
            else:
                ref_low = s

        if ref_high is not None and candle.close > ref_high.price:
            kind: EventKind = "CHoCH" if trend == "bearish" else "BOS"
            events.append(
                StructureEvent(
                    index=i,
                    time=candle.open_time,
                    kind=kind,
                    direction="bullish",
                    broken_level=ref_high.price,
                )
            )
            trend = "bullish"
            ref_high = None
        elif ref_low is not None and candle.close < ref_low.price:
            kind = "CHoCH" if trend == "bullish" else "BOS"
            events.append(
                StructureEvent(
                    index=i,
                    time=candle.open_time,
                    kind=kind,
                    direction="bearish",
                    broken_level=ref_low.price,
                )
            )
            trend = "bearish"
            ref_low = None

    return StructureState(trend=trend, events=tuple(events))


def premium_discount(
    candles: list[Candle], swings: list[Swing]
) -> Literal["premium", "discount", "equilibrium"]:
    """Position of the last close inside the current dealing range.

    Dealing range = most recent confirmed swing high vs most recent confirmed
    swing low. Above 62% of the range = premium, below 38% = discount.
    """
    if not candles:
        return "equilibrium"
    last_high = next((s for s in reversed(swings) if s.kind == "high"), None)
    last_low = next((s for s in reversed(swings) if s.kind == "low"), None)
    if last_high is None or last_low is None or last_high.price <= last_low.price:
        return "equilibrium"
    close = candles[-1].close
    position = (close - last_low.price) / (last_high.price - last_low.price)
    if position > Decimal("0.62"):
        return "premium"
    if position < Decimal("0.38"):
        return "discount"
    return "equilibrium"

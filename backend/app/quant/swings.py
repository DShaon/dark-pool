"""Fractal swing detection — the primitive under structure, liquidity, and zones.

A swing high at index i means high[i] is strictly greater than the highs of the
k candles on each side (mirror for lows). A pivot is only *confirmed* k candles
later; `confirm_index` records that, and every downstream consumer iterates in
confirmation order so nothing in the engine ever looks into the future.
Exact-equal neighboring extremes do not register as pivots (strict inequality);
equal-high/low *liquidity* is handled by tolerance grouping in liquidity.py.
"""

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from typing import Literal

from app.models.market import Candle


@dataclass(frozen=True)
class Swing:
    index: int
    confirm_index: int
    time: datetime
    price: Decimal
    kind: Literal["high", "low"]


def detect_swings(candles: list[Candle], k: int = 2) -> list[Swing]:
    """Return confirmed fractal pivots in index order."""
    if k < 1:
        raise ValueError("k must be >= 1")
    swings: list[Swing] = []
    for i in range(k, len(candles) - k):
        c = candles[i]
        window = candles[i - k : i] + candles[i + 1 : i + k + 1]
        if all(c.high > w.high for w in window):
            swings.append(
                Swing(index=i, confirm_index=i + k, time=c.open_time, price=c.high, kind="high")
            )
        if all(c.low < w.low for w in window):
            swings.append(
                Swing(index=i, confirm_index=i + k, time=c.open_time, price=c.low, kind="low")
            )
    return swings

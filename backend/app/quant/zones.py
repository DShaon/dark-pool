"""SMC zones: order blocks and fair value gaps, with mitigation tracking.

Definitions used (documented so tests and traders agree):

- **Bullish order block** — the last down-close candle immediately preceding a
  bullish *displacement* candle (body > `displacement_factor` x ATR) that also
  closes above the high of the two candles before it. Zone = that down candle's
  full range [low, high]. Mirror for bearish.
- **Bullish FVG** — three-candle imbalance: low of candle i+1 strictly above
  high of candle i-1. Zone = [high(i-1), low(i+1)]. Mirror for bearish. Gaps
  smaller than `min_gap_atr` x ATR are noise and skipped.
- **Mitigated** — price traded back into the zone *after it finished forming*
  (after the displacement candle for OBs; after the third candle for FVGs).
- **Invalidated / filled** — a close through the far side; such zones are dropped.
"""

from dataclasses import dataclass, replace
from datetime import datetime
from decimal import Decimal
from typing import Literal

from app.models.market import Candle

ZoneKind = Literal["order_block", "fvg"]
Side = Literal["bullish", "bearish"]


@dataclass(frozen=True)
class Zone:
    kind: ZoneKind
    side: Side
    top: Decimal
    bottom: Decimal
    index: int  # origin candle index
    time: datetime
    mitigated: bool = False


def _body(c: Candle) -> Decimal:
    return abs(c.close - c.open)


def detect_order_blocks(
    candles: list[Candle],
    atr: list[float | None],
    displacement_factor: float = 1.3,
    lookback: int = 3,
) -> list[Zone]:
    """Active (non-invalidated) order blocks, ordered by origin index."""
    # keyed by (origin, side); value = (zone, first index at which mitigation counts)
    found: dict[tuple[int, Side], tuple[Zone, int]] = {}
    n = len(candles)
    for i in range(1, n):
        a = atr[i] if i < len(atr) else None
        if a is None or a <= 0:
            continue
        c = candles[i]
        if float(_body(c)) <= displacement_factor * a:
            continue

        if c.close > c.open:  # bullish displacement
            prior_high = max(x.high for x in candles[max(0, i - 2) : i])
            if c.close <= prior_high:
                continue
            origin = next(
                (
                    j
                    for j in range(i - 1, max(0, i - lookback) - 1, -1)
                    if candles[j].close < candles[j].open
                ),
                None,
            )
            if origin is not None:
                o = candles[origin]
                zone = Zone("order_block", "bullish", o.high, o.low, origin, o.open_time)
                found[(origin, "bullish")] = (zone, i + 1)
        else:  # bearish displacement
            prior_low = min(x.low for x in candles[max(0, i - 2) : i])
            if c.close >= prior_low:
                continue
            origin = next(
                (
                    j
                    for j in range(i - 1, max(0, i - lookback) - 1, -1)
                    if candles[j].close > candles[j].open
                ),
                None,
            )
            if origin is not None:
                o = candles[origin]
                zone = Zone("order_block", "bearish", o.high, o.low, origin, o.open_time)
                found[(origin, "bearish")] = (zone, i + 1)

    return _track_mitigation(list(found.values()), candles)


def detect_fvgs(
    candles: list[Candle],
    atr: list[float | None],
    min_gap_atr: float = 0.1,
) -> list[Zone]:
    """Active (unfilled) fair value gaps, ordered by origin index."""
    found: list[tuple[Zone, int]] = []
    for i in range(1, len(candles) - 1):
        prev, nxt = candles[i - 1], candles[i + 1]
        a = atr[i] if i < len(atr) else None
        threshold = Decimal(str((a or 0.0) * min_gap_atr))

        if nxt.low > prev.high and (nxt.low - prev.high) > threshold:
            zone = Zone("fvg", "bullish", nxt.low, prev.high, i, candles[i].open_time)
            found.append((zone, i + 2))  # gap completes with candle i+1
        elif nxt.high < prev.low and (prev.low - nxt.high) > threshold:
            zone = Zone("fvg", "bearish", prev.low, nxt.high, i, candles[i].open_time)
            found.append((zone, i + 2))

    return _track_mitigation(found, candles)


def _track_mitigation(
    zones_with_start: list[tuple[Zone, int]], candles: list[Candle]
) -> list[Zone]:
    """Walk candles from each zone's activation index; mark mitigated, drop broken."""
    survivors: list[Zone] = []
    for zone, start in sorted(zones_with_start, key=lambda pair: pair[0].index):
        mitigated = False
        invalidated = False
        for c in candles[start:]:
            if zone.side == "bullish":
                if c.close < zone.bottom:
                    invalidated = True
                    break
                if c.low <= zone.top:
                    mitigated = True
            else:
                if c.close > zone.top:
                    invalidated = True
                    break
                if c.high >= zone.bottom:
                    mitigated = True
        if not invalidated:
            survivors.append(replace(zone, mitigated=mitigated))
    return survivors

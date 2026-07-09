"""Liquidity levels: prior-day/week extremes and equal highs/lows, with sweep state.

State semantics (chronological walk after the level exists):
- **broken** — a candle *closed* through the level: it is structure now, not liquidity.
- **swept**  — a wick traded through but the candle closed back on the near side
  (a stop hunt / liquidity grab). A later close-through still upgrades to broken.
- **intact** — untouched.
"""

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from typing import Literal

from app.models.market import Candle
from app.quant.swings import Swing

LevelKind = Literal["PDH", "PDL", "PWH", "PWL", "EQH", "EQL"]
LevelState = Literal["intact", "swept", "broken"]


@dataclass(frozen=True)
class Level:
    kind: LevelKind
    price: Decimal
    state: LevelState
    time: datetime | None = None


def _walk_state(
    price: Decimal, side: Literal["above", "below"], candles: list[Candle]
) -> LevelState:
    swept = False
    for c in candles:
        if side == "above":
            if c.close > price:
                return "broken"
            if c.high > price:
                swept = True
        else:
            if c.close < price:
                return "broken"
            if c.low < price:
                swept = True
    return "swept" if swept else "intact"


def daily_weekly_levels(
    daily_candles: list[Candle], intraday_candles: list[Candle]
) -> list[Level]:
    """PDH/PDL from the previous completed day; PWH/PWL from the prior 7 completed
    days. Sweep state is evaluated against intraday candles of the current day."""
    if len(daily_candles) < 2:
        return []
    prev_day = daily_candles[-2]
    day_start = daily_candles[-1].open_time
    todays = [c for c in intraday_candles if c.open_time >= day_start]

    levels = [
        Level("PDH", prev_day.high, _walk_state(prev_day.high, "above", todays), prev_day.open_time),
        Level("PDL", prev_day.low, _walk_state(prev_day.low, "below", todays), prev_day.open_time),
    ]

    week = daily_candles[-8:-1]
    if week:
        pwh = max(c.high for c in week)
        pwl = min(c.low for c in week)
        levels.append(Level("PWH", pwh, _walk_state(pwh, "above", todays)))
        levels.append(Level("PWL", pwl, _walk_state(pwl, "below", todays)))
    return levels


def equal_levels(
    swings: list[Swing],
    candles: list[Candle],
    tolerance_pct: float = 0.0008,
    min_members: int = 2,
) -> list[Level]:
    """Cluster same-kind pivots within a relative tolerance into EQH/EQL pools."""
    tol = Decimal(str(tolerance_pct))
    levels: list[Level] = []

    for kind, level_kind, side in (("high", "EQH", "above"), ("low", "EQL", "below")):
        pivots = [s for s in swings if s.kind == kind]
        cluster: list[Swing] = []

        def flush(cluster: list[Swing]) -> None:
            if len(cluster) < min_members:
                return
            price = (
                max(s.price for s in cluster)
                if level_kind == "EQH"
                else min(s.price for s in cluster)
            )
            start = max(s.confirm_index for s in cluster) + 1
            levels.append(
                Level(
                    level_kind,  # type: ignore[arg-type]
                    price,
                    _walk_state(price, side, candles[start:]),  # type: ignore[arg-type]
                    cluster[-1].time,
                )
            )

        for pivot in pivots:
            if not cluster:
                cluster = [pivot]
                continue
            ref = cluster[-1].price
            if ref > 0 and abs(pivot.price - ref) / ref <= tol:
                cluster.append(pivot)
            else:
                flush(cluster)
                cluster = [pivot]
        flush(cluster)

    return levels

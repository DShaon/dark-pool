"""Trade outcome grading (P3 · FR-6) — deterministic, no AI.

Pure function: candles in, an outcome out. Walks candles in time order; a
trade grades "tp" at the first candle whose range reaches the target, "sl" at
the first whose range reaches the stop — whichever comes first. No candle
reaching either level yet means "open".

The one genuine ambiguity: a single candle's high/low range can contain BOTH
levels (common on volatile crypto, especially coarser timeframes) — OHLC data
alone cannot say which was touched first within that bar. The caller may pass
`resolve_ambiguous`, an async callback that fetches FINER candles for just
that bar's time window, so the tie is usually resolved for real instead of
guessed. If resolution is unavailable, or the finer data is itself still
ambiguous, the documented default applies: assume the stop was hit first —
the same conservative assumption standard backtesting frameworks use, since
assuming the better outcome would silently overstate performance.
"""

from dataclasses import dataclass
from decimal import Decimal
from typing import Awaitable, Callable, Literal

from app.models.market import Candle

Direction = Literal["long", "short"]


def _touches(candle: Candle, level: Decimal, direction: Direction, *, is_stop: bool) -> bool:
    """Does this candle's range reach `level`, given the trade's direction?
    Long: stop sits below entry (hit on a low), target sits above (hit on a
    high). Short: mirrored."""
    below = is_stop if direction == "long" else not is_stop
    return candle.low <= level if below else candle.high >= level


@dataclass(frozen=True)
class GradeOutcome:
    outcome: Literal["tp", "sl", "open"]
    hit_at: str | None  # candle.open_time.isoformat(), or None if still open
    candles_checked: int


ResolveAmbiguous = Callable[[Candle], Awaitable[list[Candle] | None]]


async def grade_candles(
    candles: list[Candle],
    direction: Direction,
    stop: Decimal,
    target: Decimal,
    resolve_ambiguous: ResolveAmbiguous | None = None,
) -> GradeOutcome:
    for i, candle in enumerate(candles):
        hit_stop = _touches(candle, stop, direction, is_stop=True)
        hit_target = _touches(candle, target, direction, is_stop=False)

        if hit_stop and hit_target:
            if resolve_ambiguous is not None:
                finer = await resolve_ambiguous(candle)
                if finer:
                    inner = await grade_candles(finer, direction, stop, target)
                    if inner.outcome != "open":
                        return GradeOutcome(inner.outcome, inner.hit_at, i + 1)
            # Still ambiguous even at finer granularity (or none available).
            return GradeOutcome("sl", candle.open_time.isoformat(), i + 1)
        if hit_stop:
            return GradeOutcome("sl", candle.open_time.isoformat(), i + 1)
        if hit_target:
            return GradeOutcome("tp", candle.open_time.isoformat(), i + 1)

    return GradeOutcome("open", None, len(candles))

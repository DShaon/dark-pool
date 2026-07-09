"""Grading service (P3 · FR-6) — fetches candles, calls the pure grader.

Primary interval is 15m (fine enough to catch most crossings without pulling
excessive history); an ambiguous bar (both stop and target in range) drills
down to 1m for that specific window to resolve it for real. A single
1000-candle page covers ~10.4 days at 15m — grading a trade saved further
back than that may report "open" even if it was actually decided, since this
does not paginate further (a stated boundary, not a silent gap).
"""

from datetime import datetime
from decimal import Decimal

from app.adapters.base import AdapterError
from app.adapters.binance import BinanceAdapter
from app.models.market import Candle
from app.quant.grading import Direction, GradeOutcome, grade_candles

PRIMARY_INTERVAL = "15m"
DRILLDOWN_INTERVAL = "1m"
MAX_CANDLES = 1000


class GradingService:
    def __init__(self, spot: BinanceAdapter) -> None:
        self._spot = spot

    async def grade(
        self,
        symbol: str,
        direction: Direction,
        stop: Decimal,
        target: Decimal,
        since: datetime,
    ) -> GradeOutcome:
        candles = await self._spot.get_klines(
            symbol, interval=PRIMARY_INTERVAL, limit=MAX_CANDLES, start_time=since
        )

        async def resolve_ambiguous(candle: Candle) -> list[Candle] | None:
            try:
                return await self._spot.get_klines(
                    symbol,
                    interval=DRILLDOWN_INTERVAL,
                    limit=MAX_CANDLES,
                    start_time=candle.open_time,
                    end_time=candle.close_time,
                )
            except AdapterError:
                return None  # drill-down failed — fall back to the conservative default

        return await grade_candles(candles, direction, stop, target, resolve_ambiguous)

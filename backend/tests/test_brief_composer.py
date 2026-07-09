"""Brief composer integration test — fake adapters, real engine, no network.

Verifies the NFR-3 degradation contract (a failing context source becomes a
noted gap, never a failed run) and the JSON round-trip serialization contract.
"""

from datetime import datetime, timedelta, timezone
from decimal import Decimal

from app.adapters.base import AdapterError
from app.models.brief import MarketBrief
from app.models.market import Candle
from app.quant.brief import BriefComposer

T0 = datetime(2026, 1, 1, tzinfo=timezone.utc)


def series(n: int, step_hours: int) -> list[Candle]:
    out = []
    for i in range(n):
        base = Decimal(100 + i)
        out.append(
            Candle(
                open_time=T0 + timedelta(hours=i * step_hours),
                open=base,
                high=base + Decimal("1"),
                low=base - Decimal("0.2"),
                close=base + Decimal("0.8"),
                volume=Decimal("5"),
                close_time=T0 + timedelta(hours=(i + 1) * step_hours, milliseconds=-1),
            )
        )
    return out


class FakeSpot:
    async def get_klines(self, symbol: str, interval: str = "1h", limit: int = 100):
        steps = {"5m": 1, "15m": 1, "1h": 1, "4h": 4, "1d": 24}
        return series(min(limit, 60), steps[interval])


class FakeFuturesDown:
    """Spot-only symbol: every futures call fails."""

    async def get_funding(self, symbol: str):
        raise AdapterError("binance_futures", "no futures market")

    async def get_open_interest_change(self, symbol: str):
        raise AdapterError("binance_futures", "no futures market")

    async def get_long_short_ratio(self, symbol: str):
        raise AdapterError("binance_futures", "no futures market")


class FakeSentiment:
    async def get_fear_greed(self):
        return 25, "Extreme Fear"


async def test_compose_degrades_gracefully_and_round_trips():
    composer = BriefComposer(FakeSpot(), FakeFuturesDown(), FakeSentiment())  # type: ignore[arg-type]
    brief = await composer.compose("btcusdt")

    assert brief.symbol == "BTCUSDT"
    assert set(brief.timeframes) == {"5m", "15m", "1h", "4h", "1d"}
    # Alignment stays computed over the intraday core only (money-risk signal
    # unchanged by the additive 5m/1d context timeframes).
    assert set(brief.alignment.per_tf) == {"15m", "1h", "4h"}
    assert brief.derivatives is None
    assert any("derivatives unavailable" in g for g in brief.gaps)
    assert brief.sentiment is not None and brief.sentiment.fear_greed == 25
    assert brief.alignment.bias in {"long", "short", "mixed"}
    assert brief.daily_levels, "daily levels expected from fake 1d series"

    # Serialization contract: model -> JSON-mode dict -> model must be lossless.
    restored = MarketBrief.model_validate(brief.model_dump(mode="json"))
    assert restored.symbol == brief.symbol
    assert restored.timeframes["1h"].last_close == brief.timeframes["1h"].last_close

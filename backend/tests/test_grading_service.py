"""GradingService tests — fake adapter, no network.

Confirms the service fetches the primary window from `since`, drives the pure
grader correctly, and that a failing drill-down degrades to the conservative
default rather than raising (the grader already covers that path directly;
this proves the service wires it the same way end-to-end).
"""

from datetime import datetime, timedelta, timezone
from decimal import Decimal

from app.adapters.base import AdapterError
from app.models.market import Candle
from app.quant.grading_service import GradingService

T0 = datetime(2026, 7, 1, tzinfo=timezone.utc)


def candle(hours: int, o: str, h: str, low: str, c: str) -> Candle:
    return Candle(
        open_time=T0 + timedelta(hours=hours),
        open=Decimal(o), high=Decimal(h), low=Decimal(low), close=Decimal(c),
        volume=Decimal("10"),
        close_time=T0 + timedelta(hours=hours + 1, milliseconds=-1),
    )


class FakeSpot:
    def __init__(self, primary: list[Candle], drilldown: list[Candle] | None = None, fail_drilldown=False):
        self.primary = primary
        self.drilldown = drilldown
        self.fail_drilldown = fail_drilldown
        self.calls: list[dict] = []

    async def get_klines(self, symbol, interval="1h", limit=100, start_time=None, end_time=None):
        self.calls.append({"interval": interval, "start_time": start_time, "end_time": end_time})
        if interval == "1m":
            if self.fail_drilldown:
                raise AdapterError("fake", "drilldown failed")
            return self.drilldown or []
        return self.primary


async def test_service_fetches_since_and_grades():
    primary = [candle(0, "100", "105", "98", "103"), candle(1, "103", "121", "102", "118")]
    spot = FakeSpot(primary)
    service = GradingService(spot)  # type: ignore[arg-type]

    result = await service.grade("BTCUSDT", "long", Decimal("90"), Decimal("120"), since=T0)

    assert result.outcome == "tp"
    assert spot.calls[0]["interval"] == "15m"
    assert spot.calls[0]["start_time"] == T0


async def test_service_drills_down_on_ambiguous_bar():
    ambiguous = candle(0, "100", "121", "89", "115")
    finer = [
        Candle(open_time=T0, open=Decimal("100"), high=Decimal("121"), low=Decimal("100"),
               close=Decimal("120"), volume=Decimal("1"), close_time=T0 + timedelta(minutes=1)),
    ]
    spot = FakeSpot([ambiguous], drilldown=finer)
    service = GradingService(spot)  # type: ignore[arg-type]

    result = await service.grade("BTCUSDT", "long", Decimal("90"), Decimal("120"), since=T0)

    assert result.outcome == "tp"
    assert any(c["interval"] == "1m" for c in spot.calls)


async def test_service_falls_back_when_drilldown_fetch_fails():
    ambiguous = candle(0, "100", "121", "89", "115")
    spot = FakeSpot([ambiguous], fail_drilldown=True)
    service = GradingService(spot)  # type: ignore[arg-type]

    result = await service.grade("BTCUSDT", "long", Decimal("90"), Decimal("120"), since=T0)

    assert result.outcome == "sl"  # conservative default, no crash

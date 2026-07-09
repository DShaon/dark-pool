"""`/grade/{symbol}` route tests — GradingService swapped onto app.state
(same pattern as test_api.py's FakeBinance)."""

from datetime import datetime, timedelta, timezone
from decimal import Decimal

from fastapi.testclient import TestClient

from app.main import create_app
from app.models.market import Candle
from app.quant.grading_service import GradingService

T0 = datetime(2026, 7, 1, tzinfo=timezone.utc)


class FakeSpot:
    def __init__(self, candles):
        self.candles = candles

    async def get_klines(self, symbol, interval="1h", limit=100, start_time=None, end_time=None):
        return [] if interval == "1m" else self.candles


def candle(hours, o, h, low, c):
    return Candle(
        open_time=T0 + timedelta(hours=hours),
        open=Decimal(o), high=Decimal(h), low=Decimal(low), close=Decimal(c),
        volume=Decimal("1"), close_time=T0 + timedelta(hours=hours + 1, milliseconds=-1),
    )


def test_grade_returns_tp_for_a_winning_long(tmp_path):
    app = create_app()
    with TestClient(app) as client:
        candles = [candle(0, "100", "105", "98", "103"), candle(1, "103", "121", "102", "118")]
        app.state.grading_service = GradingService(FakeSpot(candles))  # type: ignore[arg-type]

        resp = client.get(
            "/grade/BTCUSDT",
            params={
                "direction": "long", "stop": "90", "target": "120",
                "since": T0.isoformat(),
            },
        )
    assert resp.status_code == 200
    body = resp.json()
    assert body["outcome"] == "tp"
    assert body["symbol"] == "BTCUSDT"
    assert body["candles_checked"] == 2


def test_grade_still_open(tmp_path):
    app = create_app()
    with TestClient(app) as client:
        app.state.grading_service = GradingService(
            FakeSpot([candle(0, "100", "105", "98", "103")])  # type: ignore[arg-type]
        )
        resp = client.get(
            "/grade/ETHUSDT",
            params={"direction": "short", "stop": "110", "target": "90", "since": T0.isoformat()},
        )
    assert resp.status_code == 200
    assert resp.json()["outcome"] == "open"
    assert resp.json()["hit_at"] is None


def test_grade_rejects_bad_symbol(tmp_path):
    app = create_app()
    with TestClient(app) as client:
        app.state.grading_service = GradingService(FakeSpot([]))  # type: ignore[arg-type]
        resp = client.get(
            "/grade/bt!",
            params={"direction": "long", "stop": "1", "target": "2", "since": T0.isoformat()},
        )
    assert resp.status_code == 422

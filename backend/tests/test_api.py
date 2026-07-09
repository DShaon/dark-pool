"""API route tests — fake adapter injected on app.state; no live network."""

from datetime import datetime, timezone
from decimal import Decimal

from fastapi.testclient import TestClient

from app.adapters.base import AdapterError
from app.main import create_app
from app.models.market import Ticker


class FakeBinance:
    """Stands in for BinanceAdapter on app.state (same duck type)."""

    def __init__(self, fail: bool = False) -> None:
        self.fail = fail
        self.calls = 0

    async def get_ticker(self, symbol: str) -> Ticker:
        self.calls += 1
        if self.fail:
            raise AdapterError("binance", "simulated outage")
        return Ticker(
            symbol=symbol.upper(),
            price=Decimal("64123.45"),
            ts=datetime.now(timezone.utc),
        )

    async def aclose(self) -> None:  # pragma: no cover - lifecycle no-op
        pass


def test_health_reports_ok():
    app = create_app()
    with TestClient(app) as client:
        resp = client.get("/health")
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "ok"
    assert body["app"] == "DARKPOOL"
    assert body["cache"] == "MemoryCache"


def test_price_returns_decimal_as_string_and_caches():
    app = create_app()
    with TestClient(app) as client:
        fake = FakeBinance()
        app.state.binance = fake

        first = client.get("/price/btcusdt")
        assert first.status_code == 200
        body = first.json()
        assert body["symbol"] == "BTCUSDT"
        # Decimal precision is part of the API contract: JSON string, not float.
        assert body["price"] == "64123.45"
        assert isinstance(body["price"], str)

        second = client.get("/price/BTCUSDT")
        assert second.status_code == 200
        assert fake.calls == 1  # second hit served from cache (TTL 2s)


def test_price_invalid_symbol_is_422():
    app = create_app()
    with TestClient(app) as client:
        app.state.binance = FakeBinance()
        resp = client.get("/price/bt!")
    assert resp.status_code == 422


def test_upstream_failure_maps_to_502():
    app = create_app()
    with TestClient(app) as client:
        app.state.binance = FakeBinance(fail=True)
        resp = client.get("/price/ETHUSDT")
    assert resp.status_code == 502
    assert "binance" in resp.json()["detail"]

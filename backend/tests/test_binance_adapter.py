"""Unit tests for the Binance adapter — mocked transport, no live network."""

from datetime import timezone
from decimal import Decimal

import httpx
import pytest
import respx

from app.adapters.base import AdapterError
from app.adapters.binance import BinanceAdapter

BASE = "https://mock.binance.test"


@respx.mock
async def test_get_ticker_parses_decimal_and_utc():
    respx.get(f"{BASE}/api/v3/ticker/price").mock(
        return_value=httpx.Response(
            200, json={"symbol": "BTCUSDT", "price": "64123.45000000"}
        )
    )
    adapter = BinanceAdapter(base_url=BASE)
    try:
        ticker = await adapter.get_ticker("btcusdt")  # lowercase in → uppercased out
    finally:
        await adapter.aclose()

    assert ticker.symbol == "BTCUSDT"
    assert ticker.price == Decimal("64123.45")
    assert isinstance(ticker.price, Decimal)
    assert ticker.ts.tzinfo == timezone.utc


@respx.mock
async def test_get_klines_parses_rows_oldest_first():
    row = [
        1719946800000, "61000.00", "61500.10", "60900.00", "61400.00",
        "1234.56789000", 1719950399999, "0", 0, "0", "0", "0",
    ]
    respx.get(f"{BASE}/api/v3/klines").mock(
        return_value=httpx.Response(200, json=[row, row])
    )
    adapter = BinanceAdapter(base_url=BASE)
    try:
        candles = await adapter.get_klines("BTCUSDT", interval="1h", limit=2)
    finally:
        await adapter.aclose()

    assert len(candles) == 2
    candle = candles[0]
    assert candle.open == Decimal("61000.00")
    assert candle.high == Decimal("61500.10")
    assert candle.volume == Decimal("1234.56789")
    assert candle.open_time.tzinfo == timezone.utc
    assert candle.close_time > candle.open_time


@respx.mock
async def test_upstream_http_error_becomes_adapter_error():
    respx.get(f"{BASE}/api/v3/ticker/price").mock(
        return_value=httpx.Response(400, json={"code": -1121, "msg": "Invalid symbol."})
    )
    adapter = BinanceAdapter(base_url=BASE)
    try:
        with pytest.raises(AdapterError) as excinfo:
            await adapter.get_ticker("NOPEUSDT")
    finally:
        await adapter.aclose()
    assert excinfo.value.provider == "binance"
    assert "400" in str(excinfo.value)


@respx.mock
async def test_malformed_payload_becomes_adapter_error():
    respx.get(f"{BASE}/api/v3/ticker/price").mock(
        return_value=httpx.Response(200, json={"unexpected": "shape"})
    )
    adapter = BinanceAdapter(base_url=BASE)
    try:
        with pytest.raises(AdapterError):
            await adapter.get_ticker("BTCUSDT")
    finally:
        await adapter.aclose()


async def test_invalid_interval_rejected_before_network():
    adapter = BinanceAdapter(base_url=BASE)
    try:
        with pytest.raises(ValueError):
            await adapter.get_klines("BTCUSDT", interval="7m")
    finally:
        await adapter.aclose()


@respx.mock
async def test_get_klines_forwards_start_and_end_time():
    from datetime import datetime, timezone

    row = [
        1719946800000, "61000.00", "61500.10", "60900.00", "61400.00",
        "1234.56789000", 1719950399999, "0", 0, "0", "0", "0",
    ]
    route = respx.get(f"{BASE}/api/v3/klines").mock(return_value=httpx.Response(200, json=[row]))
    adapter = BinanceAdapter(base_url=BASE)
    start = datetime(2026, 7, 1, tzinfo=timezone.utc)
    end = datetime(2026, 7, 2, tzinfo=timezone.utc)
    try:
        await adapter.get_klines("BTCUSDT", interval="15m", start_time=start, end_time=end)
    finally:
        await adapter.aclose()

    sent = route.calls.last.request.url.params
    assert sent["startTime"] == str(int(start.timestamp() * 1000))
    assert sent["endTime"] == str(int(end.timestamp() * 1000))

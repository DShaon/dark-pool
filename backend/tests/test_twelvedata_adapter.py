"""Twelve Data forex adapter tests — mocked transport, no live network.

Verifies the response is parsed into the SAME Candle shape as Binance, that
newest-first values are reversed to oldest-first, zero/absent volume is handled
(forex has none), the symbol is slash-formatted, and Twelve Data's HTTP-200
error envelope becomes an AdapterError.
"""

from datetime import timezone
from decimal import Decimal

import httpx
import pytest
import respx

from app.adapters.base import AdapterError
from app.adapters.twelvedata import TwelveDataAdapter

BASE = "https://mock.td.test"

# Twelve Data returns values NEWEST-first; no volume for forex spot.
TS_OK = {
    "meta": {"symbol": "EUR/USD", "interval": "1h"},
    "values": [
        {"datetime": "2026-07-09 18:00:00", "open": "1.14337", "high": "1.14388", "low": "1.14337", "close": "1.14372"},
        {"datetime": "2026-07-09 17:00:00", "open": "1.14410", "high": "1.14424", "low": "1.14322", "close": "1.14326"},
    ],
    "status": "ok",
}


@respx.mock
async def test_klines_parsed_reversed_and_slash_symbol():
    route = respx.get(f"{BASE}/time_series").mock(return_value=httpx.Response(200, json=TS_OK))
    adapter = TwelveDataAdapter(api_key="demo", base_url=BASE)
    try:
        candles = await adapter.get_klines("EURUSD", interval="1h", limit=2)
    finally:
        await adapter.aclose()

    # slash-formatted symbol + UTC timezone were requested
    sent = route.calls.last.request.url.params
    assert sent["symbol"] == "EUR/USD"
    assert sent["timezone"] == "UTC"
    assert sent["apikey"] == "demo"

    assert len(candles) == 2
    # reversed to oldest-first: the 17:00 bar now comes first
    assert candles[0].open == Decimal("1.14410")
    assert candles[1].close == Decimal("1.14372")
    assert candles[0].volume == Decimal("0")  # forex has no consolidated volume
    assert candles[0].open_time.tzinfo == timezone.utc
    assert candles[0].close_time > candles[0].open_time


@respx.mock
async def test_error_envelope_becomes_adapter_error():
    respx.get(f"{BASE}/time_series").mock(
        return_value=httpx.Response(200, json={"code": 401, "message": "get your own key", "status": "error"})
    )
    adapter = TwelveDataAdapter(api_key="demo", base_url=BASE)
    try:
        with pytest.raises(AdapterError, match="get your own key"):
            await adapter.get_klines("GBPUSD", interval="1h")
    finally:
        await adapter.aclose()


async def test_unsupported_interval_rejected_before_network():
    adapter = TwelveDataAdapter(api_key="demo", base_url=BASE)
    try:
        with pytest.raises(ValueError):
            await adapter.get_klines("EURUSD", interval="3m")  # crypto-only interval
    finally:
        await adapter.aclose()


@respx.mock
async def test_daily_bars_use_date_only_datetime():
    # 1day bars come back as "YYYY-MM-DD" (no time) — must still parse to UTC midnight.
    daily = {
        "meta": {"symbol": "EUR/USD", "interval": "1day"},
        "values": [{"datetime": "2026-07-09", "open": "1.14167", "high": "1.14494", "low": "1.14160", "close": "1.14335"}],
        "status": "ok",
    }
    respx.get(f"{BASE}/time_series").mock(return_value=httpx.Response(200, json=daily))
    adapter = TwelveDataAdapter(api_key="demo", base_url=BASE)
    try:
        candles = await adapter.get_klines("EURUSD", interval="1d", limit=1)
    finally:
        await adapter.aclose()
    assert len(candles) == 1
    assert candles[0].open_time.tzinfo == timezone.utc
    assert candles[0].open_time.hour == 0
    assert candles[0].close == Decimal("1.14335")


@respx.mock
async def test_interval_is_mapped_to_twelvedata_spelling():
    route = respx.get(f"{BASE}/time_series").mock(return_value=httpx.Response(200, json=TS_OK))
    adapter = TwelveDataAdapter(api_key="k", base_url=BASE)
    try:
        await adapter.get_klines("EURUSD", interval="1d", limit=2)
    finally:
        await adapter.aclose()
    assert route.calls.last.request.url.params["interval"] == "1day"

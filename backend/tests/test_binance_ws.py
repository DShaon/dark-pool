"""BinanceStreamHub tests — kline parsing + subscribe/unsubscribe/dispatch
bookkeeping, no real socket (`_send_control` is a safe no-op while
`self._ws is None`, which is exactly the state in these tests). The upstream
reconnect loop (`run()`) does real network I/O and is proven separately by a
live smoke test against Binance itself (see STATUS.md), not unit-tested here.
"""

import json
from decimal import Decimal

from app.adapters.binance_ws import QUEUE_MAXSIZE, BinanceStreamHub, _parse_ws_kline

RAW_KLINE = {
    "t": 1719946800000, "T": 1719950399999, "s": "BTCUSDT", "i": "1h",
    "o": "61000.00", "c": "61400.00", "h": "61500.10", "l": "60900.00",
    "v": "1234.5", "x": False,
}


def _kline_msg(stream: str = "btcusdt@kline_1h", k: dict = RAW_KLINE) -> str:
    return json.dumps({"stream": stream, "data": {"e": "kline", "k": k}})


def test_parse_ws_kline_matches_rest_shape():
    candle = _parse_ws_kline(RAW_KLINE)
    assert candle.open == Decimal("61000.00")
    assert candle.close == Decimal("61400.00")
    assert candle.high == Decimal("61500.10")
    assert candle.low == Decimal("60900.00")
    assert candle.volume == Decimal("1234.5")
    assert candle.close_time > candle.open_time


async def test_subscribe_registers_queue_and_dispatch_routes_to_it():
    hub = BinanceStreamHub()
    queue = await hub.subscribe("btcusdt@kline_1h")

    await hub._dispatch(_kline_msg())

    candle = queue.get_nowait()
    assert candle.close == Decimal("61400.00")


async def test_dispatch_ignores_non_kline_wrong_stream_and_malformed_json():
    hub = BinanceStreamHub()
    queue = await hub.subscribe("btcusdt@kline_1h")

    await hub._dispatch(json.dumps({"stream": "btcusdt@kline_1h", "data": {"e": "trade"}}))
    await hub._dispatch(_kline_msg(stream="ethusdt@kline_1h"))  # nobody subscribed to this
    await hub._dispatch("not json")

    assert queue.empty()


async def test_dispatch_never_grows_the_queue_past_its_cap():
    hub = BinanceStreamHub()
    queue = await hub.subscribe("btcusdt@kline_1h")

    for _ in range(QUEUE_MAXSIZE + 5):
        await hub._dispatch(_kline_msg())

    assert queue.qsize() <= QUEUE_MAXSIZE


async def test_unsubscribe_stops_further_dispatch_to_that_queue():
    hub = BinanceStreamHub()
    queue = await hub.subscribe("btcusdt@kline_1h")
    await hub.unsubscribe("btcusdt@kline_1h", queue)

    await hub._dispatch(_kline_msg())

    assert queue.empty()


async def test_two_subscribers_to_the_same_stream_both_receive():
    hub = BinanceStreamHub()
    q1 = await hub.subscribe("btcusdt@kline_1h")
    q2 = await hub.subscribe("btcusdt@kline_1h")

    await hub._dispatch(_kline_msg())

    assert not q1.empty()
    assert not q2.empty()

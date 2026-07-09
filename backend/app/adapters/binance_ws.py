"""Binance WebSocket collector (keyless, public combined-stream, invariant 1:
all external I/O lives here, never called directly from a route or the
frontend).

One upstream connection to Binance is shared across however many local
browser clients are watching — each calls `subscribe()` for a stream key
(e.g. `"btcusdt@kline_1h"`) and gets an `asyncio.Queue` that fills with parsed
`Candle`s as ticks arrive. Reconnects on any drop (idle timeout, Binance's
24h forced close, network blip) and re-subscribes everything that was active,
so a local client's queue never goes silently stale.

REST (`BinanceAdapter`) still owns historical backfill — this hub only carries
the live tail from the moment a client subscribes.
"""

from __future__ import annotations

import asyncio
import contextlib
import itertools
import json
import logging
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation

import websockets
from websockets.exceptions import ConnectionClosed

from app.models.market import Candle

logger = logging.getLogger(__name__)

STREAM_URL = "wss://stream.binance.com:9443/stream"
RECONNECT_DELAY_S = 2.0
QUEUE_MAXSIZE = 32  # only the latest tick matters; drop stale ones, never block


def _parse_ws_kline(k: dict) -> Candle:
    return Candle(
        open_time=datetime.fromtimestamp(int(k["t"]) / 1000, tz=timezone.utc),
        open=Decimal(str(k["o"])),
        high=Decimal(str(k["h"])),
        low=Decimal(str(k["l"])),
        close=Decimal(str(k["c"])),
        volume=Decimal(str(k["v"])),
        close_time=datetime.fromtimestamp(int(k["T"]) / 1000, tz=timezone.utc),
    )


class BinanceStreamHub:
    """Start with `asyncio.create_task(hub.run())`; stop by cancelling that
    task (and awaiting `aclose()` to release the socket cleanly)."""

    name = "binance_ws"

    def __init__(self, stream_url: str = STREAM_URL) -> None:
        self._stream_url = stream_url
        self._subscribers: dict[str, set[asyncio.Queue]] = {}
        self._lock = asyncio.Lock()
        self._ws: websockets.asyncio.client.ClientConnection | None = None
        self._id_counter = itertools.count(1)

    async def subscribe(self, stream: str) -> asyncio.Queue:
        queue: asyncio.Queue = asyncio.Queue(maxsize=QUEUE_MAXSIZE)
        async with self._lock:
            is_new = stream not in self._subscribers
            self._subscribers.setdefault(stream, set()).add(queue)
            if is_new:
                await self._send_control("SUBSCRIBE", [stream])
        return queue

    async def unsubscribe(self, stream: str, queue: asyncio.Queue) -> None:
        async with self._lock:
            subs = self._subscribers.get(stream)
            if not subs or queue not in subs:
                return
            subs.discard(queue)
            if not subs:
                del self._subscribers[stream]
                await self._send_control("UNSUBSCRIBE", [stream])

    async def _send_control(self, method: str, params: list[str]) -> None:
        if self._ws is None:
            return  # not connected yet — `run()` re-subscribes everything on connect
        msg = {"method": method, "params": params, "id": next(self._id_counter)}
        with contextlib.suppress(Exception):
            await self._ws.send(json.dumps(msg))

    async def run(self) -> None:
        """Reconnect loop — runs until cancelled."""
        while True:
            try:
                async with websockets.connect(
                    self._stream_url, ping_interval=180, open_timeout=10
                ) as ws:
                    self._ws = ws
                    async with self._lock:
                        streams = list(self._subscribers.keys())
                    if streams:
                        await self._send_control("SUBSCRIBE", streams)
                    async for raw in ws:
                        await self._dispatch(raw)
            except asyncio.CancelledError:
                raise
            except (ConnectionClosed, OSError, TimeoutError) as exc:
                logger.warning("binance ws disconnected: %s — reconnecting", exc)
            finally:
                self._ws = None
            await asyncio.sleep(RECONNECT_DELAY_S)

    async def _dispatch(self, raw: str) -> None:
        try:
            msg = json.loads(raw)
        except json.JSONDecodeError:
            return
        stream = msg.get("stream")
        data = msg.get("data")
        if not stream or not isinstance(data, dict) or data.get("e") != "kline":
            return
        try:
            candle = _parse_ws_kline(data["k"])
        except (KeyError, InvalidOperation, ValueError):
            logger.warning("malformed kline payload on %s", stream)
            return
        async with self._lock:
            queues = list(self._subscribers.get(stream, ()))
        for q in queues:
            if q.full():
                with contextlib.suppress(asyncio.QueueEmpty):
                    q.get_nowait()  # drop the stale tick — only the latest matters
            with contextlib.suppress(asyncio.QueueFull):
                q.put_nowait(candle)

    async def aclose(self) -> None:
        if self._ws is not None:
            with contextlib.suppress(Exception):
                await self._ws.close()

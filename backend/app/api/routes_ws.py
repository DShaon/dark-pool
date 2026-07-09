"""Live kline stream (P3) — browser-facing WebSocket over the shared
`BinanceStreamHub`. REST still owns historical backfill; this carries only
the live tail from the moment a browser tab subscribes.

Auth mirrors the REST bearer check (ADR-0009) but via a query param, since a
browser's `WebSocket` API cannot set custom headers on the handshake.
"""

import re

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from app.adapters.binance import VALID_INTERVALS
from app.config import get_settings

router = APIRouter()

_SYMBOL_RE = re.compile(r"^[A-Z0-9]{5,20}$")


@router.websocket("/ws/kline/{symbol}/{interval}")
async def ws_kline(websocket: WebSocket, symbol: str, interval: str) -> None:
    settings = get_settings()
    if settings.api_token:
        if websocket.query_params.get("token") != settings.api_token:
            await websocket.close(code=4401)
            return

    symbol = symbol.upper()
    if not _SYMBOL_RE.match(symbol) or interval not in VALID_INTERVALS:
        await websocket.close(code=4422)
        return

    await websocket.accept()
    hub = websocket.app.state.stream_hub
    stream = f"{symbol.lower()}@kline_{interval}"
    queue = await hub.subscribe(stream)
    try:
        while True:
            candle = await queue.get()
            await websocket.send_json(candle.model_dump(mode="json"))
    except WebSocketDisconnect:
        pass
    finally:
        await hub.unsubscribe(stream, queue)

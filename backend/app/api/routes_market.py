"""Market data routes: /health, /price/{symbol}, /klines/{symbol}.

Routes never talk to vendors directly — they use the adapter on `app.state`
(ADR-0003) and the cache layer. Upstream failures surface as 502 with the
provider named, never as raw tracebacks (NFR-3).
"""

import re
from datetime import datetime, timezone
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, Request

from app import __version__
from app.adapters.base import AdapterError
from app.adapters.binance import VALID_INTERVALS, BinanceAdapter
from app.config import get_settings
from app.core.cache import Cache
from app.models.market import Candle, Ticker

router = APIRouter()

_SYMBOL_RE = re.compile(r"^[A-Z0-9]{5,20}$")

TICKER_TTL_SECONDS = 2
KLINES_TTL_SECONDS = 10


async def require_auth(request: Request) -> None:
    """Single-user bearer auth (ADR-0009). Disabled when API_TOKEN is unset (dev)."""
    settings = get_settings()
    if not settings.api_token:
        return
    header = request.headers.get("authorization", "")
    if header != f"Bearer {settings.api_token}":
        raise HTTPException(status_code=401, detail="invalid or missing token")


def _adapter(request: Request) -> BinanceAdapter:
    return request.app.state.binance


def _cache(request: Request) -> Cache:
    return request.app.state.cache


def _validate_symbol(symbol: str) -> str:
    symbol = symbol.upper()
    if not _SYMBOL_RE.match(symbol):
        raise HTTPException(status_code=422, detail=f"invalid symbol {symbol!r}")
    return symbol


@router.get("/health")
async def health(request: Request) -> dict:
    settings = get_settings()
    return {
        "status": "ok",
        "app": settings.app_name,
        "version": __version__,
        "environment": settings.environment,
        "cache": type(request.app.state.cache).__name__,
        "time": datetime.now(timezone.utc).isoformat(),
    }


@router.get("/price/{symbol}", response_model=Ticker, dependencies=[Depends(require_auth)])
async def price(symbol: str, request: Request) -> Ticker:
    symbol = _validate_symbol(symbol)
    cache = _cache(request)
    key = f"ticker:{symbol}"

    cached = await cache.get(key)
    if cached is not None:
        return Ticker.model_validate(cached)

    try:
        ticker = await _adapter(request).get_ticker(symbol)
    except AdapterError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc

    await cache.set(key, ticker.model_dump(mode="json"), TICKER_TTL_SECONDS)
    return ticker


@router.get(
    "/klines/{symbol}", response_model=list[Candle], dependencies=[Depends(require_auth)]
)
async def klines(
    symbol: str,
    request: Request,
    interval: Annotated[str, Query()] = "1h",
    limit: Annotated[int, Query(ge=1, le=500)] = 100,
) -> list[Candle]:
    symbol = _validate_symbol(symbol)
    if interval not in VALID_INTERVALS:
        raise HTTPException(status_code=422, detail=f"invalid interval {interval!r}")

    cache = _cache(request)
    key = f"klines:{symbol}:{interval}:{limit}"

    cached = await cache.get(key)
    if cached is not None:
        return [Candle.model_validate(row) for row in cached]

    try:
        candles = await _adapter(request).get_klines(symbol, interval=interval, limit=limit)
    except AdapterError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc

    await cache.set(key, [c.model_dump(mode="json") for c in candles], KLINES_TTL_SECONDS)
    return candles

"""Binance public market data adapter (keyless).

Uses the public data mirror (`data-api.binance.vision`) — no account or API key is
required for market data. Spot weight budget is 6000/min; we self-limit well below
that. All prices are parsed as `Decimal` from Binance's string payloads; all
timestamps are converted from epoch-ms to aware UTC datetimes.
"""

from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from typing import Any

import httpx

from app.adapters.base import AdapterError, DataProvider
from app.core.ratelimit import TokenBucket
from app.models.market import Candle, Ticker

VALID_INTERVALS = {
    "1m", "3m", "5m", "15m", "30m",
    "1h", "2h", "4h", "6h", "8h", "12h",
    "1d", "3d", "1w", "1M",
}

MAX_KLINE_LIMIT = 1000


class BinanceAdapter(DataProvider):
    name = "binance"

    def __init__(
        self,
        base_url: str = "https://data-api.binance.vision",
        requests_per_second: float = 15.0,
    ) -> None:
        self._client = httpx.AsyncClient(base_url=base_url, timeout=10.0)
        self._bucket = TokenBucket(rate=requests_per_second, capacity=requests_per_second)

    async def get_ticker(self, symbol: str) -> Ticker:
        """Latest spot price for a symbol (e.g. BTCUSDT)."""
        data = await self._get("/api/v3/ticker/price", {"symbol": symbol.upper()})
        try:
            return Ticker(
                symbol=str(data["symbol"]),
                price=Decimal(str(data["price"])),
                ts=datetime.now(timezone.utc),
            )
        except (KeyError, TypeError, InvalidOperation) as exc:
            raise AdapterError(self.name, f"malformed ticker payload: {data!r}") from exc

    async def get_klines(
        self,
        symbol: str,
        interval: str = "1h",
        limit: int = 100,
        start_time: datetime | None = None,
        end_time: datetime | None = None,
    ) -> list[Candle]:
        """OHLCV candles, oldest first. `start_time`/`end_time` (UTC) let a
        caller fetch a specific window — e.g. grading a saved trade needs
        candles since it was recorded, not just "the most recent N"."""
        if interval not in VALID_INTERVALS:
            raise ValueError(f"invalid interval {interval!r}; one of {sorted(VALID_INTERVALS)}")
        limit = max(1, min(int(limit), MAX_KLINE_LIMIT))
        params: dict[str, Any] = {"symbol": symbol.upper(), "interval": interval, "limit": limit}
        if start_time is not None:
            params["startTime"] = int(start_time.timestamp() * 1000)
        if end_time is not None:
            params["endTime"] = int(end_time.timestamp() * 1000)
        rows = await self._get("/api/v3/klines", params)
        try:
            return [self._parse_kline(row) for row in rows]
        except (KeyError, IndexError, TypeError, InvalidOperation, ValueError) as exc:
            raise AdapterError(self.name, "malformed klines payload") from exc

    @staticmethod
    def _parse_kline(row: list[Any]) -> Candle:
        return Candle(
            open_time=datetime.fromtimestamp(int(row[0]) / 1000, tz=timezone.utc),
            open=Decimal(str(row[1])),
            high=Decimal(str(row[2])),
            low=Decimal(str(row[3])),
            close=Decimal(str(row[4])),
            volume=Decimal(str(row[5])),
            close_time=datetime.fromtimestamp(int(row[6]) / 1000, tz=timezone.utc),
        )

    async def _get(self, path: str, params: dict[str, Any]) -> Any:
        await self._bucket.acquire()
        try:
            resp = await self._client.get(path, params=params)
            resp.raise_for_status()
            return resp.json()
        except httpx.HTTPStatusError as exc:
            body = exc.response.text[:200]
            raise AdapterError(
                self.name, f"{path} -> HTTP {exc.response.status_code}: {body}"
            ) from exc
        except httpx.HTTPError as exc:
            raise AdapterError(self.name, f"{path} -> transport error: {exc}") from exc

    async def aclose(self) -> None:
        await self._client.aclose()

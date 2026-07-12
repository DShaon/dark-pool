"""Twelve Data forex adapter (P4 · ADR-0003 adapter pattern).

Supplies forex OHLCV in the SAME `Candle` shape as `BinanceAdapter`, so the
deterministic quant engine runs on forex identically to crypto. Free tier: 8
req/min, 800/day, one free lifetime key — but the built-in `demo` key already
serves EUR/USD, so forex works out of the box for that pair and unlocks the
rest the moment `TWELVE_DATA_API_KEY` is set.

Notes vs Binance: forex is decentralized so there is NO consolidated volume —
`volume` is 0 (the engine's VWAP correctly reports `None` on zero volume, and
no fake number is invented). Twelve Data returns candles newest-first; we
reverse to oldest-first to match the rest of the system. `close_time` is
derived from the interval since the API omits it.
"""

from datetime import datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation
from typing import Any

import httpx

from app.adapters.base import AdapterError, DataProvider
from app.core.ratelimit import TokenBucket
from app.markets import to_twelvedata_symbol
from app.models.market import Candle, Ticker

# Our canonical interval -> Twelve Data's spelling + its duration.
_INTERVAL_MAP: dict[str, tuple[str, timedelta]] = {
    "5m": ("5min", timedelta(minutes=5)),
    "15m": ("15min", timedelta(minutes=15)),
    "1h": ("1h", timedelta(hours=1)),
    "4h": ("4h", timedelta(hours=4)),
    "1d": ("1day", timedelta(days=1)),
}

MAX_OUTPUTSIZE = 5000


class TwelveDataAdapter(DataProvider):
    name = "twelvedata"

    def __init__(
        self,
        api_key: str = "demo",
        base_url: str = "https://api.twelvedata.com",
        requests_per_second: float = 0.13,  # ~8/min free-tier ceiling, self-limited
    ) -> None:
        self._api_key = api_key or "demo"
        self._client = httpx.AsyncClient(base_url=base_url, timeout=15.0)
        # Capacity = one minute's worth of tokens. A cold desk load fires a
        # burst (brief = 5 timeframe calls + chart + watchlist); allowing that
        # burst up front lets the brief resolve in seconds instead of starving
        # behind the ambient watchlist tiles, while the 0.13/s refill still
        # holds the long-run average at the 8/min ceiling.
        self._bucket = TokenBucket(rate=requests_per_second, capacity=8.0)

    async def get_ticker(self, symbol: str) -> Ticker:
        data = await self._get("/price", {"symbol": to_twelvedata_symbol(symbol)})
        try:
            return Ticker(
                symbol=symbol.upper(),
                price=Decimal(str(data["price"])),
                ts=datetime.now(timezone.utc),
            )
        except (KeyError, TypeError, InvalidOperation) as exc:
            raise AdapterError(self.name, f"malformed price payload: {data!r}") from exc

    async def get_klines(
        self,
        symbol: str,
        interval: str = "1h",
        limit: int = 100,
        start_time: datetime | None = None,
        end_time: datetime | None = None,
    ) -> list[Candle]:
        if interval not in _INTERVAL_MAP:
            raise ValueError(
                f"unsupported forex interval {interval!r}; one of {sorted(_INTERVAL_MAP)}"
            )
        td_interval, duration = _INTERVAL_MAP[interval]
        params: dict[str, Any] = {
            "symbol": to_twelvedata_symbol(symbol),
            "interval": td_interval,
            "outputsize": max(1, min(int(limit), MAX_OUTPUTSIZE)),
            "timezone": "UTC",
        }
        if start_time is not None:
            params["start_date"] = start_time.strftime("%Y-%m-%d %H:%M:%S")
        if end_time is not None:
            params["end_date"] = end_time.strftime("%Y-%m-%d %H:%M:%S")

        data = await self._get("/time_series", params)
        values = data.get("values")
        if not isinstance(values, list):
            raise AdapterError(self.name, f"no time_series values: {data!r}"[:200])
        try:
            candles = [self._parse_value(v, duration) for v in values]
        except (KeyError, TypeError, InvalidOperation, ValueError) as exc:
            raise AdapterError(self.name, "malformed time_series payload") from exc
        candles.reverse()  # Twelve Data returns newest-first; we want oldest-first
        return candles

    @staticmethod
    def _parse_datetime(raw: str) -> datetime:
        # Intraday bars are "YYYY-MM-DD HH:MM:SS"; daily bars are date-only.
        fmt = "%Y-%m-%d %H:%M:%S" if " " in raw else "%Y-%m-%d"
        return datetime.strptime(raw, fmt).replace(tzinfo=timezone.utc)

    @classmethod
    def _parse_value(cls, v: dict, duration: timedelta) -> Candle:
        open_time = cls._parse_datetime(v["datetime"])
        return Candle(
            open_time=open_time,
            open=Decimal(str(v["open"])),
            high=Decimal(str(v["high"])),
            low=Decimal(str(v["low"])),
            close=Decimal(str(v["close"])),
            volume=Decimal(str(v.get("volume", "0") or "0")),
            close_time=open_time + duration - timedelta(milliseconds=1),
        )

    async def _get(self, path: str, params: dict[str, Any]) -> Any:
        await self._bucket.acquire()
        params = {**params, "apikey": self._api_key}
        try:
            resp = await self._client.get(path, params=params)
            resp.raise_for_status()
            payload = resp.json()
        except httpx.HTTPStatusError as exc:
            raise AdapterError(
                self.name, f"{path} -> HTTP {exc.response.status_code}: {exc.response.text[:160]}"
            ) from exc
        except httpx.HTTPError as exc:
            raise AdapterError(self.name, f"{path} -> transport error: {exc}") from exc
        # Twelve Data signals errors with HTTP 200 + a status/code body.
        if isinstance(payload, dict) and payload.get("status") == "error":
            raise AdapterError(self.name, str(payload.get("message", payload))[:200])
        return payload

    async def aclose(self) -> None:
        await self._client.aclose()

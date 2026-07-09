"""Binance USDⓈ-M futures public data: funding, open interest, long/short ratio.

Keyless public endpoints on fapi.binance.com (2400 weight/min budget; we
self-limit far below). Values returned here are *analytics* (floats) — they are
context reads, never tradable levels. Spot-only symbols raise AdapterError,
which the brief composer degrades into a noted gap (NFR-3).
"""

from typing import Any

import httpx

from app.adapters.base import AdapterError, DataProvider
from app.core.ratelimit import TokenBucket


class BinanceFuturesAdapter(DataProvider):
    name = "binance_futures"

    def __init__(
        self,
        base_url: str = "https://fapi.binance.com",
        requests_per_second: float = 5.0,
    ) -> None:
        self._client = httpx.AsyncClient(base_url=base_url, timeout=10.0)
        self._bucket = TokenBucket(rate=requests_per_second, capacity=requests_per_second)

    async def get_funding(self, symbol: str) -> dict[str, float]:
        """Current funding rate and mark price from the premium index."""
        data = await self._get("/fapi/v1/premiumIndex", {"symbol": symbol.upper()})
        try:
            return {
                "funding_rate": float(data["lastFundingRate"]),
                "mark_price": float(data["markPrice"]),
            }
        except (KeyError, TypeError, ValueError) as exc:
            raise AdapterError(self.name, f"malformed premiumIndex payload: {data!r}") from exc

    async def get_open_interest_change(
        self, symbol: str, period: str = "1h", limit: int = 25
    ) -> dict[str, float | None]:
        """Latest open interest (base units) and % change across the window."""
        rows = await self._get(
            "/futures/data/openInterestHist",
            {"symbol": symbol.upper(), "period": period, "limit": limit},
        )
        try:
            series = [float(r["sumOpenInterest"]) for r in rows]
        except (KeyError, TypeError, ValueError) as exc:
            raise AdapterError(self.name, "malformed openInterestHist payload") from exc
        if not series:
            raise AdapterError(self.name, "empty openInterestHist")
        change = None
        if len(series) > 1 and series[0] > 0:
            change = (series[-1] - series[0]) / series[0] * 100.0
        return {"open_interest": series[-1], "oi_change_pct": change}

    async def get_long_short_ratio(self, symbol: str, period: str = "1h") -> float:
        rows = await self._get(
            "/futures/data/globalLongShortAccountRatio",
            {"symbol": symbol.upper(), "period": period, "limit": 1},
        )
        try:
            return float(rows[-1]["longShortRatio"])
        except (KeyError, IndexError, TypeError, ValueError) as exc:
            raise AdapterError(self.name, "malformed longShortAccountRatio payload") from exc

    async def _get(self, path: str, params: dict[str, Any]) -> Any:
        await self._bucket.acquire()
        try:
            resp = await self._client.get(path, params=params)
            resp.raise_for_status()
            return resp.json()
        except httpx.HTTPStatusError as exc:
            raise AdapterError(
                self.name, f"{path} -> HTTP {exc.response.status_code}: {exc.response.text[:200]}"
            ) from exc
        except httpx.HTTPError as exc:
            raise AdapterError(self.name, f"{path} -> transport error: {exc}") from exc

    async def aclose(self) -> None:
        await self._client.aclose()

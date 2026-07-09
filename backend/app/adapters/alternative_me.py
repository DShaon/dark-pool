"""alternative.me Crypto Fear & Greed index (free, keyless, 60 req/min)."""

from typing import Any

import httpx

from app.adapters.base import AdapterError, DataProvider
from app.core.ratelimit import TokenBucket


class AlternativeMeAdapter(DataProvider):
    name = "alternative_me"

    def __init__(self, base_url: str = "https://api.alternative.me") -> None:
        self._client = httpx.AsyncClient(base_url=base_url, timeout=10.0)
        self._bucket = TokenBucket(rate=0.5, capacity=2)  # well under 60/min

    async def get_fear_greed(self) -> tuple[int, str]:
        """Return (value 0-100, classification label)."""
        await self._bucket.acquire()
        try:
            resp = await self._client.get("/fng/", params={"limit": 1})
            resp.raise_for_status()
            data: Any = resp.json()
            entry = data["data"][0]
            return int(entry["value"]), str(entry["value_classification"])
        except httpx.HTTPError as exc:
            raise AdapterError(self.name, f"/fng/ -> {exc}") from exc
        except (KeyError, IndexError, TypeError, ValueError) as exc:
            raise AdapterError(self.name, "malformed fng payload") from exc

    async def aclose(self) -> None:
        await self._client.aclose()

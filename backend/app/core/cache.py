"""Cache layer: Upstash Redis (REST) when configured, in-memory fallback for dev.

Values are JSON-serializable dicts/lists (schemas pass through `model_dump(mode="json")`).
Infrastructure client — allowed to make HTTP calls per CLAUDE.md invariant 1.
"""

import json
import time
from typing import Any, Protocol

import httpx

from app.config import Settings


class Cache(Protocol):
    async def get(self, key: str) -> Any | None: ...
    async def set(self, key: str, value: Any, ttl_seconds: int) -> None: ...
    async def aclose(self) -> None: ...


class MemoryCache:
    """Process-local TTL cache. Dev fallback; fine for a single-user instance."""

    def __init__(self) -> None:
        self._data: dict[str, tuple[float, str]] = {}

    async def get(self, key: str) -> Any | None:
        item = self._data.get(key)
        if item is None:
            return None
        expires_at, raw = item
        if time.monotonic() > expires_at:
            self._data.pop(key, None)
            return None
        return json.loads(raw)

    async def set(self, key: str, value: Any, ttl_seconds: int) -> None:
        self._data[key] = (time.monotonic() + ttl_seconds, json.dumps(value))

    async def aclose(self) -> None:
        self._data.clear()


class UpstashCache:
    """Upstash Redis over its REST API (free tier friendly — no raw TCP needed)."""

    def __init__(self, url: str, token: str) -> None:
        self._client = httpx.AsyncClient(
            base_url=url.rstrip("/"),
            headers={"Authorization": f"Bearer {token}"},
            timeout=5.0,
        )

    async def get(self, key: str) -> Any | None:
        resp = await self._client.get(f"/get/{key}")
        resp.raise_for_status()
        raw = resp.json().get("result")
        return None if raw is None else json.loads(raw)

    async def set(self, key: str, value: Any, ttl_seconds: int) -> None:
        resp = await self._client.post(
            f"/set/{key}", params={"EX": ttl_seconds}, content=json.dumps(value)
        )
        resp.raise_for_status()

    async def aclose(self) -> None:
        await self._client.aclose()


def build_cache(settings: Settings) -> Cache:
    if settings.redis_rest_url and settings.redis_rest_token:
        return UpstashCache(settings.redis_rest_url, settings.redis_rest_token)
    return MemoryCache()

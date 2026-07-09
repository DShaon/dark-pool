"""Async token-bucket rate limiter.

Every adapter owns its own bucket (ADR-0003) so one misbehaving source can never
consume another source's budget.
"""

import asyncio
import time


class TokenBucket:
    """Classic token bucket: `rate` tokens/second refill, `capacity` burst size.

    `acquire()` sleeps until a token is available — callers are naturally queued
    (FIFO via the lock), which is the behavior we want for upstream API budgets.
    """

    def __init__(self, rate: float, capacity: float) -> None:
        if rate <= 0 or capacity <= 0:
            raise ValueError("rate and capacity must be positive")
        self._rate = float(rate)
        self._capacity = float(capacity)
        self._tokens = float(capacity)
        self._updated = time.monotonic()
        self._lock = asyncio.Lock()

    async def acquire(self, tokens: float = 1.0) -> None:
        if tokens > self._capacity:
            raise ValueError("requested more tokens than bucket capacity")
        async with self._lock:
            while True:
                now = time.monotonic()
                self._tokens = min(
                    self._capacity, self._tokens + (now - self._updated) * self._rate
                )
                self._updated = now
                if self._tokens >= tokens:
                    self._tokens -= tokens
                    return
                await asyncio.sleep((tokens - self._tokens) / self._rate)

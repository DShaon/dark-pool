"""DataProvider base contract (ADR-0003).

Every external source implements this interface, owns its own rate limiter, and
raises `AdapterError` on any upstream failure — callers never see raw transport
exceptions, and a failing source degrades gracefully (NFR-3) instead of crashing runs.
"""

from abc import ABC, abstractmethod


class AdapterError(RuntimeError):
    """An upstream data source failed or returned a malformed payload."""

    def __init__(self, provider: str, detail: str) -> None:
        self.provider = provider
        self.detail = detail
        super().__init__(f"[{provider}] {detail}")


class DataProvider(ABC):
    """Base class for all external data sources."""

    name: str = "base"

    @abstractmethod
    async def aclose(self) -> None:
        """Release network resources. Called on application shutdown."""

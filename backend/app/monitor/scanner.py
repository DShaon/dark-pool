"""Background scanner (P3 · FR-5) — Active-mode watchlist monitoring.

Ticks on an interval (APScheduler, wired in `main.py`'s lifespan). In "manual"
mode it's a no-op — the desk only analyzes on request, honoring the same
advisory-only-by-default spirit as ADR-0008. In "active" mode it scans every
watchlist symbol with the same deterministic `scan_brief` engine that powers
`/alerts` — no AI, no cost — and records newly-appearing conditions to the
feed store.

A failing symbol (bad ticker, adapter outage) is skipped, never aborts the
whole tick (NFR-3): one bad symbol can't blind the scanner to the rest of the
watchlist.
"""

from __future__ import annotations

import logging

from app.adapters.base import AdapterError
from app.monitor.alerts import AlertThresholds, scan_brief
from app.monitor.state import FeedStore, ModeStore, WatchlistStore
from app.quant.brief import BriefComposer

logger = logging.getLogger(__name__)


class Scanner:
    def __init__(
        self,
        composer: BriefComposer,
        thresholds: AlertThresholds,
        mode_store: ModeStore,
        watchlist_store: WatchlistStore,
        feed_store: FeedStore,
    ) -> None:
        self._composer = composer
        self._thresholds = thresholds
        self._mode = mode_store
        self._watchlist = watchlist_store
        self._feed = feed_store

    async def tick(self) -> dict:
        """One scan pass. Returns a small summary — useful for tests/logging,
        not part of any public API contract."""
        mode = self._mode.get()
        if mode != "active":
            return {"mode": mode, "scanned": [], "skipped": [], "new_alerts": 0}

        scanned: list[str] = []
        skipped: list[str] = []
        new_count = 0
        for symbol in self._watchlist.get():
            try:
                brief = await self._composer.compose(symbol)
            except AdapterError as exc:
                logger.warning("scanner: skipping %s: %s", symbol, exc)
                skipped.append(symbol)
                continue
            events = scan_brief(brief, self._thresholds)
            new_count += len(self._feed.record(symbol, events))
            scanned.append(symbol)

        return {"mode": mode, "scanned": scanned, "skipped": skipped, "new_alerts": new_count}

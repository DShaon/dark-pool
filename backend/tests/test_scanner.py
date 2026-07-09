"""Scanner tests — mode gating, per-symbol failure isolation, feed recording.

A FakeComposer stands in for BriefComposer (duck-typed .compose()); no network.
Reuses the rich/quiet brief builders from test_alerts.py so the fixtures stay
one source of truth.
"""

from app.adapters.base import AdapterError
from app.monitor.alerts import AlertThresholds
from app.monitor.scanner import Scanner
from app.monitor.state import FeedStore, ModeStore, WatchlistStore
from tests.test_alerts import quiet_brief, rich_brief


class FakeComposer:
    def __init__(self, briefs: dict) -> None:
        self._briefs = briefs
        self.calls: list[str] = []

    async def compose(self, symbol: str):
        self.calls.append(symbol)
        item = self._briefs.get(symbol)
        if item is None:
            raise AdapterError("fake", f"no data for {symbol}")
        if isinstance(item, Exception):
            raise item
        return item


def make_scanner(tmp_path, briefs: dict, watchlist: list[str]):
    composer = FakeComposer(briefs)
    mode = ModeStore(tmp_path / "mode.json")
    wl = WatchlistStore(tmp_path / "wl.json", default=watchlist)
    feed = FeedStore(tmp_path / "feed.json")
    scanner = Scanner(composer, AlertThresholds(), mode, wl, feed)
    return scanner, composer, mode, wl, feed


async def test_manual_mode_is_a_noop(tmp_path):
    scanner, composer, mode, wl, feed = make_scanner(
        tmp_path, {"BTCUSDT": rich_brief()}, ["BTCUSDT"]
    )
    assert mode.get() == "manual"  # default
    result = await scanner.tick()
    assert result == {"mode": "manual", "scanned": [], "skipped": [], "new_alerts": 0}
    assert composer.calls == []  # never even asked for a brief
    assert feed.recent() == []


async def test_active_mode_scans_watchlist_and_records_alerts(tmp_path):
    scanner, composer, mode, wl, feed = make_scanner(
        tmp_path,
        {"BTCUSDT": rich_brief(), "ETHUSDT": quiet_brief()},
        ["BTCUSDT", "ETHUSDT"],
    )
    mode.set("active")
    result = await scanner.tick()
    assert result["mode"] == "active"
    assert set(result["scanned"]) == {"BTCUSDT", "ETHUSDT"}
    assert result["skipped"] == []
    assert result["new_alerts"] > 0  # rich_brief trips every rule
    assert any(e["symbol"] == "BTCUSDT" for e in feed.recent())
    assert not any(e["symbol"] == "ETHUSDT" for e in feed.recent())  # quiet brief, no events


async def test_failing_symbol_is_skipped_not_fatal(tmp_path):
    scanner, composer, mode, wl, feed = make_scanner(
        tmp_path,
        {"BTCUSDT": rich_brief()},  # ETHUSDT deliberately absent → AdapterError
        ["BTCUSDT", "ETHUSDT"],
    )
    mode.set("active")
    result = await scanner.tick()
    assert result["scanned"] == ["BTCUSDT"]
    assert result["skipped"] == ["ETHUSDT"]
    assert result["new_alerts"] > 0  # BTCUSDT still got scanned


async def test_second_tick_with_unchanged_conditions_records_nothing_new(tmp_path):
    scanner, composer, mode, wl, feed = make_scanner(
        tmp_path, {"BTCUSDT": rich_brief()}, ["BTCUSDT"]
    )
    mode.set("active")
    first = await scanner.tick()
    second = await scanner.tick()  # same brief instance → identical conditions
    assert first["new_alerts"] > 0
    assert second["new_alerts"] == 0  # cooldown suppresses the repeat

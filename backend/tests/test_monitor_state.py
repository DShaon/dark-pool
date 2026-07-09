"""Scanner state store tests — mode/watchlist/feed, all file-backed + atomic.

No network. `FeedStore`'s cooldown dedup is exercised with explicit `at`
timestamps on hand-built AlertEvents (no wall-clock mocking needed).
"""

from datetime import datetime, timedelta, timezone

import pytest

from app.models.alerts import AlertEvent
from app.monitor.state import FeedStore, ModeStore, WatchlistStore

NOW = datetime(2026, 7, 8, 12, 0, tzinfo=timezone.utc)


def ev(kind="structure_break", tf="1h", msg="BOS ▲ · 1h @ 64000", at=NOW, tone="bull") -> AlertEvent:
    return AlertEvent(
        kind=kind, symbol="BTCUSDT", timeframe=tf, tone=tone,
        message=msg, message_bn="বাংলা", at=at, ref=None,
    )


# ── ModeStore ──

def test_mode_defaults_to_manual_and_persists(tmp_path):
    store = ModeStore(tmp_path / "mode.json")
    assert store.get() == "manual"
    assert store.set("active") == "active"
    assert store.get() == "active"
    # a fresh handle to the same file sees the persisted value
    assert ModeStore(tmp_path / "mode.json").get() == "active"


def test_mode_rejects_invalid_value(tmp_path):
    store = ModeStore(tmp_path / "mode.json")
    with pytest.raises(ValueError):
        store.set("sideways")  # type: ignore[arg-type]


# ── WatchlistStore ──

def test_watchlist_defaults_when_unset(tmp_path):
    store = WatchlistStore(tmp_path / "wl.json", default=["BTCUSDT", "ETHUSDT"])
    assert store.get() == ["BTCUSDT", "ETHUSDT"]


def test_watchlist_set_dedupes_uppercases_and_persists(tmp_path):
    store = WatchlistStore(tmp_path / "wl.json", default=["BTCUSDT"])
    saved = store.set(["ethusdt", "ETHUSDT", "solusdt"])
    assert saved == ["ETHUSDT", "SOLUSDT"]
    assert store.get() == ["ETHUSDT", "SOLUSDT"]


def test_watchlist_rejects_bad_symbol(tmp_path):
    store = WatchlistStore(tmp_path / "wl.json", default=["BTCUSDT"])
    with pytest.raises(ValueError):
        store.set(["bt!"])


def test_watchlist_caps_at_max(tmp_path):
    store = WatchlistStore(tmp_path / "wl.json", default=["BTCUSDT"])
    many = [f"AAA{i}USDT" for i in range(30)]
    saved = store.set(many)
    assert len(saved) == WatchlistStore.MAX_SYMBOLS


def test_watchlist_empty_list_falls_back_to_default(tmp_path):
    store = WatchlistStore(tmp_path / "wl.json", default=["BTCUSDT"])
    assert store.set([]) == ["BTCUSDT"]


# ── FeedStore ──

def test_feed_records_new_events(tmp_path):
    store = FeedStore(tmp_path / "feed.json")
    fresh = store.record("BTCUSDT", [ev()])
    assert len(fresh) == 1
    assert store.recent()[0]["symbol"] == "BTCUSDT"
    assert store.recent()[0]["message"] == "BOS ▲ · 1h @ 64000"


def test_feed_suppresses_unchanged_condition_within_cooldown(tmp_path):
    store = FeedStore(tmp_path / "feed.json", cooldown=timedelta(hours=1))
    store.record("BTCUSDT", [ev(at=NOW)])
    again = store.record("BTCUSDT", [ev(at=NOW + timedelta(minutes=10))])
    assert again == []  # same key, well within the 1h cooldown
    assert len(store.recent()) == 1


def test_feed_allows_recurrence_after_cooldown(tmp_path):
    store = FeedStore(tmp_path / "feed.json", cooldown=timedelta(hours=1))
    store.record("BTCUSDT", [ev(at=NOW)])
    later = store.record("BTCUSDT", [ev(at=NOW + timedelta(hours=2))])
    assert len(later) == 1
    assert len(store.recent()) == 2


def test_feed_caps_length(tmp_path):
    store = FeedStore(tmp_path / "feed.json", max_len=3, cooldown=timedelta(seconds=1))
    for i in range(5):
        store.record("BTCUSDT", [ev(msg=f"event {i}", at=NOW + timedelta(hours=i))])
    assert len(store.recent(limit=10)) == 3
    # newest first
    assert store.recent()[0]["message"] == "event 4"


def test_feed_recent_respects_limit(tmp_path):
    store = FeedStore(tmp_path / "feed.json", cooldown=timedelta(seconds=1))
    for i in range(5):
        store.record("BTCUSDT", [ev(msg=f"event {i}", at=NOW + timedelta(hours=i))])
    assert len(store.recent(limit=2)) == 2

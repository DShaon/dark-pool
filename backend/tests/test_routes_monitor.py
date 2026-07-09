"""`/monitor/*` route tests — mode/watchlist/feed, state stores swapped onto
app.state for isolation (same pattern as test_api.py's FakeBinance)."""

from fastapi.testclient import TestClient

from app.main import create_app
from app.monitor.state import FeedStore, ModeStore, WatchlistStore


def test_mode_get_defaults_and_post_roundtrips(tmp_path):
    app = create_app()
    with TestClient(app) as client:
        app.state.scanner_mode = ModeStore(tmp_path / "mode.json")

        assert client.get("/monitor/mode").json() == {"mode": "manual"}

        resp = client.post("/monitor/mode", json={"mode": "active"})
        assert resp.status_code == 200
        assert resp.json() == {"mode": "active"}
        assert client.get("/monitor/mode").json() == {"mode": "active"}


def test_mode_post_rejects_invalid_value(tmp_path):
    app = create_app()
    with TestClient(app) as client:
        app.state.scanner_mode = ModeStore(tmp_path / "mode.json")
        resp = client.post("/monitor/mode", json={"mode": "sideways"})
    assert resp.status_code == 422


def test_watchlist_get_defaults_and_post_validates_and_caps(tmp_path):
    app = create_app()
    with TestClient(app) as client:
        app.state.scanner_watchlist = WatchlistStore(
            tmp_path / "wl.json", default=["BTCUSDT"]
        )
        assert client.get("/monitor/watchlist").json() == {"symbols": ["BTCUSDT"]}

        ok = client.post("/monitor/watchlist", json={"symbols": ["ethusdt", "solusdt"]})
        assert ok.status_code == 200
        assert ok.json() == {"symbols": ["ETHUSDT", "SOLUSDT"]}

        bad = client.post("/monitor/watchlist", json={"symbols": ["!!"]})
        assert bad.status_code == 422


def test_feed_returns_recent_events(tmp_path):
    app = create_app()
    with TestClient(app) as client:
        feed = FeedStore(tmp_path / "feed.json")
        app.state.scanner_feed = feed
        from datetime import datetime, timezone

        from app.models.alerts import AlertEvent

        feed.record(
            "BTCUSDT",
            [
                AlertEvent(
                    kind="sentiment_extreme", symbol="BTCUSDT", timeframe=None,
                    tone="pulse", message="Extreme Fear (15)", message_bn="চরম ভয়",
                    at=datetime.now(timezone.utc), ref=None,
                )
            ],
        )
        resp = client.get("/monitor/feed")
        assert resp.status_code == 200
        events = resp.json()["events"]
        assert len(events) == 1
        assert events[0]["symbol"] == "BTCUSDT"
        assert events[0]["message_bn"] == "চরম ভয়"


def test_feed_limit_query_param(tmp_path):
    app = create_app()
    with TestClient(app) as client:
        app.state.scanner_feed = FeedStore(tmp_path / "feed.json")
        resp = client.get("/monitor/feed?limit=5")
    assert resp.status_code == 200
    assert resp.json() == {"events": []}

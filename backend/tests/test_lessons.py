"""Lessons loop tests (ADR-0019) — post-mortems in, honest aggregates out."""

import json
from datetime import datetime, timedelta, timezone

from fastapi.testclient import TestClient

from app.desk.cio import CIOSynthesizer
from app.desk.divergence import detect_divergence
from app.desk.lessons import LessonRecord, LessonsStore, cio_payload, digest
from app.desk.quick_read import QuickReadConfig
from app.main import create_app
from tests.test_cio import VALID_LONG_DRAFT, aligned_panel, make_brief

T0 = datetime(2026, 7, 10, tzinfo=timezone.utc)


def lesson(i, outcome, variant="intraday", tags=(), note=""):
    return LessonRecord(
        symbol="TESTUSDT", source="setup", variant=variant, direction="long",
        outcome=outcome, tags=list(tags), note=note, closed_at=T0 + timedelta(hours=i),
    )


def test_empty_digest_and_no_cio_noise():
    d = digest([])
    assert d.n_records == 0 and d.by_variant == {} and d.top_tags == []
    assert cio_payload(d) is None  # an empty lessons block would be noise


def test_digest_aggregates_wins_losses_tags_notes():
    records = [
        lesson(0, "tp"),
        lesson(1, "tp"),
        lesson(2, "sl", tags=["late_entry"], note="entered after the move was done"),
    ]
    d = digest(records)
    v = d.by_variant["setup:intraday"]
    assert (v.n, v.wins, v.losses) == (3, 2, 1)
    assert v.win_rate == 0.667
    assert d.top_tags == [("late_entry", 1)]
    assert d.recent_notes and "entered after the move" in d.recent_notes[0]
    assert "TESTUSDT long setup:intraday" in d.recent_notes[0]  # provenance prefix

    p = cio_payload(d)
    assert p is not None
    assert p["performance"]["setup:intraday"]["win_rate"] == 0.667
    assert p["recurring_failure_causes"][0]["cause"] == "entered too late"


def test_win_rate_hidden_below_min_n():
    d = digest([lesson(0, "tp"), lesson(1, "sl")])
    assert d.by_variant["setup:intraday"].win_rate is None  # 2 trades = noise


def test_invalidated_counts_tags_but_not_win_rate():
    d = digest([lesson(0, "invalidated", tags=["news_event"], note="CPI candle")])
    assert "setup:intraday" not in d.by_variant or d.by_variant["setup:intraday"].n == 0
    assert d.top_tags == [("news_event", 1)]


def test_store_repost_updates_not_duplicates(tmp_path):
    store = LessonsStore(tmp_path / "lessons.json")
    store.record(lesson(0, "sl"))  # graded first, no reason yet
    d = store.record(lesson(0, "sl", tags=["stop_too_tight"], note="wick took it"))
    assert d.n_records == 1  # same (symbol, closed_at) -> updated in place
    assert d.top_tags == [("stop_too_tight", 1)]


async def test_cio_receives_lessons_in_payload():
    calls = []

    class FakeGateway:
        async def chat(self, **kw):
            calls.append(kw)
            return json.dumps(VALID_LONG_DRAFT)

    cio = CIOSynthesizer(
        gateway=FakeGateway(),
        config=QuickReadConfig(provider="groq", model="test-model"),
        prompt="You are the CIO.",
    )
    brief, panel = make_brief(), aligned_panel()
    report = detect_divergence(panel, brief)
    lessons = {"note": "x", "recurring_failure_causes": [{"cause": "entered too late", "count": 3}]}
    await cio.synthesize(brief, panel, report, None, lessons)

    payload = json.loads(calls[0]["messages"][1]["content"].split("DESK INPUT:\n", 1)[1])
    assert payload["lessons"]["recurring_failure_causes"][0]["cause"] == "entered too late"

    # and without lessons the key is absent (no empty-noise blocks)
    await cio.synthesize(brief, panel, report)
    payload2 = json.loads(calls[1]["messages"][1]["content"].split("DESK INPUT:\n", 1)[1])
    assert "lessons" not in payload2


def test_lessons_routes(tmp_path):
    app = create_app()
    with TestClient(app) as client:
        app.state.lessons_store = LessonsStore(tmp_path / "lessons.json")
        body = {
            "symbol": "TESTUSDT", "source": "setup", "variant": "scalp",
            "direction": "long", "outcome": "sl", "tags": ["late_entry"],
            "note": "chased the candle", "closed_at": "2026-07-10T15:00:00Z",
        }
        assert client.post("/lessons", json=body).json() == {"ok": True, "n_records": 1}
        # unknown tag rejected with the reason
        bad = {**body, "tags": ["made_up_tag"]}
        assert client.post("/lessons", json=bad).status_code == 422

        d = client.get("/lessons").json()
        assert d["top_tags"] == [["late_entry", 1]]
        tags = client.get("/lessons/tags").json()["tags"]
        assert tags["late_entry"]["en"] == "entered too late"


def test_setups_route(tmp_path):
    from tests.test_setups import make_brief as make_setups_brief

    class FakeComposer:
        async def compose(self, symbol):
            return make_setups_brief("long")

    app = create_app()
    with TestClient(app) as client:
        app.state.brief_composer = FakeComposer()
        r = client.get("/setups/TESTUSDT")
    assert r.status_code == 200
    body = r.json()
    assert body["bias"] == "long"
    keys = [v["key"] for v in body["variants"]]
    assert keys == ["scalp", "intraday", "swing", "spot", "grid", "options"]
    intraday = next(v for v in body["variants"] if v["key"] == "intraday")
    assert intraday["tradeable"] is True and intraday["stop"] == "97.75"

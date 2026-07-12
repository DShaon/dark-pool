"""Scenario path service (ADR-0017 §2) — the anti-forecast lock.

Every waypoint must resolve to a REAL price already in the brief/plan; the
model invents nothing. A bad ref is retried once then dropped (never a 500).
"""

import json

import pytest

from app.desk.quick_read import QuickReadConfig
from app.desk.scenario import FUTURE_HORIZON_BARS, ScenarioError, ScenarioService

BRIEF = {
    "symbol": "BTCUSDT",
    "alignment": {"score": 0.6},
    "daily_levels": [{"kind": "PDH", "price": "103.5", "state": "intact"}],
    "timeframes": {
        "1h": {
            "last_close": "100.0",
            "order_blocks": [{"top": "98.5", "bottom": "97.0"}],
        }
    },
}


class FakeGateway:
    def __init__(self, responses):
        self.responses = list(responses)
        self.calls = []

    async def chat(self, **kw):
        self.calls.append(kw)
        return self.responses.pop(0)


def make_service(gw):
    return ScenarioService(
        gateway=gw,
        config=QuickReadConfig(provider="groq", model="test"),
        prompt="You are the scenario mapper.",
    )


GOOD = json.dumps(
    {
        "direction": "long",
        "waypoints": [
            {"level_ref": "brief.timeframes.1h.order_blocks[0].top", "label": "retest OB"},
            {"level_ref": "brief.daily_levels[0].price", "label": "PDH target"},
        ],
        "narrative": "If price retests the 1h OB and holds, we expect a push into the PDH.",
        "narrative_bn": None,
        "evidence": ["brief.alignment.score", "brief.daily_levels[0].price"],
    }
)


async def test_waypoints_resolve_to_real_prices_with_offsets():
    svc = make_service(FakeGateway([GOOD]))
    path = await svc.build(BRIEF, plan_data=None)
    assert [str(w.price) for w in path.waypoints] == ["98.5", "103.5"]  # real brief prices
    # offsets are evenly spaced into the future, last == horizon
    assert [w.bar_offset for w in path.waypoints] == [6, 12]
    assert path.waypoints[-1].bar_offset == FUTURE_HORIZON_BARS


async def test_invented_ref_retried_then_dropped():
    bad = json.dumps(
        {
            "direction": "long",
            "waypoints": [
                {"level_ref": "brief.timeframes.1h.made_up_level", "label": "nope"},
                {"level_ref": "brief.daily_levels[0].price"},
            ],
            "narrative": "This cites a level that does not exist in the brief at all.",
            "evidence": ["brief.alignment.score"],
        }
    )
    gw = FakeGateway([bad, bad])
    with pytest.raises(ScenarioError):
        await make_service(gw).build(BRIEF, plan_data=None)
    assert len(gw.calls) == 2  # one shot + one corrective retry
    assert "resolve" in gw.calls[1]["messages"][-1]["content"].lower()


async def test_bad_evidence_ref_dropped():
    bad = json.dumps(
        {
            "direction": "long",
            "waypoints": [
                {"level_ref": "brief.daily_levels[0].price"},
                {"level_ref": "brief.timeframes.1h.last_close"},
            ],
            "narrative": "Waypoints are fine but the evidence path is fabricated.",
            "evidence": ["brief.nonexistent.field"],
        }
    )
    gw = FakeGateway([bad, GOOD])  # recovers on retry
    path = await make_service(gw).build(BRIEF, plan_data=None)
    assert len(gw.calls) == 2
    assert path.direction == "long"


async def test_plan_refs_resolve_when_plan_present():
    plan = {"targets": [{"price": "110.0", "rr": 2.0}], "entry_zone": {"low": "99.0", "high": "101.0"}}
    resp = json.dumps(
        {
            "direction": "long",
            "waypoints": [
                {"level_ref": "plan.entry_zone.low"},
                {"level_ref": "plan.targets[0].price"},
            ],
            "narrative": "If we fill the entry zone, the desk's first target is the next stop.",
            "evidence": ["brief.alignment.score"],
        }
    )
    path = await make_service(FakeGateway([resp])).build(BRIEF, plan_data=plan)
    assert [str(w.price) for w in path.waypoints] == ["99.0", "110.0"]

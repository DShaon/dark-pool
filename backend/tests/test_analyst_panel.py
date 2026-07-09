"""Analyst panel tests — parallel fan-out, per-seat evidence lock, drop-on-fail.

Each seat gets its OWN FakeGateway with a scripted response, so we can drive
individual mandates deterministically (the real panel runs them concurrently).
No network. The brief fixture is a minimal-but-real MarketBrief so evidence
paths resolve exactly as in production.
"""

import json
from datetime import datetime, timezone
from decimal import Decimal

from app.desk.analysts import AnalystPanel, Seat
from app.desk.quick_read import QuickReadConfig, QuickReadService
from app.models.brief import (
    AlignmentOut,
    IndicatorsOut,
    MarketBrief,
    StructureOut,
    TimeframeAnalysis,
)

NOW = datetime(2026, 7, 8, 12, 0, tzinfo=timezone.utc)


def make_brief() -> MarketBrief:
    tf = TimeframeAnalysis(
        tf="1h",
        last_close=Decimal("64000"),
        structure=StructureOut(trend="bullish", last_event=None),
        premium_discount="equilibrium",
        swings=[],
        order_blocks=[],
        fvgs=[],
        equal_levels=[],
        indicators=IndicatorsOut(),
    )
    return MarketBrief(
        symbol="BTCUSDT",
        generated_at=NOW,
        timeframes={"1h": tf},
        daily_levels=[],
        derivatives=None,
        sentiment=None,
        alignment=AlignmentOut(score=1.0, bias="long", per_tf={"1h": "bullish"}),
        gaps=[],
    )


LONG_READ = {
    "direction": "long",
    "conviction": 3,
    "entry_zone": {"low": "63800", "high": "63950"},
    "stop_loss": "63500",
    "targets": [{"price": "64500", "rr": 1.8}],
    "thesis": "Structure is bullish on the hour; we buy the pullback while it holds.",
    "failure_mode": "A 1h close back below the entry zone turns this into chop.",
    "invalidation": {"price": "63500", "condition": "1h close below 63500"},
    "evidence": ["timeframes.1h.structure.trend", "alignment.bias"],
}
SHORT_READ = dict(LONG_READ, direction="short")
NO_TRADE_READ = {
    "direction": "no_trade",
    "conviction": 2,
    "targets": [],
    "thesis": "Mixed picture into overhead liquidity; we stand aside and keep powder dry.",
    "failure_mode": "A clean break either way would give us something to trade.",
    "evidence": ["alignment.bias", "timeframes.1h.structure.trend"],
}


class FakeGateway:
    def __init__(self, responses: list[str]) -> None:
        self.responses = responses
        self.calls = 0

    async def chat(self, **kwargs) -> str:
        resp = self.responses[min(self.calls, len(self.responses) - 1)]
        self.calls += 1
        return resp


def seat(mandate: str, responses: list[str]) -> tuple[Seat, FakeGateway]:
    gw = FakeGateway(responses)
    svc = QuickReadService(
        gateway=gw,  # type: ignore[arg-type] — structural: only .chat is used
        config=QuickReadConfig(provider="p", model=f"model-{mandate}"),
        prompt="system prompt",
    )
    return Seat(mandate=mandate, service=svc), gw  # type: ignore[arg-type]


async def test_panel_all_seats_survive_in_order():
    s_trend, _ = seat("trend", [json.dumps(LONG_READ)])
    s_contra, _ = seat("contrarian", [json.dumps(SHORT_READ)])
    s_deriv, _ = seat("derivatives", [json.dumps(LONG_READ)])
    s_risk, _ = seat("risk", [json.dumps(NO_TRADE_READ)])
    panel = AnalystPanel([s_trend, s_contra, s_deriv, s_risk], min_survivors=3)

    theses, dropped = await panel.run(make_brief())

    assert not dropped
    # order follows seat order for stable display
    assert [t.mandate for t in theses] == ["trend", "contrarian", "derivatives", "risk"]
    assert [t.read.direction for t in theses] == ["long", "short", "long", "no_trade"]
    # each thesis is stamped with the model that produced it
    assert theses[0].model_id == "p/model-trend"


async def test_panel_drops_failing_seat_but_others_continue():
    s1, _ = seat("trend", [json.dumps(LONG_READ)])
    s2, _ = seat("contrarian", [json.dumps(SHORT_READ)])
    s3, _ = seat("risk", [json.dumps(NO_TRADE_READ)])
    s_bad, gw_bad = seat("derivatives", ["garbage", "still garbage"])
    panel = AnalystPanel([s1, s2, s3, s_bad], min_survivors=3)

    theses, dropped = await panel.run(make_brief())

    assert len(theses) == 3
    assert [d.mandate for d in dropped] == ["derivatives"]
    assert gw_bad.calls == 2  # one shot + one corrective retry, then dropped


async def test_panel_enforces_evidence_lock_per_seat():
    bad = json.dumps(dict(LONG_READ, evidence=["timeframes.99z.nope", "alignment.bias"]))
    s_ok, _ = seat("trend", [json.dumps(LONG_READ)])
    s_bad, gw = seat("derivatives", [bad])  # same bad path returned on retry too
    panel = AnalystPanel([s_ok, s_bad], min_survivors=1)

    theses, dropped = await panel.run(make_brief())

    assert [t.mandate for t in theses] == ["trend"]
    assert [d.mandate for d in dropped] == ["derivatives"]
    assert gw.calls == 2


async def test_seat_count_and_min_survivors_exposed():
    s1, _ = seat("trend", [json.dumps(LONG_READ)])
    s2, _ = seat("risk", [json.dumps(NO_TRADE_READ)])
    panel = AnalystPanel([s1, s2], min_survivors=2)
    assert panel.seat_count == 2
    assert panel.min_survivors == 2

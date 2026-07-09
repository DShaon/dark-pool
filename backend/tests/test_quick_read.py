"""Quick Read service tests — validation loop, evidence lock, retry-then-drop.

A FakeGateway returns scripted responses; no network. The brief fixture is a
minimal-but-real MarketBrief so evidence paths resolve exactly as they would
in production.
"""

import json
from datetime import datetime, timezone
from decimal import Decimal

import pytest

from app.desk.quick_read import QuickReadConfig, QuickReadError, QuickReadService
from app.models.brief import (
    AlignmentOut,
    IndicatorsOut,
    MarketBrief,
    StructureOut,
    TimeframeAnalysis,
)
from app.models.quickread import EvidenceError, check_evidence, resolve_path

NOW = datetime(2026, 7, 7, 12, 0, tzinfo=timezone.utc)


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


VALID_READ = {
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


class FakeGateway:
    def __init__(self, responses: list[str]) -> None:
        self.responses = responses
        self.calls = 0

    async def chat(self, **kwargs) -> str:
        resp = self.responses[min(self.calls, len(self.responses) - 1)]
        self.calls += 1
        return resp


def make_service(responses: list[str]) -> tuple[QuickReadService, FakeGateway]:
    gw = FakeGateway(responses)
    svc = QuickReadService(
        gateway=gw,  # type: ignore[arg-type] — structural: only .chat is used
        config=QuickReadConfig(provider="groq", model="test-model"),
        prompt="system prompt",
    )
    return svc, gw


async def test_valid_read_passes_first_try():
    svc, gw = make_service([json.dumps(VALID_READ)])
    read = await svc.run(make_brief())
    assert gw.calls == 1
    assert read.direction == "long"
    assert read.entry_zone is not None and read.entry_zone.low == Decimal("63800")


async def test_fenced_json_is_tolerated():
    svc, _ = make_service(["```json\n" + json.dumps(VALID_READ) + "\n```"])
    read = await svc.run(make_brief())
    assert read.conviction == 3


async def test_invalid_then_valid_uses_single_retry():
    svc, gw = make_service(["not json at all", json.dumps(VALID_READ)])
    read = await svc.run(make_brief())
    assert gw.calls == 2
    assert read.direction == "long"


async def test_bad_evidence_twice_drops_the_read():
    bad = dict(VALID_READ, evidence=["timeframes.4h.structure.trend", "alignment.bias"])
    svc, gw = make_service([json.dumps(bad)])
    with pytest.raises(QuickReadError, match="4h"):
        await svc.run(make_brief())
    assert gw.calls == 2  # one shot + one corrective retry, then dropped


async def test_trade_without_levels_is_rejected():
    incomplete = {
        k: v
        for k, v in VALID_READ.items()
        if k not in ("entry_zone", "stop_loss", "invalidation")
    }
    svc, gw = make_service([json.dumps(incomplete)])
    with pytest.raises(QuickReadError):
        await svc.run(make_brief())
    assert gw.calls == 2


def test_resolve_path_walks_dicts_and_lists():
    data = {"a": {"b": [{"c": 7}]}}
    assert resolve_path(data, "a.b[0].c") == 7
    with pytest.raises(KeyError):
        resolve_path(data, "a.b[1].c")
    with pytest.raises(KeyError):
        resolve_path(data, "a.x")


def test_check_evidence_reports_every_bad_path():
    brief_data = make_brief().model_dump(mode="json")
    with pytest.raises(EvidenceError, match="nope.path"):
        check_evidence(["timeframes.1h.last_close", "nope.path"], brief_data)

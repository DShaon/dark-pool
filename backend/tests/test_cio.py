"""CIO layer tests (§F5 Fable pass) — divergence, confidence, sizing, synthesis.

Golden-fixture discipline: every expected number below is HAND-COMPUTED in a
comment next to its assertion. If a formula change breaks one of these, that
is a money-risk change and needs an ADR, not a test edit.
"""

import json
from datetime import datetime, timezone
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient

from app.core.llm import LLMError
from app.desk.cio import CIOSynthesizer, deterministic_fallback
from app.desk.confidence import compute_confidence
from app.desk.divergence import detect_divergence
from app.desk.quick_read import QuickReadConfig
from app.desk.sizing import position_size
from app.main import create_app
from app.models.analyst import AnalystThesis
from app.models.brief import (
    AlignmentOut,
    DerivativesOut,
    IndicatorsOut,
    LevelOut,
    MarketBrief,
    StructureEventOut,
    StructureOut,
    TimeframeAnalysis,
)
from app.models.quickread import EntryZone, Invalidation, QuickRead, Target

T0 = datetime(2026, 7, 9, tzinfo=timezone.utc)


# ── fixtures ──────────────────────────────────────────────────────────────


def make_brief(
    *,
    score: float = 0.67,
    trend: str = "bullish",
    event: tuple[str, str] | None = ("BOS", "bullish"),
    funding_regime: str | None = "neutral",
    atr: float | None = 2.0,
    pdh: str | None = "103",
) -> MarketBrief:
    tfa = TimeframeAnalysis(
        tf="1h",
        last_close=Decimal("100"),
        structure=StructureOut(
            trend=trend,  # type: ignore[arg-type]
            last_event=(
                StructureEventOut(
                    kind=event[0], direction=event[1], level=Decimal("99"), time=T0  # type: ignore[arg-type]
                )
                if event
                else None
            ),
        ),
        premium_discount="equilibrium",
        swings=[],
        order_blocks=[],
        fvgs=[],
        equal_levels=[],
        indicators=IndicatorsOut(atr14=atr),
    )
    return MarketBrief(
        symbol="TESTUSDT",
        generated_at=T0,
        timeframes={"1h": tfa},
        daily_levels=(
            [LevelOut(kind="PDH", price=Decimal(pdh), state="intact")] if pdh else []
        ),
        derivatives=(
            DerivativesOut(funding_rate=0.0001, funding_regime=funding_regime, mark_price=100.0)  # type: ignore[arg-type]
            if funding_regime
            else None
        ),
        sentiment=None,
        alignment=AlignmentOut(score=score, bias="long", per_tf={"1h": trend}),
    )


def thesis(mandate, direction, conviction, low=None, high=None, stop=None, tps=()):
    read = QuickRead(
        direction=direction,
        conviction=conviction,
        entry_zone=EntryZone(low=Decimal(low), high=Decimal(high)) if low else None,
        stop_loss=Decimal(stop) if stop else None,
        targets=[Target(price=Decimal(p), rr=1.0) for p in tps],
        thesis="Structure and flows support this test read.",
        failure_mode="The level breaks against us.",
        invalidation=(
            Invalidation(price=Decimal(stop), condition="close beyond the stop")
            if stop
            else None
        ),
        evidence=["alignment.score", "timeframes.1h.structure.trend"],
    )
    return AnalystThesis(mandate=mandate, model_id="test/model", read=read)


def aligned_panel():
    """3 longs clustered within 1 ATR (mids 100/101/100), risk officer aside."""
    return [
        thesis("trend", "long", 4, "99", "101", "97", ("104", "107")),
        thesis("contrarian", "long", 3, "100", "102", "98", ("105",)),
        thesis("derivatives", "long", 4, "99.5", "100.5", "97.5", ("106",)),
        thesis("risk", "no_trade", 2),
    ]


# ── divergence detector ───────────────────────────────────────────────────


def test_divergence_aligned():
    r = detect_divergence(aligned_panel(), make_brief())
    assert r.consensus_state == "aligned"
    assert r.plurality_direction == "long"
    assert r.votes == {"long": 3, "short": 0, "no_trade": 1}
    assert r.conviction_weighted["long"] == 11
    assert r.entry_cluster is True  # mid spread 1.0 <= 1.0 x ATR(2.0)
    assert r.conviction_spread == 2  # 4 (trend) - 2 (risk)


def test_divergence_entry_scatter_breaks_alignment():
    panel = aligned_panel()
    # contrarian re-priced far away: mid 105 vs 100 -> spread 5 > 2.0 band
    panel[1] = thesis("contrarian", "long", 3, "104", "106", "98", ("109",))
    r = detect_divergence(panel, make_brief())
    assert r.consensus_state == "split"
    assert r.entry_cluster is False
    assert any("scatter" in n for n in r.notes)


def test_divergence_contested_both_sides_confident():
    panel = [
        thesis("trend", "long", 4, "99", "101", "97", ("104",)),
        thesis("contrarian", "short", 4, "100", "102", "105", ("95",)),
        thesis("derivatives", "long", 2, "99", "101", "97", ("104",)),
        thesis("risk", "short", 3, "100", "102", "105", ("95",)),
    ]
    r = detect_divergence(panel, make_brief())
    # weighted: long 6, short 7 -> plurality short; both sides carry >=3
    assert r.consensus_state == "contested"
    assert r.plurality_direction == "short"


def test_divergence_opposition_low_conviction_is_split():
    panel = [
        thesis("trend", "long", 4, "99", "101", "97", ("104",)),
        thesis("contrarian", "short", 1, "100", "102", "105", ("95",)),
    ]
    r = detect_divergence(panel, make_brief())
    assert r.consensus_state == "split"
    assert r.plurality_direction == "long"  # weighted 4 vs 1


def test_divergence_weighted_tie_is_contested_no_trade():
    panel = [
        thesis("trend", "long", 3, "99", "101", "97", ("104",)),
        thesis("contrarian", "short", 3, "100", "102", "105", ("95",)),
    ]
    r = detect_divergence(panel, make_brief())
    assert r.plurality_direction == "no_trade"
    assert r.consensus_state == "contested"  # min(3,3) >= 3


def test_divergence_all_no_trade_is_aligned_stand_aside():
    panel = [thesis("trend", "no_trade", 3), thesis("risk", "no_trade", 2)]
    r = detect_divergence(panel, make_brief())
    assert r.consensus_state == "aligned"
    assert r.plurality_direction == "no_trade"


def test_divergence_single_survivor_is_never_consensus():
    r = detect_divergence(
        [thesis("trend", "long", 5, "99", "101", "97", ("104",))], make_brief()
    )
    assert r.consensus_state == "split"
    assert any("one voice" in n for n in r.notes)


def test_divergence_missing_atr_does_not_manufacture_dissent():
    panel = [
        thesis("trend", "long", 3, "90", "92", "88", ("104",)),  # far apart
        thesis("contrarian", "long", 3, "108", "110", "106", ("120",)),
        thesis("risk", "no_trade", 2),
    ]
    r = detect_divergence(panel, make_brief(atr=None))
    assert r.entry_cluster is None  # unknown, not False
    assert r.consensus_state == "aligned"  # only POSITIVE scatter blocks


# ── calibrated confidence (ADR-0007 golden values) ────────────────────────


def test_confidence_full_checklist_golden():
    brief, panel = make_brief(), aligned_panel()
    report = detect_divergence(panel, brief)
    c = compute_confidence(brief, "long", panel, report)
    # components: mtf 0.67 · structure BOS-with 1.0 · funding neutral 0.7 ·
    # room: PDH 103 vs 100 = 1.5 ATR -> (1.5-0.25)/1.75 = 0.7143
    assert c.components == {
        "mtf_alignment": 0.67,
        "structure": 1.0,
        "derivatives": 0.7,
        "liquidity_room": 0.7143,
    }
    assert c.excluded == []
    assert c.checklist == 0.7711  # (0.67+1.0+0.7+0.7143)/4 = 0.771075
    # agreement: aligned base 1.0; share 11/13 = 0.84615 -> 0.5+0.42308
    assert c.agreement == 0.9231
    assert c.weighted_vote_share == 0.8462
    # value: 0.5*0.771075 + 0.5*0.923077 = 0.847076 -> 0.85
    assert c.value == 0.85


def test_confidence_missing_derivatives_excluded_not_zeroed():
    brief, panel = make_brief(funding_regime=None), aligned_panel()
    report = detect_divergence(panel, brief)
    c = compute_confidence(brief, "long", panel, report)
    assert c.excluded == ["derivatives"]
    # checklist over 3 components: (0.67+1.0+0.7143)/3 = 0.794767
    assert c.checklist == 0.7948
    # value: 0.5*0.794767 + 0.5*0.923077 = 0.858922 -> 0.86
    assert c.value == 0.86


def test_confidence_no_trade_uses_mixed_market():
    brief = make_brief(score=0.1)
    panel = [thesis("trend", "no_trade", 3), thesis("risk", "no_trade", 2)]
    report = detect_divergence(panel, brief)
    c = compute_confidence(brief, "no_trade", panel, report)
    assert c.components == {"mixed_market": 0.9}  # 1 - |0.1|
    # aligned base 1.0, share 5/5 -> agreement 1.0; 0.45+0.5 = 0.95 (= clamp hi)
    assert c.value == 0.95


def test_confidence_everything_against_golden():
    brief = make_brief(
        score=-0.67, event=("BOS", "bearish"), funding_regime="positive_extreme",
        pdh="100.4",  # 0.2 ATR overhead -> room clamps to 0
    )
    panel = [
        thesis("trend", "long", 1, "99", "101", "97", ("104",)),
        thesis("contrarian", "short", 4, "100", "102", "105", ("95",)),
        thesis("derivatives", "short", 4, "100", "102", "105", ("95",)),
        thesis("risk", "no_trade", 2),
    ]
    report = detect_divergence(panel, brief)
    assert report.consensus_state == "split"  # max long conviction 1 < 3
    c = compute_confidence(brief, "long", panel, report)
    # all four checklist components hit 0
    assert c.checklist == 0.0
    # agreement: split 0.5 base -> 0.25; share 1/11 -> 0.045455; = 0.295455
    # value: 0.5*0 + 0.5*0.295455 = 0.147727 -> 0.15
    assert c.value == 0.15


# ── sizing ────────────────────────────────────────────────────────────────


def test_sizing_basic_long():
    s = position_size(Decimal("100"), Decimal("98"), Decimal("1.0"))
    # 2% stop distance, 1% risk -> 50% of account
    assert s.stop_distance_pct == 2.0
    assert s.position_pct == 50.0
    assert s.implied_leverage == 0.5
    assert s.capped is False


def test_sizing_cap_applies_and_reports():
    s = position_size(Decimal("100"), Decimal("99.9"), Decimal("1.0"))
    # 0.1% stop -> raw 1000% -> capped at 100
    assert s.position_pct == 100.0
    assert s.capped is True


def test_sizing_short_mirrors():
    s = position_size(Decimal("100"), Decimal("102"), Decimal("1.0"))
    assert s.position_pct == 50.0


def test_sizing_degenerate_inputs_raise():
    with pytest.raises(ValueError):
        position_size(Decimal("100"), Decimal("100"))
    with pytest.raises(ValueError):
        position_size(Decimal("0"), Decimal("98"))
    with pytest.raises(ValueError):
        position_size(Decimal("100"), Decimal("98"), Decimal("0"))


# ── CIO synthesis ─────────────────────────────────────────────────────────


class FakeGateway:
    def __init__(self, responses):
        self.responses = list(responses)
        self.calls: list[dict] = []

    async def chat(self, **kw):
        self.calls.append(kw)
        r = self.responses.pop(0)
        if isinstance(r, Exception):
            raise r
        return r


def make_cio(gateway) -> CIOSynthesizer:
    return CIOSynthesizer(
        gateway=gateway,
        config=QuickReadConfig(provider="groq", model="test-model"),
        prompt="You are the CIO.",
        risk_pct=Decimal("1.0"),
    )


VALID_LONG_DRAFT = {
    "direction": "long",
    "entry_zone": {"low": "99.5", "high": "100.5"},
    "stop_loss": "97.5",
    "targets": [{"price": "104"}, {"price": "106"}],
    "confirmation": ["15m close back above 101"],
    "invalidation": {"price": "97.5", "condition": "1h close below the cluster stop"},
    "thesis": "Three seats want longs into the cluster; we buy the zone.",
    "failure_mode": "Sweep of 97.5 without reclaim kills the idea.",
    "alternative_scenario": "Range extends and we reload lower with the risk seat.",
    "evidence": ["alignment.score", "timeframes.1h.structure.trend"],
}


async def test_cio_valid_draft_rr_and_sizing_recomputed():
    gw = FakeGateway([json.dumps(VALID_LONG_DRAFT)])
    brief, panel = make_brief(), aligned_panel()
    report = detect_divergence(panel, brief)
    plan = await make_cio(gw).synthesize(brief, panel, report)

    assert plan.direction == "long"
    assert plan.synthesizer == "groq/test-model"
    # rr recomputed in code: mid 100, risk 2.5 -> 104: 1.6 · 106: 2.4
    assert [t.rr for t in plan.targets] == [1.6, 2.4]
    # sizing: 2.5% stop distance, 1% risk -> 40%
    assert plan.sizing is not None and plan.sizing.position_pct == 40.0
    assert plan.confidence.value == 0.85  # same golden fixture as above
    assert plan.built_from == ["contrarian", "derivatives", "trend"]
    assert plan.consensus_state == "aligned"


async def test_cio_never_counter_trades_retry_then_accept():
    counter = dict(VALID_LONG_DRAFT)
    counter["direction"] = "short"  # panel plurality is long
    counter["stop_loss"] = "105"
    counter["targets"] = [{"price": "95"}]
    gw = FakeGateway([json.dumps(counter), json.dumps(VALID_LONG_DRAFT)])
    brief, panel = make_brief(), aligned_panel()
    plan = await make_cio(gw).synthesize(brief, panel, detect_divergence(panel, brief))

    assert len(gw.calls) == 2
    # the corrective message names the violated rule
    assert "counter-trade" in gw.calls[1]["messages"][-1]["content"]
    assert plan.direction == "long"


async def test_cio_invented_levels_rejected():
    invented = dict(VALID_LONG_DRAFT)
    invented["entry_zone"] = {"low": "90", "high": "91"}  # outside [98,103] span
    gw = FakeGateway([json.dumps(invented), json.dumps(VALID_LONG_DRAFT)])
    brief, panel = make_brief(), aligned_panel()
    plan = await make_cio(gw).synthesize(brief, panel, detect_divergence(panel, brief))
    assert len(gw.calls) == 2
    assert "published span" in gw.calls[1]["messages"][-1]["content"]
    assert plan.entry_zone.low == Decimal("99.5")


async def test_cio_twice_bad_falls_back_deterministically():
    gw = FakeGateway(["not json", "still not json"])
    brief, panel = make_brief(), aligned_panel()
    plan = await make_cio(gw).synthesize(brief, panel, detect_divergence(panel, brief))

    assert plan.synthesizer == "deterministic_fallback"
    assert plan.direction == "long"
    # strongest agreeing seat = trend (conviction 4, first on tie): zone 99-101
    assert plan.entry_zone == EntryZone(low=Decimal("99"), high=Decimal("101"))
    # stop widened to the panel's most conservative: min(97, 98, 97.5) = 97
    assert plan.stop_loss == Decimal("97")
    # rr vs mid 100, risk 3: 104 -> 1.33 · 107 -> 2.33
    assert [t.rr for t in plan.targets] == [1.33, 2.33]
    # sizing: 3% distance -> 33.33%
    assert plan.sizing.position_pct == 33.33
    assert plan.confidence.value == 0.85


async def test_cio_llm_error_immediate_fallback():
    gw = FakeGateway([LLMError("groq", "provider down")])
    brief, panel = make_brief(), aligned_panel()
    plan = await make_cio(gw).synthesize(brief, panel, detect_divergence(panel, brief))
    assert len(gw.calls) == 1
    assert plan.synthesizer == "deterministic_fallback"


async def test_cio_no_trade_plurality_forces_stand_aside():
    panel = [thesis("trend", "no_trade", 3), thesis("risk", "no_trade", 2)]
    brief = make_brief(score=0.1)
    # model insists on a long, twice -> guardrail rejects -> stand-aside floor
    gw = FakeGateway([json.dumps(VALID_LONG_DRAFT), json.dumps(VALID_LONG_DRAFT)])
    plan = await make_cio(gw).synthesize(brief, panel, detect_divergence(panel, brief))

    assert plan.direction == "no_trade"
    assert plan.synthesizer == "deterministic_fallback"
    assert plan.entry_zone is None and plan.stop_loss is None and not plan.targets
    assert plan.sizing is None


def test_fallback_incoherent_levels_publish_nothing():
    # an "agreeing" seat whose stop sits INSIDE the zone -> geometry broken
    panel = [
        thesis("trend", "long", 4, "99", "101", "100", ("104",)),
        thesis("contrarian", "long", 3, "99", "101", "100.5", ("105",)),
    ]
    brief = make_brief()
    plan = deterministic_fallback(brief, panel, detect_divergence(panel, brief))
    assert plan.direction == "no_trade"  # never publish incoherent numbers
    assert "coherent" in plan.thesis


# ── /plan route ───────────────────────────────────────────────────────────


class FakePanel:
    def __init__(self, theses):
        self._theses = theses
        self.min_survivors = 3
        self.seat_count = 4

    async def run(self, brief):
        return self._theses, []


class FakeComposer:
    def __init__(self, brief):
        self._brief = brief

    async def compose(self, symbol):
        return self._brief


def test_plan_route_deterministic_when_no_cio():
    app = create_app()
    with TestClient(app) as client:
        app.state.brief_composer = FakeComposer(make_brief())
        app.state.analyst_panel = FakePanel(aligned_panel())
        app.state.cio = None
        resp = client.get("/plan/TESTUSDT")
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "ok"
    assert body["plan"]["direction"] == "long"
    assert body["plan"]["synthesizer"] == "deterministic_fallback"
    assert body["plan"]["confidence"]["value"] == 0.85
    assert body["plan"]["sizing"]["position_pct"] == 33.33


def test_plan_route_degrades_below_two_survivors():
    app = create_app()
    with TestClient(app) as client:
        app.state.brief_composer = FakeComposer(make_brief())
        app.state.analyst_panel = FakePanel(
            [thesis("trend", "long", 4, "99", "101", "97", ("104",))]
        )
        app.state.cio = None
        resp = client.get("/plan/TESTUSDT")
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "degraded"
    assert body["plan"] is None
    assert "need 2" in body["reason"]

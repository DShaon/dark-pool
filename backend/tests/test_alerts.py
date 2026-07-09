"""Alert engine tests (P3 · FR-5) — deterministic rules over hand-built briefs.

Golden fixtures: a "rich" brief that trips every rule, and a "quiet" one that
trips none. Thresholds are exercised directly (config-over-code surface).
"""

from datetime import datetime, timezone
from decimal import Decimal

from app.models.brief import (
    AlignmentOut,
    DerivativesOut,
    IndicatorsOut,
    LevelOut,
    MarketBrief,
    SentimentOut,
    StructureEventOut,
    StructureOut,
    TimeframeAnalysis,
    ZoneOut,
)
from app.monitor.alerts import AlertThresholds, scan_brief

NOW = datetime(2026, 7, 8, 12, 0, tzinfo=timezone.utc)


def _tf(
    tf: str,
    close: str,
    *,
    event: StructureEventOut | None = None,
    obs: list[ZoneOut] | None = None,
    equal: list[LevelOut] | None = None,
) -> TimeframeAnalysis:
    return TimeframeAnalysis(
        tf=tf,
        last_close=Decimal(close),
        structure=StructureOut(trend="bullish", last_event=event),
        premium_discount="equilibrium",
        swings=[],
        order_blocks=obs or [],
        fvgs=[],
        equal_levels=equal or [],
        indicators=IndicatorsOut(),
    )


def rich_brief(
    event: StructureEventOut | None = None, ob_mitigated: bool = False
) -> MarketBrief:
    # models are frozen — build the desired state up-front, never mutate.
    evt = event or StructureEventOut(
        kind="BOS", direction="bullish", level=Decimal("63500"), time=NOW
    )
    ob = ZoneOut(
        kind="order_block", side="bullish",
        top=Decimal("64000"), bottom=Decimal("63900"), mitigated=ob_mitigated, time=NOW,
    )
    return MarketBrief(
        symbol="BTCUSDT",
        generated_at=NOW,
        timeframes={
            "15m": _tf("15m", "64000"),
            "1h": _tf("1h", "64000", event=evt, obs=[ob]),
            "4h": _tf("4h", "64000"),  # no event → no 4h structure alert
        },
        daily_levels=[LevelOut(kind="PDL", price=Decimal("61000"), state="swept")],
        derivatives=DerivativesOut(
            funding_rate=0.0006, funding_regime="positive_extreme", mark_price=64000.0,
            open_interest=1000.0, oi_change_24h_pct=6.5, long_short_ratio=1.2,
        ),
        sentiment=SentimentOut(fear_greed=15, label="Extreme Fear"),
        alignment=AlignmentOut(score=1.0, bias="long", per_tf={"1h": "bullish"}),
        gaps=[],
    )


def quiet_brief() -> MarketBrief:
    return MarketBrief(
        symbol="ETHUSDT",
        generated_at=NOW,
        timeframes={"15m": _tf("15m", "3000"), "1h": _tf("1h", "3000"), "4h": _tf("4h", "3000")},
        daily_levels=[LevelOut(kind="PDH", price=Decimal("3200"), state="intact")],
        derivatives=DerivativesOut(
            funding_rate=0.00005, funding_regime="neutral", mark_price=3000.0,
            open_interest=500.0, oi_change_24h_pct=1.0, long_short_ratio=1.0,
        ),
        sentiment=SentimentOut(fear_greed=52, label="Neutral"),
        alignment=AlignmentOut(score=0.0, bias="mixed", per_tf={"1h": "range"}),
        gaps=[],
    )


def test_rich_brief_trips_every_rule():
    events = scan_brief(rich_brief(), AlertThresholds())
    kinds = {e.kind for e in events}
    assert kinds == {
        "structure_break", "liquidity_sweep", "funding_extreme",
        "oi_spike", "zone_proximity", "sentiment_extreme",
    }
    # BOS bullish → bull tone; only the 1h structure event (not 4h)
    struct = [e for e in events if e.kind == "structure_break"]
    assert len(struct) == 1 and struct[0].tone == "bull" and struct[0].timeframe == "1h"
    # every alert carries a non-empty Bengali message
    assert all(e.message_bn.strip() for e in events)


def test_quiet_brief_is_silent():
    assert scan_brief(quiet_brief(), AlertThresholds()) == []


def test_choch_is_a_warn():
    choch = StructureEventOut(kind="CHoCH", direction="bearish", level=Decimal("63000"), time=NOW)
    struct = [e for e in scan_brief(rich_brief(event=choch), AlertThresholds()) if e.kind == "structure_break"]
    assert struct[0].tone == "warn" and "CHoCH" in struct[0].message


def test_oi_threshold_is_config():
    brief = quiet_brief()  # oi_change 1.0%, funding neutral, F&G 52 → otherwise silent
    assert not any(e.kind == "oi_spike" for e in scan_brief(brief, AlertThresholds()))
    tuned = AlertThresholds(oi_spike_pct=0.5)
    spikes = [e for e in scan_brief(brief, tuned) if e.kind == "oi_spike"]
    assert len(spikes) == 1 and spikes[0].tone == "pulse"


def test_zone_proximity_ignores_mitigated_zones():
    # a spent (mitigated) zone → no proximity alert
    assert not any(
        e.kind == "zone_proximity"
        for e in scan_brief(rich_brief(ob_mitigated=True), AlertThresholds())
    )

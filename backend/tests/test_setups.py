"""Setup variant engine tests (ADR-0019 + ADR-0022) — golden money math.

Every level below is HAND-COMPUTED. Two regimes now coexist:
  * structure path (ADR-0022): entries anchored on hand-crafted zones with
    hand-computed stops (farther of zone-edge/swing + 0.10 ATR buffer) and
    targets (intact equal levels / opposing zones, 1.2R floor)
  * ATR-fallback path: MUST stay byte-identical to the ADR-0019 table — the
    original golden numbers below are the regression pin proving it

Fixtures construct TimeframeAnalysis DIRECTLY (zones/levels/swings by hand),
deliberately bypassing candle-based detection: these tests own the
selection/pricing math only; detection correctness is tested elsewhere.
Changing any constant here is a money-risk change: new ADR, not a test edit.
Base fixture: close=100, ATR=2 on every anchor timeframe.
"""

from datetime import datetime, timedelta, timezone
from decimal import Decimal

from app.desk.setups import build_variants
from app.models.brief import (
    AlignmentOut,
    IndicatorsOut,
    LevelOut,
    MarketBrief,
    StructureEventOut,
    StructureOut,
    SwingOut,
    TimeframeAnalysis,
    ZoneOut,
)

T0 = datetime(2026, 7, 10, tzinfo=timezone.utc)
H = timedelta(hours=1)


def ob(side: str, top: str, bottom: str, at: datetime, kind: str = "order_block") -> ZoneOut:
    return ZoneOut(kind=kind, side=side, top=Decimal(top), bottom=Decimal(bottom),  # type: ignore[arg-type]
                   mitigated=False, time=at)


def eq(kind: str, price: str, state: str = "intact") -> LevelOut:
    return LevelOut(kind=kind, price=Decimal(price), state=state)  # type: ignore[arg-type]


def swing(price: str, kind: str, at: datetime = T0 - 3 * H) -> SwingOut:
    return SwingOut(time=at, price=Decimal(price), kind=kind)  # type: ignore[arg-type]


def make_brief(
    bias: str = "long",
    atr: float | None = 2.0,
    tfs=("15m", "1h", "4h", "1d"),
    overrides: dict[str, dict] | None = None,
) -> MarketBrief:
    """Base brief (no structure -> every directional variant falls back to the
    ADR-0019 ATR math). `overrides` merges extra TimeframeAnalysis kwargs into
    a single TF, e.g. {"1h": {"order_blocks": [...], "premium_discount": ...}}."""
    frames = {}
    for tf in tfs:
        kwargs: dict = dict(
            tf=tf,
            last_close=Decimal("100"),
            structure=StructureOut(trend="bullish" if bias == "long" else "bearish" if bias == "short" else "range"),
            premium_discount="equilibrium",
            swings=[], order_blocks=[], fvgs=[], equal_levels=[],
            indicators=IndicatorsOut(atr14=atr),
        )
        kwargs.update((overrides or {}).get(tf, {}))
        frames[tf] = TimeframeAnalysis(**kwargs)
    score = 0.67 if bias == "long" else -0.67 if bias == "short" else 0.0
    return MarketBrief(
        symbol="TESTUSDT", generated_at=T0, timeframes=frames, daily_levels=[],
        derivatives=None, sentiment=None,
        alignment=AlignmentOut(score=score, bias=bias, per_tf={}),  # type: ignore[arg-type]
    )


def by_key(variants):
    return {v.key: v for v in variants}


# ── ATR-fallback regression pin: no structure -> ADR-0019 numbers EXACTLY ──


def test_long_bias_fallback_golden_levels():
    v = by_key(build_variants(make_brief("long")))
    # scalp: band .15 stop .6 tps (.9, 1.5) on ATR 2, close 100
    s = v["scalp"]
    assert s.tradeable and s.gradeable and s.direction == "long"
    assert s.entry_kind == "atr_fallback"
    assert (s.entry_low, s.entry_high) == (Decimal("99.70"), Decimal("100.00"))
    assert s.stop == Decimal("98.65")  # mid 99.85 - 1.2
    assert [(t.price, t.rr) for t in s.targets] == [
        (Decimal("101.65"), 1.5), (Decimal("102.85"), 2.5),
    ]
    # intraday: band .25 stop 1.0 tps (1.5, 2.5)
    i = v["intraday"]
    assert (i.entry_low, i.entry_high, i.stop) == (Decimal("99.50"), Decimal("100.00"), Decimal("97.75"))
    assert [(t.price, t.rr) for t in i.targets] == [
        (Decimal("102.75"), 1.5), (Decimal("104.75"), 2.5),
    ]
    # swing: band .4 stop 1.5 tps (2.25, 4.0) -> rr2 = 4/1.5 = 2.67
    w = v["swing"]
    assert (w.entry_low, w.entry_high, w.stop) == (Decimal("99.20"), Decimal("100.00"), Decimal("96.60"))
    assert [(t.price, t.rr) for t in w.targets] == [
        (Decimal("104.10"), 1.5), (Decimal("107.60"), 2.67),
    ]
    # spot: band .5 stop 2.0 tps (3, 5)
    p = v["spot"]
    assert (p.entry_low, p.entry_high, p.stop) == (Decimal("99.00"), Decimal("100.00"), Decimal("95.50"))
    assert [(t.price, t.rr) for t in p.targets] == [
        (Decimal("105.50"), 1.5), (Decimal("109.50"), 2.5),
    ]
    # fallback + equilibrium + no structure event = 0 confluence points -> low
    assert s.quality == "low" and s.confluence == []
    # trending -> the grid is untradeable, options informational; the ADR-0022
    # provenance fields are not-applicable defaults there
    assert v["grid"].tradeable is False and "trending" in v["grid"].reason
    assert v["grid"].quality is None
    assert v["options"].tradeable is False and v["options"].gradeable is False
    assert v["options"].quality is None
    assert v["options"].entry_low == Decimal("103.00")  # strike = 100 + 1.5*2


def test_short_bias_fallback_mirrors():
    v = by_key(build_variants(make_brief("short")))
    i = v["intraday"]
    assert i.direction == "short" and i.entry_kind == "atr_fallback"
    # entry = [close, close + band*ATR]; mid 100.25; stop above; tps below
    assert (i.entry_low, i.entry_high) == (Decimal("100.00"), Decimal("100.50"))
    assert i.stop == Decimal("102.25")
    assert [(t.price, t.rr) for t in i.targets] == [
        (Decimal("97.25"), 1.5), (Decimal("95.25"), 2.5),
    ]


# ── structure path: entries on real zones (ADR-0022 golden math) ───────────


def test_structure_long_full_confluence_golden():
    """Bullish 1h OB 99.30–99.80 (0.20 below close, radius 0.25×2=0.50 ✓),
    swing low 99.10, EQL cluster on the zone, intact EQH target, discount,
    confirming BOS after the zone formed — all five confluence points."""
    brief = make_brief("long", overrides={"1h": dict(
        order_blocks=[
            ob("bullish", "99.80", "99.30", T0 - 5 * H),
            ob("bearish", "103.00", "102.50", T0 - 6 * H),  # opposing -> TP2 pool
        ],
        swings=[swing("99.10", "low")],
        equal_levels=[eq("EQL", "99.795"), eq("EQH", "101.30")],
        premium_discount="discount",
        structure=StructureOut(
            trend="bullish",
            last_event=StructureEventOut(
                kind="BOS", direction="bullish", level=Decimal("100.50"), time=T0 - 2 * H,
            ),
        ),
    )})
    i = by_key(build_variants(brief))["intraday"]
    assert i.entry_kind == "structure"
    # entry band IS the zone
    assert (i.entry_low, i.entry_high) == (Decimal("99.30"), Decimal("99.80"))
    # stop: zone stop = 99.30 - 0.10*2 = 99.10; swing stop = 99.10 - 0.20 =
    # 98.90 is FARTHER -> wins (either level holding keeps the thesis alive)
    assert i.stop == Decimal("98.90")
    # R measured from the zone's near edge 99.80: risk = 0.90
    # TP1 = intact EQH 101.30 (1.50 away, rr 1.6667 -> 1.67, >= 1.2 floor)
    # TP2 = opposing OB near edge 102.50 (2.70 away, rr 3.0)
    assert [(t.price, t.rr) for t in i.targets] == [
        (Decimal("101.30"), 1.67), (Decimal("102.50"), 3.0),
    ]
    assert i.quality == "high" and len(i.confluence) == 5
    # other variants' anchor TFs got no zones -> they honestly fall back
    assert by_key(build_variants(brief))["scalp"].entry_kind == "atr_fallback"


def test_structure_short_mirror_golden():
    """Bearish 1h OB 100.20–100.70 above close; swing high 100.90; premium.
    No structural target exists -> both TPs come from the published ratio
    table RESCALED onto the real stop distance (the coherence rule)."""
    brief = make_brief("short", overrides={"1h": dict(
        order_blocks=[ob("bearish", "100.70", "100.20", T0 - 4 * H)],
        swings=[swing("100.90", "high")],
        premium_discount="premium",
    )})
    i = by_key(build_variants(brief))["intraday"]
    assert i.entry_kind == "structure" and i.direction == "short"
    assert (i.entry_low, i.entry_high) == (Decimal("100.20"), Decimal("100.70"))
    # zone stop = 100.70 + 0.20 = 100.90; swing stop = 100.90 + 0.20 = 101.10 farther
    assert i.stop == Decimal("101.10")
    # risk from near edge 100.20 = 0.90; ratios 1.5/2.5 rescaled:
    # tp1 = 100.20 - 1.5*0.90 = 98.85 · tp2 = 100.20 - 2.5*0.90 = 97.95
    assert [(t.price, t.rr) for t in i.targets] == [
        (Decimal("98.85"), 1.5), (Decimal("97.95"), 2.5),
    ]
    # structure + fresh + premium = 3 points
    assert i.quality == "high" and len(i.confluence) == 3


def test_target_floor_rejects_uneconomic_level():
    """An intact EQH only 1.0R away is REAL but uneconomic (< 1.2R floor):
    both targets fall back to the ratio table on the new stop — never a mix."""
    brief = make_brief("long", overrides={"1h": dict(
        order_blocks=[ob("bullish", "99.80", "99.30", T0 - 30 * H)],  # stale, no swing
        equal_levels=[eq("EQH", "100.50")],
    )})
    i = by_key(build_variants(brief))["intraday"]
    # stop = zone only: 99.30 - 0.20 = 99.10; risk from 99.80 = 0.70
    assert i.stop == Decimal("99.10")
    # EQH 100.50 is 0.70 away = 1.0R < 1.2 -> rejected;
    # fallback: tp1 = 99.80 + 1.5*0.70 = 100.85 · tp2 = 99.80 + 2.5*0.70 = 101.55
    assert [(t.price, t.rr) for t in i.targets] == [
        (Decimal("100.85"), 1.5), (Decimal("101.55"), 2.5),
    ]


def test_single_structural_target_allowed():
    """One qualifying liquidity target and nothing farther -> the card shows
    ONE honest target, not a padded second."""
    brief = make_brief("long", overrides={"1h": dict(
        order_blocks=[ob("bullish", "99.80", "99.30", T0 - 30 * H)],
        equal_levels=[eq("EQH", "100.95")],
    )})
    i = by_key(build_variants(brief))["intraday"]
    # risk 0.70; EQH 1.15 away -> rr 1.6428 -> 1.64 >= floor
    assert [(t.price, t.rr) for t in i.targets] == [(Decimal("100.95"), 1.64)]


def test_stop_uses_zone_when_swing_is_nearer():
    """A swing low INSIDE the zone's risk envelope must not tighten the stop —
    the farther (zone) invalidation wins."""
    brief = make_brief("long", overrides={"1h": dict(
        order_blocks=[ob("bullish", "99.80", "99.30", T0 - 5 * H)],
        swings=[swing("99.50", "low")],  # swing stop 99.30 is NEARER than 99.10
    )})
    i = by_key(build_variants(brief))["intraday"]
    assert i.stop == Decimal("99.10")  # zone bottom 99.30 - 0.20


def test_search_radius_boundary():
    """Intraday hunts within search 1.5 × ATR 2 = 3.00 of close: a zone 2.90
    away anchors; a zone 3.10 away is last week's story -> honest fallback."""
    inside = make_brief("long", overrides={"1h": dict(
        order_blocks=[ob("bullish", "97.10", "96.60", T0 - 5 * H)],  # dist 2.90
    )})
    assert by_key(build_variants(inside))["intraday"].entry_kind == "structure"
    outside = make_brief("long", overrides={"1h": dict(
        order_blocks=[ob("bullish", "96.90", "96.40", T0 - 5 * H)],  # dist 3.10
    )})
    assert by_key(build_variants(outside))["intraday"].entry_kind == "atr_fallback"


def test_zone_straddling_price_is_not_an_entry():
    """A zone containing the current close offers no pullback — the variant
    must fall back rather than fake an at-market 'structure' entry."""
    brief = make_brief("long", overrides={"1h": dict(
        order_blocks=[ob("bullish", "100.40", "99.60", T0 - 2 * H)],  # top > close
    )})
    i = by_key(build_variants(brief))["intraday"]
    assert i.entry_kind == "atr_fallback"
    assert (i.entry_low, i.entry_high) == (Decimal("99.50"), Decimal("100.00"))


def test_quality_tier_boundaries():
    """Exactly 3 / 2 / 1 points -> high / medium / low."""
    zone_fresh = dict(order_blocks=[ob("bullish", "99.80", "99.30", T0 - 5 * H)])
    zone_stale = dict(order_blocks=[ob("bullish", "99.80", "99.30", T0 - 30 * H)])

    # structure + fresh + discount = 3 -> high
    b3 = make_brief("long", overrides={"1h": {**zone_fresh, "premium_discount": "discount"}})
    i3 = by_key(build_variants(b3))["intraday"]
    assert i3.quality == "high" and len(i3.confluence) == 3

    # structure + discount (stale zone) = 2 -> medium
    b2 = make_brief("long", overrides={"1h": {**zone_stale, "premium_discount": "discount"}})
    i2 = by_key(build_variants(b2))["intraday"]
    assert i2.quality == "medium" and len(i2.confluence) == 2

    # structure only (stale, equilibrium) = 1 -> low
    b1 = make_brief("long", overrides={"1h": zone_stale})
    i1 = by_key(build_variants(b1))["intraday"]
    assert i1.quality == "low" and len(i1.confluence) == 1


def test_fallback_quality_capped_at_medium():
    """No zone -> the overlap/freshness/structure-anchor points cannot fire;
    even with discount AND a confirming BOS the fallback caps at medium."""
    brief = make_brief("long", overrides={"1h": dict(
        premium_discount="discount",
        structure=StructureOut(
            trend="bullish",
            last_event=StructureEventOut(
                kind="BOS", direction="bullish", level=Decimal("99.50"), time=T0 - H,
            ),
        ),
    )})
    i = by_key(build_variants(brief))["intraday"]
    assert i.entry_kind == "atr_fallback"
    assert i.quality == "medium" and len(i.confluence) == 2


# ── gates (unchanged by ADR-0022 — the money-math changed, not the gates) ──


def test_mixed_bias_gates_directionals_and_frees_the_grid():
    v = by_key(build_variants(make_brief("mixed")))
    for key in ("scalp", "intraday", "swing", "spot"):
        assert v[key].tradeable is False
        assert "stands aside" in v[key].reason
        assert v[key].direction == "neutral"
        assert v[key].quality is None  # no entry -> quality not applicable
    g = v["grid"]  # chop harvest: tradeable exactly when the desk has no bias
    assert g.tradeable is True and g.gradeable is False
    assert (g.entry_low, g.entry_high) == (Decimal("97.00"), Decimal("103.00"))  # ±1.5*ATR


def test_missing_atr_disables_that_variant_only():
    brief = make_brief("long", tfs=("1h", "4h", "1d"))  # no 15m at all
    v = by_key(build_variants(brief))
    assert v["scalp"].tradeable is False and "15m" in v["scalp"].reason
    assert v["intraday"].tradeable is True  # its own anchor is fine


def test_all_variants_always_render():
    for bias in ("long", "short", "mixed"):
        assert len(build_variants(make_brief(bias))) == 6  # cards never vanish

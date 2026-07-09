"""Golden-fixture tests for the quant/SMC engine.

Every fixture is a hand-computed candle sequence where the expected pivots,
structure events, zones, and states are known in advance. If any of these
break, the engine's meaning changed — that is a bug or a deliberate ADR, never
an accident.
"""

from datetime import datetime, timedelta, timezone
from decimal import Decimal

from app.models.market import Candle
from app.quant import ta
from app.quant.brief import compute_alignment, funding_regime
from app.quant.liquidity import daily_weekly_levels, equal_levels
from app.quant.structure import analyze_structure, premium_discount
from app.quant.swings import Swing, detect_swings
from app.quant.zones import detect_fvgs, detect_order_blocks

T0 = datetime(2026, 1, 1, tzinfo=timezone.utc)


def mk(o: str, h: str, l: str, c: str, i: int, hours: int = 1) -> Candle:
    return Candle(
        open_time=T0 + timedelta(hours=i * hours),
        open=Decimal(o), high=Decimal(h), low=Decimal(l), close=Decimal(c),
        volume=Decimal("1"),
        close_time=T0 + timedelta(hours=(i + 1) * hours, milliseconds=-1),
    )


# Hand-verified sequence (k=1): pivots high@1 (12), low@3 (10.5), high@5 (13.2);
# BOS bullish at i4 (close 12.9 > 12), CHoCH bearish at i7 (close 10.4 < 10.5).
GOLDEN = [
    mk("10", "11", "9", "10.5", 0),
    mk("10.5", "12", "10", "11.5", 1),
    mk("11.5", "11.8", "10.8", "11", 2),
    mk("11", "11.2", "10.5", "10.8", 3),
    mk("10.8", "13", "10.7", "12.9", 4),
    mk("12.9", "13.2", "12", "12.2", 5),
    mk("12.2", "12.5", "11.5", "11.8", 6),
    mk("11.8", "12", "10.2", "10.4", 7),
]


def test_swing_detection_golden():
    swings = detect_swings(GOLDEN, k=1)
    assert [(s.kind, s.index, str(s.price)) for s in swings] == [
        ("high", 1, "12"),
        ("low", 3, "10.5"),
        ("high", 5, "13.2"),
    ]
    assert all(s.confirm_index == s.index + 1 for s in swings)


def test_structure_bos_then_choch():
    state = analyze_structure(GOLDEN, swing_k=1)
    kinds = [(e.kind, e.direction, str(e.broken_level), e.index) for e in state.events]
    assert kinds == [
        ("BOS", "bullish", "12", 4),
        ("CHoCH", "bearish", "10.5", 7),
    ]
    assert state.trend == "bearish"


def test_premium_discount_golden():
    swings = detect_swings(GOLDEN, k=1)
    # close 10.4 inside range [10.5, 13.2] -> below it -> deep discount
    assert premium_discount(GOLDEN, swings) == "discount"


def test_fvg_detect_and_mitigate():
    base = [
        mk("9.8", "10", "9.5", "9.9", 0),
        # high 10.7 on the middle candle so candle 3 (low 10.6) does NOT open a
        # second gap against it — this fixture must contain exactly one FVG.
        mk("9.9", "10.7", "9.9", "10.3", 1),
        mk("10.5", "10.8", "10.5", "10.7", 2),  # low 10.5 > high[0] 10 -> bullish FVG [10, 10.5]
        mk("10.7", "10.9", "10.6", "10.8", 3),  # stays above the gap
    ]
    atr = [None] * 10

    untouched = detect_fvgs(base, atr)
    assert len(untouched) == 1
    z = untouched[0]
    assert (z.side, str(z.top), str(z.bottom), z.index, z.mitigated) == (
        "bullish", "10.5", "10", 1, False,
    )

    touched = detect_fvgs(base + [mk("10.8", "10.85", "10.3", "10.6", 4)], atr)
    assert touched[0].mitigated is True

    closed_through = detect_fvgs(base + [mk("10.8", "10.85", "9.7", "9.8", 4)], atr)
    assert closed_through == []  # close below bottom kills the gap


def test_order_block_detect_mitigate_invalidate():
    atr = [0.5] * 10
    base = [
        mk("11", "11.1", "10.4", "10.5", 0),      # bearish origin candle
        mk("10.5", "12.6", "10.5", "12.5", 1),     # displacement: body 2.0 > 0.65, closes above 11.1
        mk("12.5", "12.8", "12.4", "12.6", 2),     # stays away
    ]
    obs = detect_order_blocks(base, atr)
    assert len(obs) == 1
    ob = obs[0]
    assert (ob.side, str(ob.top), str(ob.bottom), ob.index, ob.mitigated) == (
        "bullish", "11.1", "10.4", 0, False,
    )

    revisited = detect_order_blocks(
        base + [mk("12.6", "12.7", "11.0", "12.0", 3)], atr
    )
    assert revisited[0].mitigated is True  # low 11.0 entered the zone

    crash = [mk("12.6", "12.7", "11.0", "12.0", 3), mk("12", "12.1", "10.0", "10.1", 4)]
    after_break = detect_order_blocks(base + crash, atr)
    # The bullish OB is invalidated (close 10.1 < bottom 10.4)...
    assert [z for z in after_break if z.side == "bullish"] == []
    # ...while the breakdown displacement itself correctly mints a fresh bearish
    # OB from the last up-close candle (index 2) — real engine behavior.
    bearish = [z for z in after_break if z.side == "bearish"]
    assert len(bearish) == 1
    assert bearish[0].index == 2 and bearish[0].mitigated is False


def test_equal_highs_swept_then_broken():
    flat = [mk("14.2", "14.5", "14", "14.2", i) for i in range(10)]
    pivots = [
        Swing(index=2, confirm_index=3, time=flat[2].open_time, price=Decimal("15.00"), kind="high"),
        Swing(index=6, confirm_index=7, time=flat[6].open_time, price=Decimal("15.01"), kind="high"),
    ]

    swept_candles = list(flat)
    swept_candles[8] = mk("14.2", "15.05", "14", "14.9", 8)  # wick through, close below
    levels = equal_levels(pivots, swept_candles)
    assert len(levels) == 1
    assert (levels[0].kind, str(levels[0].price), levels[0].state) == ("EQH", "15.01", "swept")

    broken_candles = list(swept_candles)
    broken_candles[9] = mk("14.9", "15.4", "14.8", "15.2", 9)  # close through
    assert equal_levels(pivots, broken_candles)[0].state == "broken"


def test_daily_weekly_levels_and_sweep():
    days = [mk(str(100 + i), str(110 + i), str(90 + i), str(105 + i), i, hours=24) for i in range(9)]
    prev = days[-2]  # PDH = 117, PDL = 97
    today_start = days[-1].open_time
    intraday = [
        Candle(
            open_time=today_start + timedelta(hours=h),
            open=Decimal("108"), high=Decimal("109"), low=Decimal("107"),
            close=Decimal("108"), volume=Decimal("1"),
            close_time=today_start + timedelta(hours=h + 1, milliseconds=-1),
        )
        for h in range(3)
    ]
    # wick above PDH (117) but close back under -> swept
    intraday.append(
        Candle(
            open_time=today_start + timedelta(hours=3),
            open=Decimal("116"), high=Decimal("117.5"), low=Decimal("115"),
            close=Decimal("116.5"), volume=Decimal("1"),
            close_time=today_start + timedelta(hours=4, milliseconds=-1),
        )
    )
    levels = {lv.kind: lv for lv in daily_weekly_levels(days, intraday)}
    assert str(levels["PDH"].price) == str(prev.high)
    assert levels["PDH"].state == "swept"
    assert levels["PDL"].state == "intact"
    assert str(levels["PWH"].price) == "117"  # max high of days[-8:-1]
    assert str(levels["PWL"].price) == "91"   # min low of that window


def test_indicators_hand_checked():
    assert ta.ema([1, 2, 3, 4, 5], 3)[-1] == 4.0

    up = [float(i) for i in range(1, 17)]
    assert ta.rsi(up, 14)[-1] == 100.0

    flat_candles = [mk("10", "10.5", "9.5", "10", i) for i in range(20)]
    assert abs(ta.atr(flat_candles, 14)[-1] - 1.0) < 1e-9

    upper, mid, lower = ta.bollinger([10.0] * 25, 20)
    assert upper[-1] == mid[-1] == lower[-1] == 10.0

    single = [mk("10", "11", "9", "10", 0)]
    assert abs(ta.vwap(single)[-1] - 10.0) < 1e-9

    ramp = [float(i) for i in range(1, 41)]
    line, signal, hist = ta.macd(ramp)
    assert line[-1] is not None and signal[-1] is not None
    assert abs(hist[-1] - (line[-1] - signal[-1])) < 1e-12


def test_funding_regime_thresholds():
    assert funding_regime(0.0006) == "positive_extreme"
    assert funding_regime(0.0002) == "positive"
    assert funding_regime(0.0) == "neutral"
    assert funding_regime(-0.0002) == "negative"
    assert funding_regime(-0.0006) == "negative_extreme"


def test_alignment_bias():
    from app.models.brief import IndicatorsOut, StructureOut, TimeframeAnalysis

    def tfa(trend: str) -> TimeframeAnalysis:
        return TimeframeAnalysis(
            tf="1h", last_close=Decimal("1"),
            structure=StructureOut(trend=trend),  # type: ignore[arg-type]
            premium_discount="equilibrium", swings=[], order_blocks=[], fvgs=[],
            equal_levels=[], indicators=IndicatorsOut(),
        )

    all_bull = compute_alignment({"15m": tfa("bullish"), "1h": tfa("bullish"), "4h": tfa("bullish")})
    assert (all_bull.score, all_bull.bias) == (1.0, "long")

    mixed = compute_alignment({"15m": tfa("bullish"), "1h": tfa("bearish"), "4h": tfa("range")})
    assert mixed.bias == "mixed"

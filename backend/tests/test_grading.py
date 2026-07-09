"""Grading algorithm tests — the pure `grade_candles` function.

Golden fixtures: hand-built candles exercise clean TP hits, clean SL hits,
still-open trades, and the one genuine ambiguity (a candle whose range
contains BOTH levels) — both the "resolved via finer data" and "still
ambiguous, falls back to the documented conservative default" paths.
"""

from datetime import datetime, timedelta, timezone
from decimal import Decimal

from app.models.market import Candle
from app.quant.grading import grade_candles

T0 = datetime(2026, 7, 1, tzinfo=timezone.utc)


def candle(i: int, o: str, h: str, low: str, c: str) -> Candle:
    return Candle(
        open_time=T0 + timedelta(hours=i),
        open=Decimal(o),
        high=Decimal(h),
        low=Decimal(low),
        close=Decimal(c),
        volume=Decimal("100"),
        close_time=T0 + timedelta(hours=i + 1, milliseconds=-1),
    )


async def test_long_hits_target_first():
    candles = [
        candle(0, "100", "105", "98", "103"),   # neither level touched
        candle(1, "103", "121", "102", "118"),  # target=120 touched
    ]
    result = await grade_candles(candles, "long", stop=Decimal("90"), target=Decimal("120"))
    assert result.outcome == "tp"
    assert result.candles_checked == 2


async def test_long_hits_stop_first():
    candles = [
        candle(0, "100", "105", "98", "103"),
        candle(1, "103", "108", "89", "95"),  # stop=90 touched
    ]
    result = await grade_candles(candles, "long", stop=Decimal("90"), target=Decimal("120"))
    assert result.outcome == "sl"
    assert result.candles_checked == 2


async def test_still_open_when_neither_level_reached():
    candles = [candle(0, "100", "105", "98", "103")]
    result = await grade_candles(candles, "long", stop=Decimal("90"), target=Decimal("120"))
    assert result.outcome == "open"
    assert result.hit_at is None
    assert result.candles_checked == 1


async def test_short_direction_is_mirrored():
    # short: stop ABOVE entry, target BELOW — hit_stop on a high, hit_target on a low
    candles = [candle(0, "100", "106", "94", "96")]  # target=95 touched, stop=110 not
    result = await grade_candles(candles, "short", stop=Decimal("110"), target=Decimal("95"))
    assert result.outcome == "tp"


async def test_ambiguous_bar_resolved_by_finer_candles():
    # 1h bar touches BOTH stop (90) and target (120) — genuinely ambiguous at this granularity
    ambiguous = candle(0, "100", "121", "89", "115")

    async def resolve(c: Candle) -> list[Candle]:
        # the "real" 1m sequence: target touched well before the dip to stop
        return [
            Candle(open_time=c.open_time, open=Decimal("100"), high=Decimal("121"),
                   low=Decimal("100"), close=Decimal("120"), volume=Decimal("1"),
                   close_time=c.open_time + timedelta(minutes=1)),
            Candle(open_time=c.open_time + timedelta(minutes=30), open=Decimal("120"),
                   high=Decimal("120"), low=Decimal("89"), close=Decimal("95"),
                   volume=Decimal("1"), close_time=c.close_time),
        ]

    result = await grade_candles(
        [ambiguous], "long", stop=Decimal("90"), target=Decimal("120"), resolve_ambiguous=resolve
    )
    assert result.outcome == "tp"  # finer data proves target came first


async def test_ambiguous_bar_still_ambiguous_at_finer_level_defaults_conservative():
    ambiguous = candle(0, "100", "121", "89", "115")

    async def resolve(c: Candle) -> list[Candle]:
        # even the "finer" data has one bar touching both — can't disambiguate further
        return [candle(0, "100", "121", "89", "115")]

    result = await grade_candles(
        [ambiguous], "long", stop=Decimal("90"), target=Decimal("120"), resolve_ambiguous=resolve
    )
    assert result.outcome == "sl"  # conservative default: stop wins


async def test_ambiguous_bar_without_a_resolver_defaults_conservative():
    ambiguous = candle(0, "100", "121", "89", "115")
    result = await grade_candles([ambiguous], "long", stop=Decimal("90"), target=Decimal("120"))
    assert result.outcome == "sl"


async def test_resolver_returning_none_defaults_conservative():
    ambiguous = candle(0, "100", "121", "89", "115")

    async def resolve(c: Candle) -> None:
        return None  # e.g. the drill-down fetch itself failed

    result = await grade_candles(
        [ambiguous], "long", stop=Decimal("90"), target=Decimal("120"), resolve_ambiguous=resolve
    )
    assert result.outcome == "sl"

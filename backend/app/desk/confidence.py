"""Calibrated confidence (ADR-0007, ADR-0015) — pure code, no LLM.

    confidence = 0.5 x deterministic checklist + 0.5 x panel agreement

The checklist is computed from the Market Brief alone (facts), the agreement
from the divergence report + conviction-weighted votes (the desk). Raw LLM
self-confidence is NEVER an input (ADR-0007: uncalibrated decoration).

Checklist components (each 0..1; a component that cannot be computed from the
brief is EXCLUDED from the average and listed — missing data must not
manufacture signal in either direction, NFR-3):

  mtf_alignment   — alignment.score signed by plan direction, clamped 0..1.
  structure       — the anchor TF's (1h -> 15m -> 4h) structure read:
                    BOS with the plan 1.0 · CHoCH with 0.7 · no event: trend
                    match 0.75 / range 0.5 / oppose 0.25 · CHoCH against
                    0.25 · BOS against 0.0.
  derivatives     — crowding vs the plan (crowded same side = vulnerable):
                    long: negative_extreme 1.0 (shorts pay -> squeeze fuel),
                    negative 0.85, neutral 0.7, positive 0.4,
                    positive_extreme 0.0; short mirrored. Excluded when the
                    brief has no derivatives (spot-only symbol, forex).
  liquidity_room  — distance from the anchor close to the nearest INTACT
                    opposing level (daily levels + anchor-TF equal levels) in
                    ATR units: >= 2 ATR -> 1.0, <= 0.25 ATR -> 0.0, linear
                    between; no intact opposing level -> 1.0 (clear skies).
                    Excluded when no ATR is available.

A no_trade plan has one component: mixed_market = 1 - |alignment.score| —
the choppier the tape, the more confident the desk is in standing aside.

Agreement = 0.5 x state_base (aligned 1.0 / split 0.5 / contested 0.2)
          + 0.5 x conviction-weighted share of survivors voting the plan's
            direction (abstaining seats dilute it — an uneasy risk officer
            SHOULD lower published confidence).

RECALIBRATION (ADR-0018): when a `CalibrationParams` is supplied, each seat's
conviction is multiplied by its learned reliability weight (clamped 0.6–1.4,
shrunk to 1.0 on small samples) and the 0.5/0.5 blend becomes the refit
blend_w. Weights adjust CONFIDENCE only — never direction. With no params
(or none earned yet) the formula is EXACTLY the original, and the breakdown
says `calibrated=False`.

The published value is clamped to [0.05, 0.95] — the desk is never certain —
and rounded to 2dp.
"""

from decimal import Decimal

from app.desk.calibration import CalibrationParams
from app.desk.divergence import ATR_TF_PRIORITY, anchor_atr
from app.models.analyst import AnalystThesis
from app.models.brief import MarketBrief, TimeframeAnalysis
from app.models.tradeplan import ConfidenceBreakdown, Direction, DivergenceReport

STATE_BASE = {"aligned": 1.0, "split": 0.5, "contested": 0.2}
ROOM_FULL_ATR = 2.0  # this much room to opposing liquidity = full marks
ROOM_ZERO_ATR = 0.25  # this close = zero
CLAMP_LO, CLAMP_HI = 0.05, 0.95


def _anchor_tf(brief: MarketBrief) -> TimeframeAnalysis | None:
    for tf in ATR_TF_PRIORITY:
        if tf in brief.timeframes:
            return brief.timeframes[tf]
    return None


def _clamp01(x: float) -> float:
    return max(0.0, min(1.0, x))


def _structure_component(tfa: TimeframeAnalysis, direction: Direction) -> float:
    with_us = "bullish" if direction == "long" else "bearish"
    ev = tfa.structure.last_event
    if ev is not None:
        if ev.direction == with_us:
            return 1.0 if ev.kind == "BOS" else 0.7
        return 0.0 if ev.kind == "BOS" else 0.25
    if tfa.structure.trend == with_us:
        return 0.75
    if tfa.structure.trend == "range":
        return 0.5
    return 0.25


def _derivatives_component(brief: MarketBrief, direction: Direction) -> float | None:
    if brief.derivatives is None:
        return None
    regime = brief.derivatives.funding_regime
    table_long = {
        "negative_extreme": 1.0,
        "negative": 0.85,
        "neutral": 0.7,
        "positive": 0.4,
        "positive_extreme": 0.0,
    }
    if direction == "long":
        return table_long[regime]
    mirror = {
        "positive_extreme": 1.0,
        "positive": 0.85,
        "neutral": 0.7,
        "negative": 0.4,
        "negative_extreme": 0.0,
    }
    return mirror[regime]


def _liquidity_room_component(
    brief: MarketBrief, tfa: TimeframeAnalysis, direction: Direction
) -> float | None:
    atr = anchor_atr(brief)
    if atr is None or atr <= 0:
        return None
    price = tfa.last_close
    levels = [
        lv.price
        for lv in list(brief.daily_levels) + list(tfa.equal_levels)
        if lv.state == "intact"
        and ((direction == "long" and lv.price > price)
             or (direction == "short" and lv.price < price))
    ]
    if not levels:
        return 1.0  # no intact opposing liquidity mapped — clear skies
    nearest = min(levels, key=lambda p: abs(p - price))
    room_atr = float(abs(nearest - price) / atr)
    return _clamp01((room_atr - ROOM_ZERO_ATR) / (ROOM_FULL_ATR - ROOM_ZERO_ATR))


def compute_confidence(
    brief: MarketBrief,
    direction: Direction,
    theses: list[AnalystThesis],
    report: DivergenceReport,
    calibration: CalibrationParams | None = None,
) -> ConfidenceBreakdown:
    components: dict[str, float] = {}
    excluded: list[str] = []

    if direction == "no_trade":
        components["mixed_market"] = round(1.0 - abs(brief.alignment.score), 4)
    else:
        sign = 1.0 if direction == "long" else -1.0
        components["mtf_alignment"] = round(_clamp01(brief.alignment.score * sign), 4)

        tfa = _anchor_tf(brief)
        if tfa is not None:
            components["structure"] = _structure_component(tfa, direction)
        else:
            excluded.append("structure")

        deriv = _derivatives_component(brief, direction)
        if deriv is not None:
            components["derivatives"] = deriv
        else:
            excluded.append("derivatives")

        room = _liquidity_room_component(brief, tfa, direction) if tfa else None
        if room is not None:
            components["liquidity_room"] = round(room, 4)
        else:
            excluded.append("liquidity_room")

    checklist = (
        sum(components.values()) / len(components) if components else 0.5
    )

    # Seat reliability weights (ADR-0018): learned multipliers on conviction.
    # Missing/unlearned seats weigh 1.0; weights NEVER pick the direction —
    # that decision already happened in the divergence detector, unweighted.
    seat_w = calibration.seat_weights if calibration else {}
    state_base = STATE_BASE[report.consensus_state]
    total_conviction = sum(
        t.read.conviction * seat_w.get(t.mandate, 1.0) for t in theses
    )
    agreeing = sum(
        t.read.conviction * seat_w.get(t.mandate, 1.0)
        for t in theses
        if t.read.direction == direction
    )
    weighted_share = (agreeing / total_conviction) if total_conviction else 0.0
    agreement = 0.5 * state_base + 0.5 * weighted_share

    blend_w = calibration.blend_w if calibration else 0.5
    value = max(
        CLAMP_LO, min(CLAMP_HI, blend_w * checklist + (1.0 - blend_w) * agreement)
    )
    calibrated = calibration is not None and (
        blend_w != 0.5 or any(w != 1.0 for w in seat_w.values())
    )

    return ConfidenceBreakdown(
        value=round(value, 2),
        checklist=round(checklist, 4),
        agreement=round(agreement, 4),
        components=components,
        excluded=excluded,
        state_base=state_base,
        weighted_vote_share=round(weighted_share, 4),
        calibrated=calibrated,
        blend_w=round(blend_w, 3),
        seat_weights={m: round(w, 4) for m, w in seat_w.items()} if calibrated else {},
    )


__all__ = ["compute_confidence"]

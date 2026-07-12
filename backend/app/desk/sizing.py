"""Risk-based position sizing (FR-4 · ADR-0015) — pure Decimal math.

The desk risks a fixed, configured fraction of the account per trade
(`risk_pct_per_trade`, default 1%). The position size follows from the stop
distance — tighter stop, larger size; wider stop, smaller size — capped at
`max_position_pct` of account notional so a paper-thin stop can never
recommend an absurd position (the cap is reported, never silent).

    position_pct = risk_pct / stop_distance_pct * 100   (then capped)

Advisory only (invariant 5): this emits percentages, never orders.
"""

from decimal import ROUND_HALF_UP, Decimal

from app.models.tradeplan import SizingOut

_Q = Decimal("0.01")


def position_size(
    entry: Decimal,
    stop: Decimal,
    risk_pct: Decimal = Decimal("1.0"),
    max_position_pct: Decimal = Decimal("100.0"),
) -> SizingOut:
    """Size from entry/stop. Raises ValueError on a degenerate stop —
    the caller treats that as an invalid plan, not a sized one."""
    if entry <= 0:
        raise ValueError("entry must be positive")
    if stop == entry:
        raise ValueError("stop equals entry — no risk distance to size against")
    if risk_pct <= 0:
        raise ValueError("risk_pct must be positive")

    stop_distance_pct = abs(entry - stop) / entry * Decimal("100")
    raw = risk_pct / stop_distance_pct * Decimal("100")
    capped = raw > max_position_pct
    position_pct = min(raw, max_position_pct).quantize(_Q, rounding=ROUND_HALF_UP)

    return SizingOut(
        risk_pct=float(risk_pct),
        stop_distance_pct=float(stop_distance_pct.quantize(_Q, rounding=ROUND_HALF_UP)),
        position_pct=float(position_pct),
        capped=capped,
        implied_leverage=float(
            (position_pct / Decimal("100")).quantize(_Q, rounding=ROUND_HALF_UP)
        ),
    )


__all__ = ["position_size"]

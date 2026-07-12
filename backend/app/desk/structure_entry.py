"""Structure-aware entry/stop/target selection (ADR-0022) — pure, no I/O.

The ADR-0019 directional variants priced everything off raw ATR multiples and
ignored the structure the brief already computes. This module supplies the
missing judgment, deterministically:

  * entries anchor on a real unmitigated order block / FVG on the variant's
    own anchor timeframe (the style's existing `band` constant becomes a
    SEARCH RADIUS in ATR units — scalp still hunts tight, swing still wide)
  * stops sit beyond the genuine invalidation — the FARTHER of the zone's far
    edge and the most recent opposing swing (if either still holds, the
    thesis isn't broken; the wider stop is the honest one)
  * targets are real liquidity: intact equal highs/lows first, then opposing
    unmitigated zones, subject to a minimum R:R floor — never an arbitrary
    ATR projection when a real magnet exists
  * every setup carries an auditable confluence score: discrete points, each
    traced to a named brief fact (NFR-7 — no opaque quality numbers)

When no structure qualifies, the caller falls back to the ADR-0019 ATR math
byte-for-byte, labeled `entry_kind="atr_fallback"` — honest, never hidden.

Every constant here is a money-risk constant pinned by golden tests
(tests/test_setups.py); changing one is a new-ADR decision, not an edit.
"""

from datetime import datetime, timedelta
from decimal import ROUND_HALF_UP, Decimal
from typing import Literal

from app.models.brief import TimeframeAnalysis, ZoneOut
from app.models.setups import VariantTarget

Direction = Literal["long", "short"]

# Stop buffer past the invalidation line, in ATR units. Small relative to every
# style's stop multiple (0.6–2.0) — it clears the exact level without changing
# the style's risk character.
STOP_BUFFER_ATR = Decimal("0.10")

# A structural target must pay at least this many R or it is rejected and the
# style's published ratio table takes over. Set BELOW the smallest published
# ratio (1.5) so it acts as a true floor for real-but-near liquidity, not a
# restatement of the table.
MIN_RR_FLOOR = Decimal("1.2")

# A zone older than this many bars on its own anchor TF is stale context, not
# the current setup. A designed judgment call (stated in ADR-0022), same order
# of magnitude as the brief's swing/zone lookback caps.
FRESHNESS_BARS = 20

# Relative price tolerance for "this zone sits on an equal-level cluster".
EQUAL_LEVEL_TOLERANCE = Decimal("0.0015")  # 0.15%

TF_DELTA: dict[str, timedelta] = {
    "15m": timedelta(minutes=15),
    "1h": timedelta(hours=1),
    "4h": timedelta(hours=4),
}

_RR_Q = Decimal("0.01")


def quantize_level(value: Decimal, ref: Decimal) -> Decimal:
    """Quantize a price to a sane precision inferred from the reference close:
    at least 2 decimals (a round close like 100 must not collapse levels to
    integers), up to 8 (sub-cent alt/forex precision preserved).
    (Moved here from desk/setups.py so both modules share one quantizer.)"""
    exp = ref.normalize().as_tuple().exponent
    places = max(2, min(8, -exp)) if isinstance(exp, int) else 2
    return value.quantize(Decimal(1).scaleb(-places), rounding=ROUND_HALF_UP)


def select_entry_zone(
    tfa: TimeframeAnalysis,
    direction: Direction,
    close: Decimal,
    atr: Decimal,
    search: Decimal,
) -> ZoneOut | None:
    """The nearest unmitigated same-side zone that offers a genuine pullback
    within the style's search radius (`search` × ATR — a per-style patience
    constant, NOT the fallback band width: live measurement showed real zones
    form 0.4–8 ATR behind price, so reusing the tiny band constants would
    have made this path near-unreachable; ADR-0022 §1). Zones straddling the
    current price are excluded on purpose: a limit at the zone's near edge
    would sit on the wrong side of the market and fill instantly at a
    worse-than-market price — a dishonest simulated entry.
    Ties (identical distance) prefer order blocks over FVGs: committed orders
    over inefficiency gaps."""
    side = "bullish" if direction == "long" else "bearish"
    radius = search * atr
    best: tuple[Decimal, int, ZoneOut] | None = None
    for zone in list(tfa.order_blocks) + list(tfa.fvgs):
        if zone.side != side or zone.mitigated:
            continue
        if direction == "long":
            if zone.top > close:
                continue
            dist = close - zone.top
        else:
            if zone.bottom < close:
                continue
            dist = zone.bottom - close
        if dist > radius:
            continue
        rank = (dist, 0 if zone.kind == "order_block" else 1)
        if best is None or rank < (best[0], best[1]):
            best = (rank[0], rank[1], zone)
    return best[2] if best else None


def structure_stop(
    tfa: TimeframeAnalysis,
    direction: Direction,
    zone: ZoneOut,
    close: Decimal,
    atr: Decimal,
) -> Decimal:
    """The honest invalidation: beyond the zone's far edge, widened to beyond
    the most recent opposing swing when that swing sits farther out. If either
    level still holds, the thesis isn't broken — so the FARTHER (more
    conservative) of the two is the stop. A swing is only used when it is
    strictly farther than the zone stop, which also guards against noisy
    swings on the wrong side of price producing a nonsensical level."""
    buf = STOP_BUFFER_ATR * atr
    if direction == "long":
        stop = zone.bottom - buf
        for swing in reversed(tfa.swings):  # brief swings are chronological
            if swing.kind == "low" and swing.price < close:
                candidate = swing.price - buf
                if candidate < stop:
                    stop = candidate
                break
    else:
        stop = zone.top + buf
        for swing in reversed(tfa.swings):
            if swing.kind == "high" and swing.price > close:
                candidate = swing.price + buf
                if candidate > stop:
                    stop = candidate
                break
    return stop


def search_targets(
    tfa: TimeframeAnalysis,
    direction: Direction,
    entry: Decimal,
    stop: Decimal,
    tps: tuple[Decimal, ...],
    stop_mult: Decimal,
    ref: Decimal,
) -> list[VariantTarget]:
    """Real targets first: intact equal levels (the liquidity pool price is
    drawn to) and opposing unmitigated zones' NEAR edges (don't assume price
    punches through), nearest first, equal levels preferred at equal distance.
    A structural TP1 must pay >= MIN_RR_FLOOR against the real stop; if none
    qualifies, BOTH targets come from the style's published ratio table
    rescaled onto the new stop distance (tp = entry ± ratio×R), so published
    R:R ratios hold exactly even in fallback. Structural targets may be one or
    two (a second is used only if a farther candidate exists) — provenance is
    never mixed within the pair beyond that ordering rule (ADR-0022 §3)."""
    risk = abs(entry - stop)
    if risk <= 0:  # cannot happen by construction (stop carries an ATR buffer)
        return _fallback_targets(direction, entry, risk, tps, stop_mult, ref)

    sign = Decimal(1) if direction == "long" else Decimal(-1)
    eq_kind = "EQH" if direction == "long" else "EQL"
    opp_side = "bearish" if direction == "long" else "bullish"

    # (distance, priority, price): priority 0 = equal level, 1 = zone edge.
    candidates: list[tuple[Decimal, int, Decimal]] = []
    for level in tfa.equal_levels:
        if level.kind != eq_kind or level.state != "intact":
            continue
        dist = sign * (level.price - entry)
        if dist > 0:
            candidates.append((dist, 0, level.price))
    for zone in list(tfa.order_blocks) + list(tfa.fvgs):
        if zone.side != opp_side or zone.mitigated:
            continue
        near_edge = zone.bottom if direction == "long" else zone.top
        dist = sign * (near_edge - entry)
        if dist > 0:
            candidates.append((dist, 1, near_edge))
    candidates.sort(key=lambda c: (c[0], c[1]))

    qualified = [c for c in candidates if c[0] / risk >= MIN_RR_FLOOR]
    if not qualified:
        return _fallback_targets(direction, entry, risk, tps, stop_mult, ref)

    out = [_target(qualified[0][2], qualified[0][0] / risk, ref)]
    farther = [c for c in qualified[1:] if c[0] > qualified[0][0]]
    if farther:
        out.append(_target(farther[0][2], farther[0][0] / risk, ref))
    return out


def _target(price: Decimal, rr: Decimal, ref: Decimal) -> VariantTarget:
    return VariantTarget(
        price=quantize_level(price, ref),
        rr=float(rr.quantize(_RR_Q, rounding=ROUND_HALF_UP)),
    )


def _fallback_targets(
    direction: Direction,
    entry: Decimal,
    risk: Decimal,
    tps: tuple[Decimal, ...],
    stop_mult: Decimal,
    ref: Decimal,
) -> list[VariantTarget]:
    sign = Decimal(1) if direction == "long" else Decimal(-1)
    return [
        _target(entry + sign * (m / stop_mult) * risk, m / stop_mult, ref)
        for m in tps
    ]


def score_confluence(
    tfa: TimeframeAnalysis,
    direction: Direction,
    zone: ZoneOut | None,
    anchor_tf: str,
    generated_at: datetime,
) -> tuple[Literal["high", "medium", "low"], list[str]]:
    """Discrete, auditable confluence points — each traced to a named brief
    fact, never a blended opaque score (NFR-7). ATR-fallback entries (no zone)
    can only ever earn the premium/discount and structure-event points, so
    they cap at "medium" — an honest fallback is never allowed to claim top
    quality (ADR-0022 §4).

      >= 3 points -> high · == 2 -> medium · <= 1 -> low
    """
    points = 0
    reasons: list[str] = []

    if zone is not None:
        zone_name = "order block" if zone.kind == "order_block" else "FVG"
        points += 1
        reasons.append(f"structure-anchored entry ({zone_name})")

        # Zone sits on an equal-level liquidity cluster of the matching side
        # (equal lows under a long entry, equal highs over a short entry).
        cluster_kind = "EQL" if direction == "long" else "EQH"
        for level in tfa.equal_levels:
            if level.kind != cluster_kind or level.state != "intact":
                continue
            near = min(
                abs(level.price - zone.top) / zone.top if zone.top else Decimal(1),
                abs(level.price - zone.bottom) / zone.bottom if zone.bottom else Decimal(1),
            )
            if near <= EQUAL_LEVEL_TOLERANCE:
                points += 1
                reasons.append(f"aligned with intact {cluster_kind} liquidity cluster")
                break

        delta = TF_DELTA.get(anchor_tf)
        if delta is not None and zone.time >= generated_at - FRESHNESS_BARS * delta:
            points += 1
            reasons.append(f"fresh {zone_name} (within last {FRESHNESS_BARS} {anchor_tf} candles)")

    wanted = "discount" if direction == "long" else "premium"
    if tfa.premium_discount == wanted:
        points += 1
        reasons.append(f"entry sits in a {wanted} zone")

    event = tfa.structure.last_event
    if event is not None:
        matches = event.direction == ("bullish" if direction == "long" else "bearish")
        confirms_zone = zone is None or event.time >= zone.time
        if matches and confirms_zone:
            points += 1
            reasons.append(f"confirmed by recent {event.kind}")

    quality: Literal["high", "medium", "low"] = (
        "high" if points >= 3 else "medium" if points == 2 else "low"
    )
    return quality, reasons


__all__ = [
    "STOP_BUFFER_ATR",
    "MIN_RR_FLOOR",
    "FRESHNESS_BARS",
    "EQUAL_LEVEL_TOLERANCE",
    "quantize_level",
    "select_entry_zone",
    "structure_stop",
    "search_targets",
    "score_confluence",
]

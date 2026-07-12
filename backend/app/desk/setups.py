"""Setup variant engine (FR-4 variant fan, v1 · ADR-0019) — pure code, no AI.

Each variant is an ATR-rule transformation of the brief, sized to its own
anchor timeframe. All levels measure from the anchor TF's last_close via the
entry-band midpoint, so R:R is exact by construction (tp_mult / stop_mult).

Long (short mirrored), entry band = [close − band·ATR, close] (buy the dip to
current; shorts sell the pop):

  key       venue     lev  anchor  band   stop   TP1    TP2     RR1 / RR2
  scalp     PERP      5x   15m     0.15   0.60   0.90   1.50    1.5 / 2.5
  intraday  PERP      3x   1h      0.25   1.00   1.50   2.50    1.5 / 2.5
  swing     MARGIN    2x   4h      0.40   1.50   2.25   4.00    1.5 / 2.67
  spot      SPOT      1x   4h      0.50   2.00   3.00   5.00    1.5 / 2.5
  grid      GRID BOT  1x   1h      range = close ± 1.5·ATR (chop harvest)
  options   OPTIONS   1x   1d      covered-call strike = close + 1.5·ATR

Gating (the honesty rules):
  * Directional variants (scalp/intraday/swing/spot) need a directional MTF
    bias — `alignment.bias == "mixed"` -> tradeable=False ("stand aside").
  * The grid is the inverse: it harvests chop, so it's tradeable ONLY when the
    bias is mixed.
  * Options is informational v1 (needs held spot; no TP/SL semantics).
  * grid/options are never `gradeable` — a TP/SL candle-walk doesn't describe
    their outcome; only the 4 directional variants join the journal loop.
  * Missing ATR on a variant's anchor TF -> that variant is untradeable.

Structure-aware pass (ADR-0022): each directional variant first hunts a real
unmitigated order block / FVG on its own anchor TF (its `band` constant is
the ATR-unit search radius), stops beyond the genuine invalidation, targets
real liquidity — see desk/structure_entry.py. When no structure qualifies it
falls back to the ADR-0019 ATR math byte-for-byte, labeled
`entry_kind="atr_fallback"`. AUTOMATIC multiplier tuning from outcomes was
considered and REJECTED (ADR-0019 §4): silent self-tuning on small samples
is an overfit factory.
"""

from dataclasses import dataclass
from decimal import ROUND_HALF_UP, Decimal

from app.desk.structure_entry import (
    quantize_level,
    score_confluence,
    search_targets,
    select_entry_zone,
    structure_stop,
)
from app.models.brief import MarketBrief
from app.models.setups import SetupVariant, SetupsResponse, VariantTarget

_RR_Q = Decimal("0.01")


@dataclass(frozen=True)
class _Rule:
    key: str
    venue: str
    style: str
    leverage: int
    anchor_tf: str
    band: Decimal  # ATR-fallback entry-band width (ADR-0019, unchanged)
    stop: Decimal
    tps: tuple[Decimal, ...]
    # Zone-search radius in anchor-TF ATR units (ADR-0022) — each style's
    # patience horizon. Distinct from `band` on purpose: live measurement
    # showed real zones sit 0.4–8 ATR behind price, far outside the band.
    search: Decimal
    edge: str
    edge_bn: str


_DIRECTIONAL: tuple[_Rule, ...] = (
    _Rule(
        "scalp", "PERP", "5x scalp", 5, "15m",
        Decimal("0.15"), Decimal("0.6"), (Decimal("0.9"), Decimal("1.5")),
        Decimal("1.0"),  # a scalp only trades the zone being tapped right now
        "Fast in-and-out on the 15m impulse; tight stop, take profit quickly.",
        "১৫ মিনিটের গতিতে দ্রুত ঢোকা-বের হওয়া; ছোট স্টপ, দ্রুত লাভ তোলা।",
    ),
    _Rule(
        "intraday", "PERP", "3x intraday", 3, "1h",
        Decimal("0.25"), Decimal("1.0"), (Decimal("1.5"), Decimal("2.5")),
        Decimal("1.5"),  # today's pullback, not last week's
        "The desk's default: ride the 1h structure for the day, out by close.",
        "ডেস্কের মূল স্টাইল: ১ ঘণ্টার কাঠামো ধরে দিনের ট্রেড, দিনশেষে বের।",
    ),
    _Rule(
        "swing", "MARGIN", "2x swing", 2, "4h",
        Decimal("0.40"), Decimal("1.5"), (Decimal("2.25"), Decimal("4.0")),
        Decimal("2.5"),  # a swing waits for the deeper 4h retrace
        "Multi-day hold on the 4h trend; wider stop buys time to be right.",
        "৪ ঘণ্টার ট্রেন্ডে কয়েক দিনের হোল্ড; বড় স্টপ মানে ভুল শোধরানোর সময়।",
    ),
    _Rule(
        "spot", "SPOT", "spot accumulate", 1, "4h",
        Decimal("0.50"), Decimal("2.0"), (Decimal("3.0"), Decimal("5.0")),
        Decimal("3.0"),  # accumulation is the most patient hunter
        "No leverage, no liquidation: accumulate the dip, patience is the edge.",
        "লিভারেজ নেই, লিকুইডেশন নেই: ডিপে জমানো — ধৈর্যই এখানে সুবিধা।",
    ),
)

_GRID_RANGE = Decimal("1.5")  # close ± 1.5 x ATR(1h)
_OPTIONS_STRIKE = Decimal("1.5")  # covered-call strike offset, ATR(1d)
_MIXED_REASON = "mixed multi-timeframe alignment — the desk stands aside"


def _atr(brief: MarketBrief, tf: str) -> Decimal | None:
    tfa = brief.timeframes.get(tf)
    if tfa is None or tfa.indicators.atr14 is None:
        return None
    atr = Decimal(str(tfa.indicators.atr14))
    return atr if atr > 0 else None


def _close(brief: MarketBrief, tf: str) -> Decimal | None:
    tfa = brief.timeframes.get(tf)
    return tfa.last_close if tfa is not None else None


# One shared quantizer (ADR-0022 moved it beside the structure logic).
_q = quantize_level


def build_variants(brief: MarketBrief) -> list[SetupVariant]:
    bias = brief.alignment.bias  # "long" | "short" | "mixed"
    out: list[SetupVariant] = []

    for r in _DIRECTIONAL:
        atr = _atr(brief, r.anchor_tf)
        close = _close(brief, r.anchor_tf)
        tfa = brief.timeframes.get(r.anchor_tf)
        base = dict(
            key=r.key, venue=r.venue, style=r.style, leverage=r.leverage,
            anchor_tf=r.anchor_tf, edge=r.edge, edge_bn=r.edge_bn, gradeable=True,
        )
        if bias == "mixed":
            out.append(SetupVariant(**base, direction="neutral", tradeable=False, reason=_MIXED_REASON))
            continue
        if atr is None or close is None or tfa is None:
            out.append(SetupVariant(
                **base, direction=bias, tradeable=False,
                reason=f"no ATR on the {r.anchor_tf} anchor timeframe",
            ))
            continue

        # ── ADR-0022: structure first — a real unmitigated zone within the
        #    style's search radius anchors the entry; the honest fallback is
        #    the ADR-0019 ATR band, byte-for-byte, labeled as such. ──
        zone = select_entry_zone(tfa, bias, close, atr, r.search)
        if zone is not None:
            entry_kind = "structure"
            lo, hi = zone.bottom, zone.top
            # The band IS the zone; R math measures from its near edge — the
            # same worse edge the ADR-0020 backtest fills at (first touch).
            entry_ref = zone.top if bias == "long" else zone.bottom
            stop = structure_stop(tfa, bias, zone, close, atr)
            targets = search_targets(tfa, bias, entry_ref, stop, r.tps, r.stop, close)
        else:
            entry_kind = "atr_fallback"
            sign = Decimal(1) if bias == "long" else Decimal(-1)
            lo = close - r.band * atr if bias == "long" else close
            hi = close if bias == "long" else close + r.band * atr
            mid = (lo + hi) / 2
            stop = mid - sign * r.stop * atr
            targets = [
                VariantTarget(
                    price=_q(mid + sign * m * atr, close),
                    rr=float((m / r.stop).quantize(_RR_Q, rounding=ROUND_HALF_UP)),
                )
                for m in r.tps
            ]

        quality, confluence = score_confluence(
            tfa, bias, zone, r.anchor_tf, brief.generated_at
        )
        out.append(SetupVariant(
            **base, direction=bias, tradeable=True,
            entry_low=_q(lo, close), entry_high=_q(hi, close), stop=_q(stop, close),
            targets=targets,
            entry_kind=entry_kind, quality=quality, confluence=confluence,
        ))

    # ── grid: harvests chop — tradeable exactly when the desk has NO bias ──
    atr1h, close1h = _atr(brief, "1h"), _close(brief, "1h")
    grid_base = dict(
        key="grid", venue="GRID BOT", style="range harvest", leverage=1,
        anchor_tf="1h", gradeable=False,
        edge="Buys low / sells high inside the range; earns while price chops.",
        edge_bn="রেঞ্জের ভেতর নিচে কেনে-উপরে বেচে; দাম এদিক-ওদিক করলেই আয়।",
    )
    if bias == "mixed" and atr1h is not None and close1h is not None:
        out.append(SetupVariant(
            **grid_base, direction="neutral", tradeable=True,
            entry_low=_q(close1h - _GRID_RANGE * atr1h, close1h),
            entry_high=_q(close1h + _GRID_RANGE * atr1h, close1h),
        ))
    else:
        out.append(SetupVariant(
            **grid_base, direction="neutral", tradeable=False,
            reason=(
                "trending market — a grid gets run over; wait for a range"
                if bias != "mixed" else "no ATR on the 1h anchor timeframe"
            ),
        ))

    # ── options: informational v1 (needs held spot; not gradeable) ──
    atr1d, close1d = _atr(brief, "1d"), _close(brief, "1d")
    opt_base = dict(
        key="options", venue="OPTIONS", style="covered call", leverage=1,
        anchor_tf="1d", gradeable=False, direction="neutral", tradeable=False,
        edge="Income against held spot: sell the call above the daily range.",
        edge_bn="হাতে থাকা স্পটের বিপরীতে আয়: দৈনিক রেঞ্জের উপরে কল বেচা।",
    )
    if atr1d is not None and close1d is not None:
        strike = _q(close1d + _OPTIONS_STRIKE * atr1d, close1d)
        out.append(SetupVariant(
            **opt_base, entry_low=strike, entry_high=strike,
            reason="informational — requires held spot (v1 does not track holdings)",
        ))
    else:
        out.append(SetupVariant(**opt_base, reason="no ATR on the 1d anchor timeframe"))

    return out


__all__ = ["build_variants"]

"""Alert rules (P3 · FR-5) — deterministic detection over one Market Brief.

`scan_brief` reads only fields the engine already computed and emits notable
CURRENT conditions (structure event, liquidity sweep, funding/OI extreme, price
near a fresh zone, sentiment extreme). Thresholds are config (config/alerts.yaml
→ `AlertThresholds`), never hard-coded constants (invariant 6). All price math is
`Decimal` (invariant 3). Change-since-last-scan alerts are the background
scanner's job (later P3) — this is the point-in-time layer it will diff.
"""

from __future__ import annotations

from decimal import Decimal
from pathlib import Path

import yaml
from pydantic import BaseModel, Field

from app.models.alerts import AlertEvent
from app.models.brief import MarketBrief


class AlertThresholds(BaseModel):
    oi_spike_pct: float = 5.0
    zone_proximity_pct: Decimal = Decimal("0.5")  # within X% of a fresh OB/FVG edge
    fng_low: int = 20
    fng_high: int = 80
    structure_timeframes: list[str] = Field(default_factory=lambda: ["1h", "4h"])
    zone_timeframes: list[str] = Field(default_factory=lambda: ["15m", "1h"])
    sweep_timeframes: list[str] = Field(default_factory=lambda: ["15m", "1h"])
    max_sweeps: int = 3


def load_thresholds(path: str | Path) -> AlertThresholds:
    p = Path(path)
    if not p.exists():
        return AlertThresholds()
    data = yaml.safe_load(p.read_text(encoding="utf-8")) or {}
    return AlertThresholds(**data)


def _fmt(v: Decimal) -> str:
    """Display price: thousands-grouped, trailing zeros trimmed."""
    s = f"{v:,.6f}".rstrip("0").rstrip(".")
    return s or "0"


def scan_brief(brief: MarketBrief, th: AlertThresholds) -> list[AlertEvent]:
    at = brief.generated_at
    sym = brief.symbol
    out: list[AlertEvent] = []

    # ── Structure events (BOS = with-trend, CHoCH = reversal warning) ──
    for tf in th.structure_timeframes:
        t = brief.timeframes.get(tf)
        if not t or not t.structure.last_event:
            continue
        e = t.structure.last_event
        up = e.direction == "bullish"
        arrow = "▲" if up else "▼"
        lvl = _fmt(e.level)
        if e.kind == "BOS":
            out.append(AlertEvent(
                kind="structure_break", symbol=sym, timeframe=tf, tone="bull" if up else "bear",
                message=f"BOS {arrow} · {tf} @ {lvl}",
                message_bn=f"{tf}-এ কাঠামো {'উপরে' if up else 'নিচে'} ভাঙল (BOS) @ {lvl} — ট্রেন্ড চালু",
                at=at, ref=lvl,
            ))
        else:  # CHoCH — character change, caution
            out.append(AlertEvent(
                kind="structure_break", symbol=sym, timeframe=tf, tone="warn",
                message=f"CHoCH {arrow} · {tf} @ {lvl}",
                message_bn=f"{tf}-এ চরিত্র বদল (CHoCH) @ {lvl} — ট্রেন্ড ঘোরার ইঙ্গিত, সাবধান",
                at=at, ref=lvl,
            ))

    # ── Liquidity sweeps (daily levels + equal highs/lows) ──
    swept = [lv for lv in brief.daily_levels if lv.state == "swept"]
    for tf in th.sweep_timeframes:
        t = brief.timeframes.get(tf)
        if t:
            swept += [lv for lv in t.equal_levels if lv.state == "swept"]
    for lv in swept[: th.max_sweeps]:
        px = _fmt(lv.price)
        out.append(AlertEvent(
            kind="liquidity_sweep", symbol=sym, timeframe=None, tone="warn",
            message=f"{lv.kind} swept @ {px}",
            message_bn=f"{lv.kind} সুইপ হলো @ {px} — স্টপ নেওয়া শেষ, উল্টো চাল সম্ভব",
            at=at, ref=px,
        ))

    # ── Derivatives: funding extreme + OI spike ──
    d = brief.derivatives
    if d is not None:
        if d.funding_regime.endswith("extreme"):
            pos = d.funding_regime.startswith("positive")
            side = "long" if pos else "short"
            side_bn = "লং-দের ভিড়" if pos else "শর্টদের ভিড়"
            out.append(AlertEvent(
                kind="funding_extreme", symbol=sym, timeframe=None, tone="warn",
                message=f"Funding extreme ({'positive' if pos else 'negative'}) — {side} squeeze risk",
                message_bn=f"ফান্ডিং চরম {'পজিটিভ' if pos else 'নেগেটিভ'} — {side_bn}, স্কুইজের ঝুঁকি",
                at=at,
            ))
        oi = d.oi_change_24h_pct
        if oi is not None and abs(oi) >= th.oi_spike_pct:
            building = oi > 0
            out.append(AlertEvent(
                kind="oi_spike", symbol=sym, timeframe=None, tone="pulse",
                message=f"OI {oi:+.1f}% — {'new money building' if building else 'positions unwinding'}",
                message_bn=f"ওপেন ইন্টারেস্ট {oi:+.1f}% — {'নতুন টাকা ঢুকছে' if building else 'পজিশন বন্ধ হচ্ছে'}",
                at=at,
            ))

    # ── Price near a fresh (unmitigated) order block / FVG ──
    for tf in th.zone_timeframes:
        t = brief.timeframes.get(tf)
        if not t:
            continue
        price = t.last_close
        best: tuple[Decimal, object] | None = None
        for z in [*t.order_blocks, *t.fvgs]:
            if z.mitigated:
                continue
            if z.bottom <= price <= z.top:
                dist = Decimal(0)
            elif price < z.bottom:
                dist = z.bottom - price
            else:
                dist = price - z.top
            pct = (dist / price * 100) if price else Decimal(0)
            if pct <= th.zone_proximity_pct and (best is None or pct < best[0]):
                best = (pct, z)
        if best is not None:
            z = best[1]
            label = "OB" if z.kind == "order_block" else "FVG"  # type: ignore[attr-defined]
            band = f"{_fmt(z.bottom)}–{_fmt(z.top)}"  # type: ignore[attr-defined]
            out.append(AlertEvent(
                kind="zone_proximity", symbol=sym, timeframe=tf, tone="pulse",
                message=f"Price near fresh {label} · {tf} @ {band}",
                message_bn=f"দাম টাটকা {label}-এর কাছে · {tf} @ {band} — প্রতিক্রিয়ার সম্ভাবনা",
                at=at,
            ))

    # ── Sentiment extremes ──
    s = brief.sentiment
    if s is not None:
        if s.fear_greed <= th.fng_low:
            out.append(AlertEvent(
                kind="sentiment_extreme", symbol=sym, timeframe=None, tone="pulse",
                message=f"Extreme Fear ({s.fear_greed}) — often a bounce zone",
                message_bn=f"চরম ভয় ({s.fear_greed}) — প্রায়ই কেনার সুযোগ",
                at=at,
            ))
        elif s.fear_greed >= th.fng_high:
            out.append(AlertEvent(
                kind="sentiment_extreme", symbol=sym, timeframe=None, tone="warn",
                message=f"Extreme Greed ({s.fear_greed}) — caution",
                message_bn=f"চরম লোভ ({s.fear_greed}) — সাবধান, টপ কাছে হতে পারে",
                at=at,
            ))

    return out

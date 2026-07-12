"""Market Brief composer — fans out to adapters, runs the engine, assembles facts.

Required: spot klines on 15m/1h/4h (failure = AdapterError up to the route).
Optional: daily levels, derivatives, sentiment — each failure degrades into an
entry in `gaps` instead of failing the run (NFR-3).

Asset-class aware (P4): a forex symbol (EURUSD) is fetched from Twelve Data and
run through the SAME quant engine as crypto — full SMC/structure/TA parity. The
crypto-only context (funding/OI/L-S, Fear & Greed) is simply absent for forex
and noted in `gaps`; forex's own context (DXY, COT, sessions) lands in later P4.
"""

import asyncio
from datetime import datetime, timezone

from app.adapters.alternative_me import AlternativeMeAdapter
from app.adapters.base import AdapterError
from app.adapters.binance import BinanceAdapter
from app.adapters.binance_futures import BinanceFuturesAdapter
from app.adapters.twelvedata import TwelveDataAdapter
from app.markets import asset_class
from app.models.brief import (
    AlignmentOut,
    DerivativesOut,
    IndicatorsOut,
    LevelOut,
    MarketBrief,
    SentimentOut,
    StructureEventOut,
    StructureOut,
    SwingOut,
    TimeframeAnalysis,
    ZoneOut,
)
from app.models.market import Candle
from app.quant import ta
from app.quant.liquidity import daily_weekly_levels, equal_levels
from app.quant.structure import analyze_structure, premium_discount
from app.quant.swings import detect_swings
from app.quant.zones import Zone, detect_fvgs, detect_order_blocks

# Analysis set shown on the chart + structure rail. 5m and 1d are additive
# context; the intraday core (below) still owns the alignment score so the
# money-risk signal keeps its established meaning (ADR-0007, unchanged).
TIMEFRAMES = ("5m", "15m", "1h", "4h", "1d")
ALIGNMENT_TIMEFRAMES = ("15m", "1h", "4h")
KLINE_LIMIT = 200
SWING_K = 2
MAX_SWINGS_OUT = 8
MAX_ZONES_PER_SIDE = 3
MAX_EQUAL_LEVELS = 4

# Binance funding is a per-8h decimal; 0.0001 (0.01%) is the neutral baseline.
FUNDING_EXTREME = 0.0005
FUNDING_ELEVATED = 0.00015


def funding_regime(rate: float) -> str:
    if rate >= FUNDING_EXTREME:
        return "positive_extreme"
    if rate >= FUNDING_ELEVATED:
        return "positive"
    if rate <= -FUNDING_EXTREME:
        return "negative_extreme"
    if rate <= -FUNDING_ELEVATED:
        return "negative"
    return "neutral"


def analyze_timeframe(tf: str, candles: list[Candle]) -> TimeframeAnalysis:
    """Pure function: one timeframe's candles -> one TimeframeAnalysis block."""
    swings = detect_swings(candles, k=SWING_K)
    structure = analyze_structure(candles, swing_k=SWING_K)
    atr_series = ta.atr(candles, 14)

    def zone_out(zones: list[Zone]) -> list[ZoneOut]:
        # Most recent origins first; unmitigated preferred; hard cap per side.
        picked: list[Zone] = []
        for side in ("bullish", "bearish"):
            side_zones = sorted(
                (z for z in zones if z.side == side),
                key=lambda z: (z.mitigated, -z.index),
            )[:MAX_ZONES_PER_SIDE]
            picked.extend(side_zones)
        return [
            ZoneOut(
                kind=z.kind, side=z.side, top=z.top, bottom=z.bottom,
                mitigated=z.mitigated, time=z.time,
            )
            for z in sorted(picked, key=lambda z: z.index)
        ]

    last_event = structure.last_event
    closes = ta.closes(candles)
    macd_line, macd_signal, macd_hist = ta.macd(closes)
    bb_upper, bb_mid, bb_lower = ta.bollinger(closes)

    return TimeframeAnalysis(
        tf=tf,
        last_close=candles[-1].close,
        structure=StructureOut(
            trend=structure.trend,
            last_event=(
                StructureEventOut(
                    kind=last_event.kind,
                    direction=last_event.direction,
                    level=last_event.broken_level,
                    time=last_event.time,
                )
                if last_event
                else None
            ),
        ),
        premium_discount=premium_discount(candles, swings),
        swings=[
            SwingOut(time=s.time, price=s.price, kind=s.kind)
            for s in swings[-MAX_SWINGS_OUT:]
        ],
        order_blocks=zone_out(detect_order_blocks(candles, atr_series)),
        fvgs=zone_out(detect_fvgs(candles, atr_series)),
        equal_levels=[
            LevelOut(kind=lv.kind, price=lv.price, state=lv.state)
            for lv in equal_levels(swings, candles)[-MAX_EQUAL_LEVELS:]
        ],
        indicators=IndicatorsOut(
            ema20=ta.last(ta.ema(closes, 20)),
            ema50=ta.last(ta.ema(closes, 50)),
            ema200=ta.last(ta.ema(closes, 200)),
            rsi14=ta.last(ta.rsi(closes, 14)),
            macd=ta.last(macd_line),
            macd_signal=ta.last(macd_signal),
            macd_hist=ta.last(macd_hist),
            atr14=ta.last(atr_series),
            bb_upper=ta.last(bb_upper),
            bb_mid=ta.last(bb_mid),
            bb_lower=ta.last(bb_lower),
            vwap=ta.last(ta.vwap(candles)),
        ),
    )


def compute_alignment(timeframes: dict[str, TimeframeAnalysis]) -> AlignmentOut:
    value = {"bullish": 1, "bearish": -1, "range": 0}
    per_tf = {tf: t.structure.trend for tf, t in timeframes.items()}
    score = sum(value[t] for t in per_tf.values()) / max(len(per_tf), 1)
    bias = "long" if score > 0.34 else "short" if score < -0.34 else "mixed"
    return AlignmentOut(score=round(score, 2), bias=bias, per_tf=per_tf)


class BriefComposer:
    def __init__(
        self,
        spot: BinanceAdapter,
        futures: BinanceFuturesAdapter,
        sentiment: AlternativeMeAdapter,
        forex: TwelveDataAdapter | None = None,
    ) -> None:
        self._spot = spot
        self._futures = futures
        self._sentiment = sentiment
        self._forex = forex

    async def compose(self, symbol: str) -> MarketBrief:
        symbol = symbol.upper()
        if asset_class(symbol) == "forex":
            return await self._compose_forex(symbol)
        return await self._compose_crypto(symbol)

    async def _compose_forex(self, symbol: str) -> MarketBrief:
        """Forex path: OHLCV from Twelve Data → the same engine. No derivatives
        or Fear & Greed (crypto-only); those become `gaps`, not failures."""
        if self._forex is None:
            raise AdapterError("twelvedata", "no forex data source configured")
        gaps: list[str] = []

        series = await asyncio.gather(
            *(self._forex.get_klines(symbol, tf, KLINE_LIMIT) for tf in TIMEFRAMES)
        )
        raw = dict(zip(TIMEFRAMES, series))
        timeframes = {tf: analyze_timeframe(tf, candles) for tf, candles in raw.items()}

        daily_levels: list[LevelOut] = []
        try:
            daily = await self._forex.get_klines(symbol, "1d", 10)
            daily_levels = [
                LevelOut(kind=lv.kind, price=lv.price, state=lv.state)
                for lv in daily_weekly_levels(daily, raw["15m"])
            ]
        except AdapterError as exc:
            gaps.append(f"daily_levels unavailable: {_why(exc)}")

        gaps.append("derivatives: n/a for forex spot (funding/OI/L-S are crypto-only)")
        gaps.append("fear_greed: crypto-only sentiment index; forex n/a")
        gaps.append("volume: forex is decentralized — no consolidated volume (VWAP off)")
        gaps.append("dxy / cot / session-context: scheduled with later P4")

        return MarketBrief(
            symbol=symbol,
            generated_at=datetime.now(timezone.utc),
            timeframes=timeframes,
            daily_levels=daily_levels,
            derivatives=None,
            sentiment=None,
            alignment=compute_alignment(
                {tf: timeframes[tf] for tf in ALIGNMENT_TIMEFRAMES}
            ),
            gaps=gaps,
        )

    async def _compose_crypto(self, symbol: str) -> MarketBrief:
        gaps: list[str] = []

        series = await asyncio.gather(
            *(self._spot.get_klines(symbol, tf, KLINE_LIMIT) for tf in TIMEFRAMES)
        )
        raw = dict(zip(TIMEFRAMES, series))
        timeframes = {tf: analyze_timeframe(tf, candles) for tf, candles in raw.items()}

        # PDH/PDL/PWH/PWL want only the last ~2 weeks of daily candles; sweep
        # state is judged against the 15m tape.
        daily_task = self._spot.get_klines(symbol, "1d", 10)
        funding_task = self._futures.get_funding(symbol)
        oi_task = self._futures.get_open_interest_change(symbol)
        ls_task = self._futures.get_long_short_ratio(symbol)
        fng_task = self._sentiment.get_fear_greed()
        daily_res, funding_res, oi_res, ls_res, fng_res = await asyncio.gather(
            daily_task, funding_task, oi_task, ls_task, fng_task,
            return_exceptions=True,
        )

        daily_levels: list[LevelOut] = []
        if isinstance(daily_res, BaseException):
            gaps.append(f"daily_levels unavailable: {_why(daily_res)}")
        else:
            daily_levels = [
                LevelOut(kind=lv.kind, price=lv.price, state=lv.state)
                for lv in daily_weekly_levels(daily_res, raw["15m"])
            ]

        derivatives: DerivativesOut | None = None
        if isinstance(funding_res, BaseException):
            gaps.append(f"derivatives unavailable: {_why(funding_res)}")
        else:
            oi = None if isinstance(oi_res, BaseException) else oi_res
            if oi is None:
                gaps.append(f"open_interest unavailable: {_why(oi_res)}")
            ls = None if isinstance(ls_res, BaseException) else ls_res
            if ls is None:
                gaps.append(f"long_short_ratio unavailable: {_why(ls_res)}")
            derivatives = DerivativesOut(
                funding_rate=funding_res["funding_rate"],
                funding_regime=funding_regime(funding_res["funding_rate"]),  # type: ignore[arg-type]
                mark_price=funding_res["mark_price"],
                open_interest=oi["open_interest"] if oi else None,
                oi_change_24h_pct=oi["oi_change_pct"] if oi else None,
                long_short_ratio=ls,
            )

        sentiment: SentimentOut | None = None
        if isinstance(fng_res, BaseException):
            gaps.append(f"sentiment unavailable: {_why(fng_res)}")
        else:
            sentiment = SentimentOut(fear_greed=fng_res[0], label=fng_res[1])

        gaps.append("volume_profile: not included in brief v1.0")
        gaps.append("liquidation_clusters: not included in brief v1.0")

        return MarketBrief(
            symbol=symbol,
            generated_at=datetime.now(timezone.utc),
            timeframes=timeframes,
            daily_levels=daily_levels,
            derivatives=derivatives,
            sentiment=sentiment,
            alignment=compute_alignment(
                {tf: timeframes[tf] for tf in ALIGNMENT_TIMEFRAMES}
            ),
            gaps=gaps,
        )


def _why(exc: BaseException | object) -> str:
    if isinstance(exc, AdapterError):
        return exc.detail[:120]
    return str(exc)[:120]

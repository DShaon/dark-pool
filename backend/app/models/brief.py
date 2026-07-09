"""Market Brief schema — the single source of facts for the AI layer.

Field paths are a stable, versioned contract: analyst `evidence` references
(e.g. "timeframes.1h.structure.trend", "derivatives.funding_regime") must
resolve into this schema, and the evidence lock rejects citations that don't
(invariant 7 / Fable Rails F4). Rename a field only with a version bump.
Decimal price levels serialize as JSON strings; float analytics as numbers.
"""

from datetime import datetime
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, ConfigDict, field_serializer

BRIEF_VERSION = "1.0"


class _PriceModel(BaseModel):
    """Base for models carrying Decimal price fields (serialized as strings)."""

    model_config = ConfigDict(frozen=True)


class SwingOut(_PriceModel):
    time: datetime
    price: Decimal
    kind: Literal["high", "low"]

    @field_serializer("price")
    def _ser(self, v: Decimal) -> str:
        return format(v, "f")


class StructureEventOut(_PriceModel):
    kind: Literal["BOS", "CHoCH"]
    direction: Literal["bullish", "bearish"]
    level: Decimal
    time: datetime

    @field_serializer("level")
    def _ser(self, v: Decimal) -> str:
        return format(v, "f")


class StructureOut(BaseModel):
    model_config = ConfigDict(frozen=True)
    trend: Literal["bullish", "bearish", "range"]
    last_event: StructureEventOut | None = None


class ZoneOut(_PriceModel):
    kind: Literal["order_block", "fvg"]
    side: Literal["bullish", "bearish"]
    top: Decimal
    bottom: Decimal
    mitigated: bool
    time: datetime

    @field_serializer("top", "bottom")
    def _ser(self, v: Decimal) -> str:
        return format(v, "f")


class LevelOut(_PriceModel):
    kind: Literal["PDH", "PDL", "PWH", "PWL", "EQH", "EQL"]
    price: Decimal
    state: Literal["intact", "swept", "broken"]

    @field_serializer("price")
    def _ser(self, v: Decimal) -> str:
        return format(v, "f")


class IndicatorsOut(BaseModel):
    model_config = ConfigDict(frozen=True)
    ema20: float | None = None
    ema50: float | None = None
    ema200: float | None = None
    rsi14: float | None = None
    macd: float | None = None
    macd_signal: float | None = None
    macd_hist: float | None = None
    atr14: float | None = None
    bb_upper: float | None = None
    bb_mid: float | None = None
    bb_lower: float | None = None
    vwap: float | None = None


class TimeframeAnalysis(_PriceModel):
    tf: str
    last_close: Decimal
    structure: StructureOut
    premium_discount: Literal["premium", "discount", "equilibrium"]
    swings: list[SwingOut]
    order_blocks: list[ZoneOut]
    fvgs: list[ZoneOut]
    equal_levels: list[LevelOut]
    indicators: IndicatorsOut

    @field_serializer("last_close")
    def _ser(self, v: Decimal) -> str:
        return format(v, "f")


class DerivativesOut(BaseModel):
    model_config = ConfigDict(frozen=True)
    funding_rate: float
    funding_regime: Literal[
        "positive_extreme", "positive", "neutral", "negative", "negative_extreme"
    ]
    mark_price: float
    open_interest: float | None = None
    oi_change_24h_pct: float | None = None
    long_short_ratio: float | None = None


class SentimentOut(BaseModel):
    model_config = ConfigDict(frozen=True)
    fear_greed: int
    label: str


class AlignmentOut(BaseModel):
    model_config = ConfigDict(frozen=True)
    score: float  # -1..1, sign = direction
    bias: Literal["long", "short", "mixed"]
    per_tf: dict[str, str]


class MarketBrief(BaseModel):
    model_config = ConfigDict(frozen=True)
    version: str = BRIEF_VERSION
    symbol: str
    generated_at: datetime
    timeframes: dict[str, TimeframeAnalysis]
    daily_levels: list[LevelOut]
    derivatives: DerivativesOut | None = None
    sentiment: SentimentOut | None = None
    alignment: AlignmentOut
    gaps: list[str] = []

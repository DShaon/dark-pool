"""Setup variant contracts (FR-4 variant fan, v1 · ADR-0019).

Six venue/style variants derived DETERMINISTICALLY from the Market Brief —
ATR-rule scaffolds computed in code (no AI, golden-tested), replacing the
frontend's old SAMPLE cards so that saving one to the journal grades REAL
levels. These are engine rule variants, not full analyst plans; the UI labels
them exactly that (provenance registry).

Money fields are Decimal serialized as strings (invariant 3).
"""

from datetime import datetime
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, Field, field_serializer

VariantKey = Literal["scalp", "intraday", "swing", "spot", "grid", "options"]


class VariantTarget(BaseModel):
    price: Decimal
    rr: float  # computed in code: tp_mult / stop_mult

    @field_serializer("price")
    def _ser(self, v: Decimal) -> str:
        return str(v)


class SetupVariant(BaseModel):
    key: VariantKey
    venue: str  # "SPOT" / "PERP" / "MARGIN" / "GRID BOT" / "OPTIONS"
    style: str  # display name, e.g. "3x intraday"
    leverage: int = Field(ge=1, le=10)
    anchor_tf: str  # the timeframe whose ATR sized the levels
    direction: Literal["long", "short", "neutral"]
    tradeable: bool  # False = no valid setup right now (reason says why)
    gradeable: bool  # False = TP/SL candle-walk doesn't apply (grid/options)
    reason: str | None = None  # why untradeable, when it is
    entry_low: Decimal | None = None
    entry_high: Decimal | None = None
    stop: Decimal | None = None
    targets: list[VariantTarget] = Field(default_factory=list, max_length=2)
    edge: str  # one-line English edge description
    edge_bn: str  # Bengali rendering (static per variant)
    # ── ADR-0022: structure-aware provenance (directional variants only;
    #    grid/options keep the defaults — quality None = not applicable) ──
    entry_kind: Literal["structure", "atr_fallback"] = "atr_fallback"
    quality: Literal["high", "medium", "low"] | None = None
    confluence: list[str] = Field(default_factory=list)

    @field_serializer("entry_low", "entry_high", "stop")
    def _ser(self, v: Decimal | None) -> str | None:
        return None if v is None else str(v)


class SetupsResponse(BaseModel):
    symbol: str
    generated_at: datetime
    brief_generated_at: datetime
    bias: Literal["long", "short", "mixed"]
    variants: list[SetupVariant]


__all__ = ["SetupVariant", "SetupsResponse", "VariantTarget", "VariantKey"]

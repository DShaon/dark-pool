"""Alert contracts (P3 · FR-5). An AlertEvent is one notable, deterministically
detected condition on a symbol — surfaced in-app (the Desk Tape). Bilingual
(EN + native Bangla). `tone` maps straight to the tape's semantic colours;
`at` is UTC (the brief's generated_at). No AI here — pure engine facts."""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel

AlertKind = Literal[
    "structure_break",
    "liquidity_sweep",
    "funding_extreme",
    "oi_spike",
    "zone_proximity",
    "sentiment_extreme",
]
Tone = Literal["bull", "bear", "warn", "dim", "pulse"]


class AlertEvent(BaseModel):
    kind: AlertKind
    symbol: str
    timeframe: str | None = None
    tone: Tone
    message: str  # terse English
    message_bn: str  # natural Bangla
    at: datetime
    ref: str | None = None  # a price/level for context, display string


class AlertFeedResponse(BaseModel):
    symbol: str
    generated_at: datetime
    alerts: list[AlertEvent]

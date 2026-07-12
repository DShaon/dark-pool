"""AI scenario path contract (ADR-0017 §2) — sequence opinion, NEVER a forecast.

The model's ONLY freedom is which REAL, already-computed price levels the market
visits and in what order. Each `level_ref` is a dot-path that must resolve to an
existing price inside the resolution context (`brief.*` or `plan.*`); an
unresolvable ref fails validation in code (invariant 7). The server resolves each
ref to its real price and assigns future bar offsets — the model invents no numbers.
"""

from datetime import datetime
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, Field, field_serializer


class Waypoint(BaseModel):
    level_ref: str = Field(min_length=3, max_length=80)
    label: str | None = Field(default=None, max_length=48)
    # Resolved server-side (never sent by the model):
    price: Decimal | None = None
    bar_offset: int | None = None  # bars into the future from the last candle

    @field_serializer("price")
    def _ser(self, v: Decimal | None) -> str | None:
        return None if v is None else str(v)


class ScenarioPath(BaseModel):
    direction: Literal["long", "short", "neutral"]
    waypoints: list[Waypoint] = Field(min_length=2, max_length=6)
    narrative: str = Field(min_length=10, max_length=500)
    narrative_bn: str | None = Field(default=None, max_length=800)
    evidence: list[str] = Field(min_length=1, max_length=12)


class ScenarioResponse(BaseModel):
    """API envelope. Degrades (path=None + reason) — never a 500 (NFR-3)."""

    symbol: str
    generated_at: datetime
    status: Literal["ok", "unavailable"]
    reason: str | None = None
    model_id: str | None = None
    path: ScenarioPath | None = None


__all__ = ["Waypoint", "ScenarioPath", "ScenarioResponse"]

"""Trade outcome grading contracts (P3 · FR-6)."""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel


class GradeResponse(BaseModel):
    symbol: str
    outcome: Literal["tp", "sl", "open"]
    hit_at: datetime | None = None
    candles_checked: int

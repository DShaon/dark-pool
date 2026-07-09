"""Market data schemas.

Contract (CLAUDE.md invariant 3): every price/size is `Decimal`, parsed from the
exchange's string representation — never from float. All timestamps are UTC.
Over JSON, Decimal fields serialize as **strings** (precision is part of the API
contract; the frontend renders them, it does not do float math on them).
"""

from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, field_serializer


class Ticker(BaseModel):
    model_config = ConfigDict(frozen=True)

    symbol: str
    price: Decimal
    ts: datetime  # UTC, when we observed the price

    @field_serializer("price")
    def _serialize_price(self, value: Decimal) -> str:
        return format(value, "f")


class Candle(BaseModel):
    model_config = ConfigDict(frozen=True)

    open_time: datetime  # UTC
    open: Decimal
    high: Decimal
    low: Decimal
    close: Decimal
    volume: Decimal
    close_time: datetime  # UTC

    @field_serializer("open", "high", "low", "close", "volume")
    def _serialize_decimal(self, value: Decimal) -> str:
        return format(value, "f")

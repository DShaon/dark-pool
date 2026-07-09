"""Trade outcome grading route (P3 · FR-6) — deterministic, no AI.

The frontend's journal (localStorage, single-user P1) calls this once per
open trade to check whether price has since reached the target or the stop.
No state is written here — a pure read/compute; the frontend applies the
result to its own stored trade.
"""

from datetime import datetime
from decimal import Decimal
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query, Request

from app.adapters.base import AdapterError
from app.api.routes_market import _validate_symbol, require_auth
from app.models.grading import GradeResponse
from app.quant.grading_service import GradingService

router = APIRouter()


def _service(request: Request) -> GradingService:
    return request.app.state.grading_service


@router.get(
    "/grade/{symbol}", response_model=GradeResponse, dependencies=[Depends(require_auth)]
)
async def grade(
    symbol: str,
    request: Request,
    direction: Literal["long", "short"] = Query(...),
    stop: Decimal = Query(...),
    target: Decimal = Query(...),
    since: datetime = Query(...),
) -> GradeResponse:
    symbol = _validate_symbol(symbol)
    try:
        outcome = await _service(request).grade(symbol, direction, stop, target, since)
    except AdapterError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    return GradeResponse(
        symbol=symbol,
        outcome=outcome.outcome,
        hit_at=datetime.fromisoformat(outcome.hit_at) if outcome.hit_at else None,
        candles_checked=outcome.candles_checked,
    )

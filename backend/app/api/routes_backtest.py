"""Backtest routes (P5 · ADR-0020).

POST /backtest/{symbol}  — start a walk-forward replay (one at a time; 409 if
                           busy). Crypto only: the free forex tier (800 req/day)
                           cannot feed a backtest's history paging.
GET  /backtest/status    — poll the running job (progress 0..1, phase message).
GET  /backtest/{symbol}  — the last stored report for a symbol, 404 if none.
"""

from fastapi import APIRouter, Depends, HTTPException, Query, Request

from app.api.routes_market import _validate_symbol, require_auth
from app.markets import is_forex
from app.models.backtest import BacktestJobStatus, BacktestReport
from app.quant.backtest_service import BacktestBusy, BacktestRunner

router = APIRouter()


def _runner(request: Request) -> BacktestRunner:
    return request.app.state.backtest


@router.post("/backtest/{symbol}", status_code=202, dependencies=[Depends(require_auth)])
async def start_backtest(
    symbol: str, request: Request, days: int | None = Query(default=None, ge=7)
) -> dict:
    symbol = _validate_symbol(symbol)
    runner = _runner(request)
    cfg = runner.config
    if is_forex(symbol):
        raise HTTPException(
            status_code=400,
            detail="backtest is crypto-only in v1 — the free forex data tier "
            "(800 requests/day) cannot supply the history",
        )
    days = days or cfg.window_days_default
    if days > cfg.window_days_max:
        raise HTTPException(
            status_code=400, detail=f"days capped at {cfg.window_days_max}"
        )
    try:
        runner.start(symbol, days)
    except BacktestBusy:
        raise HTTPException(
            status_code=409, detail="a backtest is already running — poll /backtest/status"
        ) from None
    return {"started": True, "symbol": symbol, "days": days}


@router.get(
    "/backtest/status",
    response_model=BacktestJobStatus,
    dependencies=[Depends(require_auth)],
)
async def backtest_status(request: Request) -> BacktestJobStatus:
    return _runner(request).status()


@router.get(
    "/backtest/{symbol}",
    response_model=BacktestReport,
    dependencies=[Depends(require_auth)],
)
async def backtest_report(symbol: str, request: Request) -> BacktestReport:
    symbol = _validate_symbol(symbol)
    report = request.app.state.backtest_store.get(symbol)
    if report is None:
        raise HTTPException(status_code=404, detail=f"no stored backtest for {symbol}")
    return report

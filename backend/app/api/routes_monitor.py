"""Monitoring routes (P3 · FR-5) — mode toggle, watchlist sync, scanner feed.

The background scanner (`app.monitor.scanner.Scanner`) reads the same mode +
watchlist stores this exposes, so flipping Active/Manual here changes what the
very next scheduled tick does — no restart required. The frontend's watchlist
(localStorage, single-user) pushes its list here via POST /monitor/watchlist
whenever it changes, so Active mode can scan symbols even with no tab open.
"""

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel

from app.api.routes_market import require_auth
from app.monitor.state import FeedStore, ModeStore, ScannerMode, WatchlistStore

router = APIRouter()


class ModeBody(BaseModel):
    mode: ScannerMode


class WatchlistBody(BaseModel):
    symbols: list[str]


def _mode_store(request: Request) -> ModeStore:
    return request.app.state.scanner_mode


def _watchlist_store(request: Request) -> WatchlistStore:
    return request.app.state.scanner_watchlist


def _feed_store(request: Request) -> FeedStore:
    return request.app.state.scanner_feed


@router.get("/monitor/mode", dependencies=[Depends(require_auth)])
async def get_mode(request: Request) -> dict:
    return {"mode": _mode_store(request).get()}


@router.post("/monitor/mode", dependencies=[Depends(require_auth)])
async def set_mode(body: ModeBody, request: Request) -> dict:
    return {"mode": _mode_store(request).set(body.mode)}


@router.get("/monitor/watchlist", dependencies=[Depends(require_auth)])
async def get_watchlist(request: Request) -> dict:
    return {"symbols": _watchlist_store(request).get()}


@router.post("/monitor/watchlist", dependencies=[Depends(require_auth)])
async def set_watchlist(body: WatchlistBody, request: Request) -> dict:
    try:
        saved = _watchlist_store(request).set(body.symbols)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return {"symbols": saved}


@router.get("/monitor/feed", dependencies=[Depends(require_auth)])
async def get_feed(
    request: Request, limit: int = Query(default=50, ge=1, le=200)
) -> dict:
    """Recent scanner-detected conditions across the whole watchlist — what
    fired while a symbol wasn't open on the desk. Empty in Manual mode."""
    return {"events": _feed_store(request).recent(limit=limit)}

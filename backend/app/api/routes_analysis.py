"""Analysis routes.

/brief/{symbol}     — the deterministic Market Brief (FR-2)
/quickread/{symbol} — one-model validated read over that brief (FR-3 tier 1)
/desk/{symbol}      — the Full Desk: mandate-analyst panel over that brief (tier 2)
"""

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query, Request

from app.adapters.base import AdapterError
from app.api.routes_market import _cache, _validate_symbol, require_auth
from app.core.llm import LLMError
from app.desk.analysts import AnalystPanel
from app.desk.quick_read import QuickReadError, QuickReadService
from app.models.alerts import AlertFeedResponse
from app.models.analyst import DeskPanelResponse
from app.models.brief import MarketBrief
from app.models.quickread import QuickReadResponse
from app.monitor.alerts import scan_brief
from app.quant.brief import BriefComposer

router = APIRouter()

BRIEF_TTL_SECONDS = 30
QUICKREAD_TTL_SECONDS = 60
DESK_TTL_SECONDS = 120  # Full Desk fans out N model calls — cache longer
ALERTS_TTL_SECONDS = 20  # derived from the brief; refresh roughly with it


def _composer(request: Request) -> BriefComposer:
    return request.app.state.brief_composer


async def _get_brief(symbol: str, request: Request) -> MarketBrief:
    cache = _cache(request)
    key = f"brief:{symbol}"

    cached = await cache.get(key)
    if cached is not None:
        return MarketBrief.model_validate(cached)

    try:
        result = await _composer(request).compose(symbol)
    except AdapterError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc

    await cache.set(key, result.model_dump(mode="json"), BRIEF_TTL_SECONDS)
    return result


@router.get(
    "/brief/{symbol}", response_model=MarketBrief, dependencies=[Depends(require_auth)]
)
async def brief(symbol: str, request: Request) -> MarketBrief:
    return await _get_brief(_validate_symbol(symbol), request)


@router.get(
    "/quickread/{symbol}",
    response_model=QuickReadResponse,
    dependencies=[Depends(require_auth)],
)
async def quickread(
    symbol: str, request: Request, force: bool = Query(default=False)
) -> QuickReadResponse:
    """First AI pass. Degrades to status=degraded — never 500s on model failure."""
    symbol = _validate_symbol(symbol)
    service: QuickReadService | None = request.app.state.quick_read
    if service is None:
        raise HTTPException(
            status_code=503, detail="no LLM provider configured (set a key in .env)"
        )

    cache = _cache(request)
    key = f"quickread:{symbol}"
    if not force:
        cached = await cache.get(key)
        if cached is not None:
            return QuickReadResponse.model_validate(cached)

    market_brief = await _get_brief(symbol, request)
    now = datetime.now(timezone.utc)
    try:
        read = await service.run(market_brief)
        result = QuickReadResponse(
            symbol=symbol,
            generated_at=now,
            brief_generated_at=market_brief.generated_at,
            model_id=service.model_id,
            status="ok",
            read=read,
        )
    except (QuickReadError, LLMError) as exc:
        # Dropped analyst never blocks (invariant 2) — report, don't raise.
        result = QuickReadResponse(
            symbol=symbol,
            generated_at=now,
            brief_generated_at=market_brief.generated_at,
            model_id=service.model_id,
            status="degraded",
            reason=str(exc)[:300],
        )

    await cache.set(key, result.model_dump(mode="json"), QUICKREAD_TTL_SECONDS)
    return result


@router.get(
    "/desk/{symbol}",
    response_model=DeskPanelResponse,
    dependencies=[Depends(require_auth)],
)
async def desk(
    symbol: str, request: Request, force: bool = Query(default=False)
) -> DeskPanelResponse:
    """Full Desk (tier 2): fan the brief out to the mandate analysts in parallel.

    Never 500s on model failure — dropped seats are reported and the run is
    marked degraded when fewer than `min_survivors` analysts survive (§B5).
    The CIO synthesis into one plan + calibrated confidence land with Fable (§F5);
    `tally` here is a display count of what each seat concluded, not a verdict.
    """
    symbol = _validate_symbol(symbol)
    panel: AnalystPanel | None = request.app.state.analyst_panel
    if panel is None:
        raise HTTPException(
            status_code=503, detail="no analyst panel configured (set provider keys in .env)"
        )

    cache = _cache(request)
    key = f"desk:{symbol}"
    if not force:
        cached = await cache.get(key)
        if cached is not None:
            return DeskPanelResponse.model_validate(cached)

    market_brief = await _get_brief(symbol, request)
    now = datetime.now(timezone.utc)

    theses, dropped = await panel.run(market_brief)

    tally = {"long": 0, "short": 0, "no_trade": 0}
    for t in theses:
        tally[t.read.direction] = tally.get(t.read.direction, 0) + 1

    ok = len(theses) >= panel.min_survivors
    reason: str | None = None
    if not ok:
        reason = f"only {len(theses)}/{panel.seat_count} analysts survived"
        if dropped:
            reason += " (dropped: " + ", ".join(d.mandate for d in dropped) + ")"

    result = DeskPanelResponse(
        symbol=symbol,
        generated_at=now,
        brief_generated_at=market_brief.generated_at,
        theses=theses,
        dropped=dropped,
        tally=tally,
        status="ok" if ok else "degraded",
        reason=reason,
    )

    await cache.set(key, result.model_dump(mode="json"), DESK_TTL_SECONDS)
    return result


@router.get(
    "/alerts/{symbol}", response_model=AlertFeedResponse, dependencies=[Depends(require_auth)]
)
async def alerts(symbol: str, request: Request) -> AlertFeedResponse:
    """Deterministic notable conditions on a symbol (FR-5) — no AI. Feeds the
    Desk Tape. The background scanner (Active mode) will diff these over time."""
    symbol = _validate_symbol(symbol)
    cache = _cache(request)
    key = f"alerts:{symbol}"

    cached = await cache.get(key)
    if cached is not None:
        return AlertFeedResponse.model_validate(cached)

    market_brief = await _get_brief(symbol, request)
    events = scan_brief(market_brief, request.app.state.alert_thresholds)
    result = AlertFeedResponse(
        symbol=symbol, generated_at=market_brief.generated_at, alerts=events
    )
    await cache.set(key, result.model_dump(mode="json"), ALERTS_TTL_SECONDS)
    return result

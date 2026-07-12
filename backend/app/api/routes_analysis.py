"""Analysis routes.

/brief/{symbol}     — the deterministic Market Brief (FR-2)
/quickread/{symbol} — one-model validated read over that brief (FR-3 tier 1)
/desk/{symbol}      — the Full Desk: mandate-analyst panel over that brief (tier 2)
/plan/{symbol}      — the CIO's synthesized TradePlan (§B5 · ADR-0015)
/scenario/{symbol}  — AI sequence path over REAL levels (ADR-0017 §2)
/setups/{symbol}    — deterministic ATR-rule setup variants (ADR-0019)
"""

from datetime import datetime, timezone
from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException, Query, Request

from app.adapters.base import AdapterError
from app.api.routes_market import _cache, _validate_symbol, require_auth
from app.config import get_settings
from app.core.llm import LLMError
from app.desk.analysts import AnalystPanel
from app.desk.cio import deterministic_fallback
from app.desk.divergence import detect_divergence
from app.desk.quick_read import QuickReadError, QuickReadService
from app.desk.scenario import ScenarioError, ScenarioService
from app.desk.setups import build_variants
from app.models.alerts import AlertFeedResponse
from app.models.analyst import DeskPanelResponse
from app.models.brief import MarketBrief
from app.models.quickread import QuickReadResponse
from app.models.scenario import ScenarioResponse
from app.models.setups import SetupsResponse
from app.models.tradeplan import TradePlanResponse
from app.markets import is_forex
from app.monitor.alerts import scan_brief
from app.quant.brief import BriefComposer

router = APIRouter()

BRIEF_TTL_SECONDS = 30
# Forex goes through Twelve Data's free tier (8 req/min, 800/day). Composing a
# forex brief costs 5 upstream calls (one per timeframe), so a 30s TTL would
# re-spend 10 calls/min on the brief alone and blow the budget. Cache forex
# briefs far longer — forex is for intermittent analysis on the free tier, not
# 24/7 streaming (see ADR-0014).
FOREX_BRIEF_TTL_SECONDS = 180
QUICKREAD_TTL_SECONDS = 60
DESK_TTL_SECONDS = 120  # Full Desk fans out N model calls — cache longer
PLAN_TTL_SECONDS = 120  # the CIO plan rides the same cadence as the panel
SCENARIO_TTL_SECONDS = 120  # AI sequence path — cache like the plan
ALERTS_TTL_SECONDS = 20  # derived from the brief; refresh roughly with it
MIN_SURVIVORS_FOR_PLAN = 2  # one voice is not a desk (ADR-0015)


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

    ttl = FOREX_BRIEF_TTL_SECONDS if is_forex(symbol) else BRIEF_TTL_SECONDS
    await cache.set(key, result.model_dump(mode="json"), ttl)
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


async def _get_desk(
    symbol: str, request: Request, force: bool
) -> DeskPanelResponse:
    """Shared by /desk and /plan so both draw from the same 120s panel cache."""
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
    `tally` here is a display count of what each seat concluded, not a verdict —
    the verdict is /plan's job.
    """
    return await _get_desk(_validate_symbol(symbol), request, force)


@router.get(
    "/plan/{symbol}",
    response_model=TradePlanResponse,
    dependencies=[Depends(require_auth)],
)
async def plan(
    symbol: str, request: Request, force: bool = Query(default=False)
) -> TradePlanResponse:
    """The desk's final call (§B5 · ADR-0015): panel → divergence detector →
    CIO synthesis (guard-railed) → ONE TradePlan with ADR-0007 calibrated
    confidence and risk-based sizing.

    Needs >= 2 surviving analysts to synthesize (one voice is not a desk);
    otherwise degrades with a reason, never 500s. With no CIO model configured
    the deterministic fallback still produces a plan (NFR-3).
    """
    symbol = _validate_symbol(symbol)
    cache = _cache(request)

    # The panel is never force-re-run from here (that's /desk?force's job —
    # avoids double LLM spend). The plan cache is keyed by the desk run's
    # timestamp, so a fresh desk run automatically invalidates the plan;
    # ?force=true re-synthesizes from the SAME panel (e.g. a flaky synthesis).
    desk_result = await _get_desk(symbol, request, force=False)
    key = f"plan:{symbol}:{desk_result.generated_at.isoformat()}"
    if not force:
        cached = await cache.get(key)
        if cached is not None:
            return TradePlanResponse.model_validate(cached)

    now = datetime.now(timezone.utc)

    if len(desk_result.theses) < MIN_SURVIVORS_FOR_PLAN:
        result = TradePlanResponse(
            symbol=symbol,
            generated_at=now,
            brief_generated_at=desk_result.brief_generated_at,
            status="degraded",
            reason=(
                f"only {len(desk_result.theses)} analyst(s) survived — "
                f"need {MIN_SURVIVORS_FOR_PLAN} to synthesize a plan"
                + (f" ({desk_result.reason})" if desk_result.reason else "")
            ),
            plan=None,
        )
        await cache.set(key, result.model_dump(mode="json"), PLAN_TTL_SECONDS)
        return result

    market_brief = await _get_brief(symbol, request)
    report = detect_divergence(desk_result.theses, market_brief)
    # Recalibration (ADR-0018): learned seat weights + blend refit, read fresh
    # from the outcome store — adjusts CONFIDENCE only, never direction.
    calibration = request.app.state.calibration_store.params()

    # Lessons (ADR-0019): the desk's post-mortem memory rides the synthesis
    # input beside the brief. None when nothing has been learned yet.
    lessons = request.app.state.lessons_store.cio_payload()

    cio = request.app.state.cio
    if cio is not None:
        trade_plan = await cio.synthesize(
            market_brief, desk_result.theses, report, calibration, lessons
        )
    else:
        settings = get_settings()
        trade_plan = deterministic_fallback(
            market_brief,
            desk_result.theses,
            report,
            risk_pct=Decimal(str(settings.risk_pct_per_trade)),
            max_position_pct=Decimal(str(settings.max_position_pct)),
            calibration=calibration,
        )

    reason = None
    if desk_result.status == "degraded":
        reason = f"panel degraded: {desk_result.reason}"
    result = TradePlanResponse(
        symbol=symbol,
        generated_at=now,
        brief_generated_at=desk_result.brief_generated_at,
        status="ok",
        reason=reason,
        plan=trade_plan,
    )
    await cache.set(key, result.model_dump(mode="json"), PLAN_TTL_SECONDS)
    return result


@router.get(
    "/setups/{symbol}",
    response_model=SetupsResponse,
    dependencies=[Depends(require_auth)],
)
async def setups(symbol: str, request: Request) -> SetupsResponse:
    """Deterministic ATR-rule setup variants (FR-4 fan, v1 · ADR-0019) — pure
    code over the cached brief, no AI. Directional variants need a directional
    MTF bias; the grid needs the opposite (chop). These are engine rule
    scaffolds, honestly labeled — not full analyst plans."""
    symbol = _validate_symbol(symbol)
    market_brief = await _get_brief(symbol, request)
    return SetupsResponse(
        symbol=symbol,
        generated_at=datetime.now(timezone.utc),
        brief_generated_at=market_brief.generated_at,
        bias=market_brief.alignment.bias,
        variants=build_variants(market_brief),
    )


@router.get(
    "/scenario/{symbol}",
    response_model=ScenarioResponse,
    dependencies=[Depends(require_auth)],
)
async def scenario(
    symbol: str, request: Request, force: bool = Query(default=False)
) -> ScenarioResponse:
    """AI sequence path (ADR-0017 §2) — the model picks which REAL brief levels
    price visits and in what order; the server resolves each to its actual price
    and future bar offset. No price is invented; degrades to unavailable, never
    500s. Drawn dashed-gold and labelled 'sequence opinion, not a forecast'."""
    symbol = _validate_symbol(symbol)
    service: ScenarioService | None = request.app.state.scenario
    now = datetime.now(timezone.utc)
    if service is None:
        return ScenarioResponse(
            symbol=symbol, generated_at=now, status="unavailable",
            reason="no scenario model configured", model_id=None, path=None,
        )

    cache = _cache(request)
    key = f"scenario:{symbol}"
    if not force:
        cached = await cache.get(key)
        if cached is not None:
            return ScenarioResponse.model_validate(cached)

    market_brief = await _get_brief(symbol, request)
    try:
        path = await service.build(market_brief.model_dump(mode="json"), plan_data=None)
        result = ScenarioResponse(
            symbol=symbol, generated_at=now, status="ok",
            model_id=service.model_id, path=path,
        )
    except ScenarioError as exc:
        result = ScenarioResponse(
            symbol=symbol, generated_at=now, status="unavailable",
            reason=str(exc)[:300], model_id=service.model_id, path=None,
        )
    await cache.set(key, result.model_dump(mode="json"), SCENARIO_TTL_SECONDS)
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

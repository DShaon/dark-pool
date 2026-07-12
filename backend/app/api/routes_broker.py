"""Paper broker routes (P5 · ADR-0021).

THE approval gate lives here and only here: approve/reject/close are
authenticated HTTP actions driven by the web UI. The MCP (AI-facing) surface
can propose and read — it has no approval capability at all (ADR-0021 §1).

POST /broker/propose        — submit a complete order intent (source "ui")
GET  /broker/proposals      — lifecycle list (lazily expires stale ones)
POST /broker/approve/{id}   — the human click: guardrails, then a paper fill
POST /broker/reject/{id}
GET  /broker/positions      — open/closed paper positions, open ones LIVE-
                             priced (mark price + unrealized PnL/R)
POST /broker/close/{id}     — manual market close (slippage priced honestly)
GET  /broker/account        — balance, equity, unrealized (live prices)
POST /broker/reset          — wipe paper state back to the starting balance
POST /broker/deposit        — top up the paper balance (bookkeeping, not
                             risk math — a fat-finger cap only, owner request)
"""

from fastapi import APIRouter, Depends, HTTPException, Query, Request

from app.adapters.base import AdapterError
from app.api.routes_market import require_auth
from app.broker.paper import BrokerStateError, PaperBroker
from app.models.broker import (
    DepositIn,
    OrderProposal,
    PaperAccountView,
    PaperPosition,
    ProposalIn,
)

router = APIRouter(dependencies=[Depends(require_auth)])


def _broker(request: Request) -> PaperBroker:
    return request.app.state.broker


@router.post("/broker/propose", response_model=OrderProposal, status_code=201)
async def propose(intent: ProposalIn, request: Request) -> OrderProposal:
    """Rest a proposal — legacy (needs approval) or a limit that auto-fills on
    touch (ADR-0023). Market orders must use POST /broker/market instead."""
    if intent.order_type == "market":
        raise HTTPException(
            status_code=400, detail="market orders go to POST /broker/market"
        )
    try:
        return _broker(request).propose(intent, source="ui")
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)[:300]) from exc


@router.post("/broker/market")
async def market(intent: ProposalIn, request: Request) -> dict:
    """Manual MARKET order — fills at once at the live price (ADR-0023).
    Returns {approved, reason, proposal, position}."""
    try:
        result = await _broker(request).place_market_order(intent)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)[:300]) from exc
    except BrokerStateError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except AdapterError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    return {
        "approved": result["approved"],
        "reason": result["reason"],
        "proposal": result["proposal"],
        "position": result["position"],
    }


@router.get("/broker/proposals", response_model=list[OrderProposal])
async def proposals(
    request: Request, status: str | None = Query(default=None)
) -> list[OrderProposal]:
    return _broker(request).list_proposals(status)


@router.post("/broker/approve/{proposal_id}")
async def approve(proposal_id: str, request: Request) -> dict:
    try:
        result = await _broker(request).approve(proposal_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except BrokerStateError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except AdapterError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    return {
        "approved": result["approved"],
        "reason": result["reason"],
        "proposal": result["proposal"],
        "position": result["position"],
    }


@router.post("/broker/reject/{proposal_id}", response_model=OrderProposal)
async def reject(proposal_id: str, request: Request) -> OrderProposal:
    try:
        return _broker(request).reject(proposal_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except BrokerStateError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@router.get("/broker/positions", response_model=list[PaperPosition])
async def positions(
    request: Request, status: str | None = Query(default=None)
) -> list[PaperPosition]:
    return await _broker(request).positions_live(status)


@router.post("/broker/close/{position_id}", response_model=PaperPosition)
async def close(position_id: str, request: Request) -> PaperPosition:
    try:
        return await _broker(request).close_position(position_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except BrokerStateError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except AdapterError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc


@router.get("/broker/account", response_model=PaperAccountView)
async def account(request: Request) -> PaperAccountView:
    return await _broker(request).account()


@router.post("/broker/reset")
async def reset(request: Request) -> dict:
    _broker(request).reset()
    return {"ok": True, "note": "paper account reset to the starting balance"}


@router.post("/broker/deposit", response_model=PaperAccountView)
async def deposit(body: DepositIn, request: Request) -> PaperAccountView:
    try:
        _broker(request).deposit(body.amount)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return await _broker(request).account()

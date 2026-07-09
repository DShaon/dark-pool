"""DARKPOOL MCP server (ADR-0006) — the interactive-CIO seam, over stdio.

Exposes the desk's deterministic + AI layers as MCP tools so Claude Code can act
as CIO: read the Market Brief, run the Quick Read or the full analyst panel,
weigh the debate ITSELF, and persist the resulting plan. The CIO synthesis is
the driving model's judgment (Fable per §F5) — this server serves data and
records the decision; it never fabricates a verdict.

    Run (stdio):   python -m app.mcp.server        # from backend/, venv active
    Register CC:   claude mcp add darkpool -- <backend>/.venv/Scripts/python.exe -m app.mcp.server

Tools: desk_health · get_market_brief · quick_read · run_full_desk ·
       save_trade_plan · list_trade_plans.
"""

from __future__ import annotations

import re
from pathlib import Path

from mcp.server.fastmcp import FastMCP

from app.adapters.alternative_me import AlternativeMeAdapter
from app.adapters.base import AdapterError
from app.adapters.binance import BinanceAdapter
from app.adapters.binance_futures import BinanceFuturesAdapter
from app.config import get_settings
from app.core.llm import LLMError
from app.desk.factory import build_desk
from app.desk.plan_store import CioPlan, PlanStore, Target
from app.desk.quick_read import QuickReadError
from app.quant.brief import BriefComposer

_SYMBOL_RE = re.compile(r"^[A-Z0-9]{5,20}$")

# Built once at import — a separate process from the HTTP app, its own clients.
_settings = get_settings()
_spot = BinanceAdapter(base_url=_settings.binance_data_base)
_futures = BinanceFuturesAdapter()
_sentiment = AlternativeMeAdapter()
_composer = BriefComposer(spot=_spot, futures=_futures, sentiment=_sentiment)
_gateway, _quick_read, _panel = build_desk(_settings)
_store = PlanStore(Path(_settings.data_dir) / "trade_plans.json")

mcp = FastMCP("darkpool")


def _sym(symbol: str) -> str:
    s = symbol.strip().upper()
    if not _SYMBOL_RE.match(s):
        raise ValueError(f"invalid symbol {symbol!r} (expected e.g. BTCUSDT)")
    return s


@mcp.tool()
def desk_health() -> dict:
    """What the desk can do right now: which AI tiers are wired + the panel seats."""
    return {
        "quick_read": _quick_read.model_id if _quick_read else None,
        "full_desk_seats": _panel.seat_count if _panel else 0,
        "min_survivors": _panel.min_survivors if _panel else None,
        "market_data": "binance public (keyless)",
        "note": "advisory only; CIO synthesis is the caller's judgment (Fable-tier).",
    }


@mcp.tool()
async def get_market_brief(symbol: str) -> dict:
    """Deterministic Market Brief (structure, zones, liquidity, indicators, derivatives,
    sentiment across 5m/15m/1h/4h/1d). The only facts the desk knows — no AI."""
    try:
        brief = await _composer.compose(_sym(symbol))
        return brief.model_dump(mode="json")
    except (AdapterError, ValueError) as exc:
        return {"error": str(exc)}


@mcp.tool()
async def quick_read(symbol: str) -> dict:
    """Tier-1: one fast, evidence-locked AI read over the brief (degrades, never raises)."""
    if _quick_read is None:
        return {"error": "no LLM provider configured (set a key in backend/.env)"}
    try:
        brief = await _composer.compose(_sym(symbol))
    except (AdapterError, ValueError) as exc:
        return {"error": str(exc)}
    try:
        read = await _quick_read.run(brief)
        return {"status": "ok", "model_id": _quick_read.model_id, "read": read.model_dump(mode="json")}
    except (QuickReadError, LLMError) as exc:
        return {"status": "degraded", "reason": str(exc)[:300]}


@mcp.tool()
async def run_full_desk(symbol: str) -> dict:
    """Tier-2: fan the brief out to the 4 mandate analysts (Trend / Contrarian /
    Derivatives / Risk) and return their evidence-locked theses for YOU to synthesize.
    This is the debate — the single CIO call is yours to make from it, then save it."""
    if _panel is None:
        return {"error": "no analyst panel configured (set provider keys in backend/.env)"}
    try:
        brief = await _composer.compose(_sym(symbol))
    except (AdapterError, ValueError) as exc:
        return {"error": str(exc)}
    theses, dropped = await _panel.run(brief)
    tally = {"long": 0, "short": 0, "no_trade": 0}
    for t in theses:
        tally[t.read.direction] = tally.get(t.read.direction, 0) + 1
    return {
        "status": "ok" if len(theses) >= _panel.min_survivors else "degraded",
        "brief_generated_at": brief.generated_at.isoformat(),
        "tally": tally,
        "theses": [t.model_dump(mode="json") for t in theses],
        "dropped": [d.model_dump(mode="json") for d in dropped],
    }


@mcp.tool()
def save_trade_plan(
    symbol: str,
    direction: str,
    thesis: str,
    conviction: int = 3,
    entry_low: str | None = None,
    entry_high: str | None = None,
    stop: str | None = None,
    targets: list[str] | None = None,
    notes: str | None = None,
) -> dict:
    """Persist the CIO's synthesized plan (P1 file store → Postgres later). `targets`
    are price strings, e.g. ["64500","65200"]. Prices stay strings (precision-safe).
    Returns the saved record with its id. Advisory only — nothing executes."""
    try:
        plan = CioPlan(
            symbol=_sym(symbol),
            direction=direction,  # schema Literal validates long|short|no_trade
            conviction=conviction,
            entry_low=entry_low,
            entry_high=entry_high,
            stop=stop,
            targets=[Target(price=p) for p in (targets or [])],
            thesis=thesis,
            notes=notes,
        )
    except ValueError as exc:  # pydantic ValidationError is a ValueError subclass
        return {"error": str(exc)[:400]}
    return _store.add(plan)


@mcp.tool()
def list_trade_plans(symbol: str | None = None, limit: int = 20) -> list[dict]:
    """Recent CIO plans (newest first), optionally filtered by symbol."""
    return _store.list(symbol.upper() if symbol else None, limit)


def main() -> None:
    mcp.run()  # stdio transport


if __name__ == "__main__":
    main()

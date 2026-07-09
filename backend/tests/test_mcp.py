"""MCP surface tests — the file-backed plan store + tool registration.

The store is exercised directly (no network). The server module is imported to
assert every CIO tool is registered; its network/LLM tools are covered by the
brief/quick-read/panel tests they reuse.
"""

import json

import pytest

from app.desk.plan_store import CioPlan, PlanStore, Target


def make_plan(**kw) -> CioPlan:
    base = dict(
        symbol="BTCUSDT",
        direction="long",
        conviction=4,
        thesis="Bullish structure on the hour; buy the pullback into 4H demand and hold.",
        targets=[Target(price="64500", rr=1.8)],
    )
    base.update(kw)
    return CioPlan(**base)


def test_add_and_list_roundtrip(tmp_path):
    store = PlanStore(tmp_path / "plans.json")
    assert store.list() == []

    rec = store.add(make_plan())
    assert rec["id"].startswith("plan_")
    assert rec["symbol"] == "BTCUSDT"
    assert "saved_at" in rec

    got = store.list()
    assert len(got) == 1 and got[0]["id"] == rec["id"]
    # persisted to disk (atomic write)
    on_disk = json.loads((tmp_path / "plans.json").read_text(encoding="utf-8"))
    assert on_disk[0]["thesis"].startswith("Bullish")


def test_newest_first_symbol_filter_and_limit(tmp_path):
    store = PlanStore(tmp_path / "plans.json")
    store.add(make_plan(symbol="BTCUSDT"))
    store.add(make_plan(symbol="ETHUSDT", direction="short"))
    store.add(make_plan(symbol="BTCUSDT", direction="no_trade", conviction=2, targets=[]))

    all_plans = store.list()
    assert all_plans[0]["symbol"] == "BTCUSDT"  # newest first (last added)
    assert all_plans[0]["direction"] == "no_trade"
    assert len(store.list(symbol="btcusdt")) == 2  # case-insensitive filter
    assert len(store.list(limit=1)) == 1


def test_no_trade_plan_needs_no_levels(tmp_path):
    store = PlanStore(tmp_path / "plans.json")
    rec = store.add(
        CioPlan(
            symbol="BTCUSDT",
            direction="no_trade",
            conviction=1,
            thesis="Stand aside — mixed timeframes and overhead liquidity both ways.",
        )
    )
    assert rec["direction"] == "no_trade" and rec["targets"] == []


def test_bad_direction_rejected():
    with pytest.raises(ValueError):
        CioPlan(symbol="BTCUSDT", direction="sideways", conviction=3, thesis="x" * 20)


def test_short_thesis_rejected():
    with pytest.raises(ValueError):
        CioPlan(symbol="BTCUSDT", direction="long", conviction=3, thesis="too short")


async def test_mcp_exposes_the_cio_tools():
    from app.mcp import server as srv

    try:
        tools = await srv.mcp.list_tools()
        names = {t.name for t in tools}
        assert {
            "desk_health",
            "get_market_brief",
            "quick_read",
            "run_full_desk",
            "save_trade_plan",
            "list_trade_plans",
        } <= names
    finally:
        # importing the module built real adapters/gateway — close them cleanly
        for client in (srv._spot, srv._futures, srv._sentiment):
            await client.aclose()
        if srv._gateway is not None:
            await srv._gateway.aclose()

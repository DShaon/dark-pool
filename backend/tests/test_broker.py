"""Paper broker tests (P5 · ADR-0021) — golden fixtures + the gate itself.

Every expected number is HAND-COMPUTED in a comment. The guardrails
(beyond-stop, entry tolerance, no stacking), the cost charging, and — above
all — the STRUCTURAL gate (no approve capability on the MCP surface) are the
contract: if a change breaks one, that is a money-risk change and needs a new
ADR, not a test edit.

Clean-arithmetic config used in most tests: fee 10 bps, slippage 0 —
balance 10000 · live 100 · stop 98 · risk 1% ⇒ stop distance 2% ⇒
position 50% ⇒ notional 5000 ⇒ qty 50 ⇒ entry fee 5.
"""

from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient

from app.adapters.base import AdapterError
from app.broker.paper import (
    BrokerConfig,
    BrokerStateError,
    PaperBroker,
    load_broker_config,
)
from app.main import create_app
from app.models.broker import ProposalIn
from app.models.market import Ticker
from app.quant.grading import GradeOutcome


class FakeSpot:
    def __init__(self, price: str = "100"):
        self.price = Decimal(price)
        self.fail = False

    async def get_ticker(self, symbol: str) -> Ticker:
        if self.fail:
            raise AdapterError("binance", "down")
        return Ticker(symbol=symbol, price=self.price, ts=datetime.now(timezone.utc))


class FakeGrading:
    def __init__(self):
        self.outcome = "open"
        self.fail = False

    async def grade(self, symbol, direction, stop, target, since) -> GradeOutcome:
        if self.fail:
            raise AdapterError("binance", "down")
        return GradeOutcome(self.outcome, None, 1)


CLEAN = BrokerConfig(
    starting_balance=Decimal("10000"),
    fee_bps_per_side=10.0,
    slippage_bps_per_side=0.0,
    entry_tolerance_pct=Decimal("0.5"),
    proposal_ttl_hours=6,
)


def make_broker(tmp_path, config=CLEAN, price="100"):
    spot, grading = FakeSpot(price), FakeGrading()
    broker = PaperBroker(
        path=tmp_path / "paper.json",
        config=config,
        spot=spot,  # type: ignore[arg-type]
        grading=grading,  # type: ignore[arg-type]
        risk_pct_default=Decimal("1.0"),
        max_position_pct=Decimal("100.0"),
    )
    return broker, spot, grading


def long_intent(**over) -> ProposalIn:
    base = dict(
        symbol="BTCUSDT", direction="long",
        entry_low=Decimal("99"), entry_high=Decimal("100.5"),
        stop=Decimal("98"), targets=[Decimal("103")],
        thesis="test long",
    )
    base.update(over)
    return ProposalIn(**base)


def perp_intent(**over) -> ProposalIn:
    """A manual MARKET perp order at ~100 (fills at the FakeSpot live price)."""
    base = dict(
        symbol="BTCUSDT", direction="long",
        entry_low=Decimal("100"), entry_high=Decimal("100"),
        stop=Decimal("98"), targets=[Decimal("103")],
        thesis="perp test", order_type="market", market_type="perp", leverage=5,
    )
    base.update(over)
    return ProposalIn(**base)


def limit_intent(**over) -> ProposalIn:
    """A resting LIMIT order at 100 (auto-fills on touch when source=ui)."""
    base = dict(
        symbol="BTCUSDT", direction="long",
        entry_low=Decimal("100"), entry_high=Decimal("100"),
        stop=Decimal("98"), targets=[Decimal("103")],
        thesis="limit test", order_type="limit", market_type="spot", leverage=1,
    )
    base.update(over)
    return ProposalIn(**base)


# ── config pins (the yaml values ARE money-risk constants) ─────────────────


def test_config_yaml_pinned():
    cfg = load_broker_config("config/broker.yaml")
    assert cfg.starting_balance == Decimal("10000")
    assert cfg.fee_bps_per_side == 10.0
    assert cfg.slippage_bps_per_side == 2.0
    assert cfg.entry_tolerance_pct == Decimal("0.5")
    assert cfg.proposal_ttl_hours == 6
    assert cfg.max_open_per_symbol == 1
    assert cfg.monitor_interval_seconds == 60
    assert cfg.max_deposit_per_request == Decimal("1000000")
    assert cfg.max_leverage == 20  # ADR-0023


# ── proposal schema: an approver must see a coherent order ─────────────────


def test_geometry_validation():
    with pytest.raises(ValueError, match="stop must sit below"):
        long_intent(stop=Decimal("99.5"))
    with pytest.raises(ValueError, match="target must sit above"):
        long_intent(targets=[Decimal("100")])
    with pytest.raises(ValueError, match="risk_pct"):
        long_intent(risk_pct=Decimal("6"))
    with pytest.raises(ValueError, match="stop must sit above"):
        ProposalIn(
            symbol="BTCUSDT", direction="short",
            entry_low=Decimal("100"), entry_high=Decimal("100.5"),
            stop=Decimal("100.2"), targets=[Decimal("97")], thesis="bad short",
        )


def test_propose_forex_refused(tmp_path):
    broker, _, _ = make_broker(tmp_path)
    with pytest.raises(ValueError, match="crypto-only"):
        broker.propose(long_intent(symbol="EURUSD"), source="mcp")


def test_propose_records_and_expires(tmp_path):
    broker, _, _ = make_broker(tmp_path)
    p = broker.propose(long_intent(), source="mcp")
    assert p.status == "pending" and p.source == "mcp"
    assert p.expires_at - p.created_at == timedelta(hours=6)
    assert p.audit[0].action == "proposed"
    # Force the TTL to lapse, then any read flips it to expired.
    state = broker._load()
    state.proposals[0].expires_at = datetime.now(timezone.utc) - timedelta(minutes=1)
    broker._save(state)
    listed = broker.list_proposals()
    assert listed[0].status == "expired"
    assert listed[0].audit[-1].actor == "system"


# ── the fill: golden money math ────────────────────────────────────────────


@pytest.mark.asyncio
async def test_approve_fill_golden(tmp_path):
    broker, _, _ = make_broker(tmp_path)
    p = broker.propose(long_intent(), source="mcp")
    result = await broker.approve(p.id)
    assert result["approved"] is True
    pos = result["position"]
    # live 100, slip 0 -> eff 100; stop dist (100-98)/100 = 2% -> position 50%
    # notional 5000, qty 50, entry fee 5000 x 0.001 = 5 -> balance 9995
    assert pos.entry_price == Decimal("100")
    assert pos.qty == Decimal("50")
    assert pos.notional_entry == Decimal("5000")
    assert pos.fees_paid == Decimal("5")
    assert pos.position_pct == Decimal("50.0")
    assert broker._load().balance == Decimal("9995")
    assert result["proposal"].status == "filled"
    assert result["proposal"].position_id == pos.id
    assert any(e.action == "filled" for e in pos.audit)


@pytest.mark.asyncio
async def test_slippage_applied_against_trader(tmp_path):
    cfg = CLEAN.model_copy(update={"slippage_bps_per_side": 2.0})
    broker, _, _ = make_broker(tmp_path, config=cfg)
    p = broker.propose(long_intent(), source="ui")
    result = await broker.approve(p.id)
    # long fill: 100 x (1 + 0.0002) = 100.02, exactly
    assert result["position"].entry_price == Decimal("100.02")


@pytest.mark.asyncio
async def test_approve_refused_outside_tolerance_stays_pending(tmp_path):
    broker, spot, _ = make_broker(tmp_path, price="105")
    p = broker.propose(long_intent(), source="mcp")
    result = await broker.approve(p.id)
    # zone 99–100.5 ±0.5% -> [98.505, 101.0025]; live 105 is outside
    assert result["approved"] is False and "outside the entry zone" in result["reason"]
    assert result["proposal"].status == "pending"  # price may come back
    spot.price = Decimal("100")  # ...and it did
    result2 = await broker.approve(p.id)
    assert result2["approved"] is True


@pytest.mark.asyncio
async def test_approve_refused_beyond_stop_kills_proposal(tmp_path):
    broker, _, _ = make_broker(tmp_path, price="97")  # below the 98 stop
    p = broker.propose(long_intent(), source="mcp")
    result = await broker.approve(p.id)
    assert result["approved"] is False and "the plan is dead" in result["reason"]
    assert result["proposal"].status == "expired"  # dead plans don't linger approvable
    with pytest.raises(BrokerStateError):
        await broker.approve(p.id)


@pytest.mark.asyncio
async def test_no_stacking_per_symbol(tmp_path):
    broker, _, _ = make_broker(tmp_path)
    first = broker.propose(long_intent(), source="mcp")
    assert (await broker.approve(first.id))["approved"] is True
    second = broker.propose(long_intent(), source="mcp")
    result = await broker.approve(second.id)
    assert result["approved"] is False and "not stacking" in result["reason"]
    assert result["proposal"].status == "pending"


def test_reject_and_wrong_states(tmp_path):
    broker, _, _ = make_broker(tmp_path)
    p = broker.propose(long_intent(), source="ui")
    rejected = broker.reject(p.id)
    assert rejected.status == "rejected"
    with pytest.raises(BrokerStateError):
        broker.reject(p.id)
    with pytest.raises(KeyError):
        broker.reject("nope")


# ── deterministic closes: golden money math ────────────────────────────────


@pytest.mark.asyncio
async def test_monitor_closes_tp_golden(tmp_path):
    broker, _, grading = make_broker(tmp_path)
    p = broker.propose(long_intent(), source="mcp")
    await broker.approve(p.id)
    grading.outcome = "tp"
    assert await broker.monitor_tick() == 1
    pos = broker.positions("closed")[0]
    # exit AT target 103: gross = 3 x 50 = 150; exit fee = 5150 x 0.001 = 5.15
    # realized = 150 - 5 - 5.15 = 139.85; risk = 2 x 50 = 100 -> 1.3985R
    # balance = 9995 + 150 - 5.15 = 10139.85
    assert pos.exit_reason == "tp" and pos.exit_price == Decimal("103")
    assert pos.realized_pnl == Decimal("139.85")
    assert pos.realized_r == 1.3985
    assert pos.fees_paid == Decimal("10.15")
    assert broker._load().balance == Decimal("10139.85")


@pytest.mark.asyncio
async def test_monitor_closes_sl_golden(tmp_path):
    broker, _, grading = make_broker(tmp_path)
    p = broker.propose(long_intent(), source="mcp")
    await broker.approve(p.id)
    grading.outcome = "sl"
    assert await broker.monitor_tick() == 1
    pos = broker.positions("closed")[0]
    # exit AT stop 98: gross = -2 x 50 = -100; exit fee = 4900 x 0.001 = 4.90
    # realized = -100 - 5 - 4.90 = -109.90 -> -1.099R
    # balance = 9995 - 100 - 4.90 = 9890.10
    assert pos.exit_reason == "sl"
    assert pos.realized_pnl == Decimal("-109.90")
    assert pos.realized_r == -1.099
    assert broker._load().balance == Decimal("9890.10")


@pytest.mark.asyncio
async def test_monitor_skips_failing_symbol_and_open_outcome(tmp_path):
    broker, _, grading = make_broker(tmp_path)
    p = broker.propose(long_intent(), source="mcp")
    await broker.approve(p.id)
    assert await broker.monitor_tick() == 0  # outcome "open" -> untouched
    grading.fail = True
    assert await broker.monitor_tick() == 0  # adapter down -> skipped, not crashed
    assert broker.positions("open")


@pytest.mark.asyncio
async def test_manual_close_slippage_against_trader(tmp_path):
    cfg = CLEAN.model_copy(update={"slippage_bps_per_side": 2.0})
    broker, spot, _ = make_broker(tmp_path, config=cfg)
    p = broker.propose(long_intent(), source="ui")
    await broker.approve(p.id)
    spot.price = Decimal("102")
    pos = await broker.close_position(broker.positions("open")[0].id)
    # long exit is a sell: 102 x (1 - 0.0002) = 101.9796, exactly
    assert pos.exit_price == Decimal("101.9796")
    assert pos.exit_reason == "manual"
    with pytest.raises(BrokerStateError):
        await broker.close_position(pos.id)


# ── account view + reset ───────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_account_view_and_pricing_gap(tmp_path):
    broker, spot, _ = make_broker(tmp_path)
    p = broker.propose(long_intent(), source="mcp")
    await broker.approve(p.id)
    spot.price = Decimal("101")
    view = await broker.account()
    # unrealized = (101 - 100) x 50 = 50; equity = 9995 + 50 = 10045
    assert view.balance == Decimal("9995")
    assert view.unrealized_pnl == Decimal("50")
    assert view.equity == Decimal("10045")
    assert view.n_open == 1 and view.n_pending == 0
    spot.fail = True
    gap_view = await broker.account()
    assert gap_view.pricing_gaps == ["BTCUSDT"]
    assert gap_view.equity == gap_view.balance  # unpriceable -> not guessed


@pytest.mark.asyncio
async def test_reset(tmp_path):
    broker, _, _ = make_broker(tmp_path)
    p = broker.propose(long_intent(), source="ui")
    await broker.approve(p.id)
    broker.reset()
    assert broker._load().balance == Decimal("10000")
    assert broker.list_proposals() == [] and broker.positions() == []


# ── live per-position PnL (owner request, 2026-07-12) ──────────────────────


@pytest.mark.asyncio
async def test_positions_live_enriches_open_only_golden(tmp_path):
    broker, spot, _ = make_broker(tmp_path)
    p = broker.propose(long_intent(), source="ui")
    await broker.approve(p.id)  # entry 100, qty 50, stop 98 -> risk 100
    spot.price = Decimal("101")
    live = await broker.positions_live("open")
    pos = live[0]
    # unrealized = (101 - 100) x 50 = 50; risk = (100-98) x 50 = 100 -> r 0.50
    assert pos.mark_price == Decimal("101")
    assert pos.unrealized_pnl == Decimal("50")
    assert pos.unrealized_r == 0.5
    # closed positions carry realized_* instead, never live fields
    await broker.close_position(pos.id)
    closed = await broker.positions_live("closed")
    assert closed[0].mark_price is None and closed[0].unrealized_pnl is None
    assert closed[0].realized_pnl is not None


@pytest.mark.asyncio
async def test_positions_live_pricing_gap_leaves_fields_none(tmp_path):
    broker, spot, _ = make_broker(tmp_path)
    p = broker.propose(long_intent(), source="ui")
    await broker.approve(p.id)
    spot.fail = True
    live = await broker.positions_live("open")
    assert live[0].mark_price is None  # never a guessed number
    assert live[0].unrealized_pnl is None and live[0].unrealized_r is None


@pytest.mark.asyncio
async def test_positions_live_matches_account_aggregate(tmp_path):
    """The two views share ONE formula (_unrealized) — this proves they can't
    silently drift: summing per-position unrealized must equal the account's
    aggregate, at any price."""
    broker, spot, _ = make_broker(tmp_path)
    p = broker.propose(long_intent(), source="ui")
    await broker.approve(p.id)
    spot.price = Decimal("97.30")  # a price with no round-number coincidence
    live = await broker.positions_live("open")
    total = sum((x.unrealized_pnl for x in live), Decimal(0))
    view = await broker.account()
    assert total == view.unrealized_pnl


# ── deposit (bookkeeping, not risk math — owner request, 2026-07-12) ───────


def test_deposit_golden(tmp_path):
    broker, _, _ = make_broker(tmp_path)
    new_balance = broker.deposit(Decimal("5000"))
    assert new_balance == Decimal("15000")
    assert broker._load().balance == Decimal("15000")
    # a second deposit stacks
    assert broker.deposit(Decimal("250.50")) == Decimal("15250.50")


def test_deposit_rejects_non_positive(tmp_path):
    broker, _, _ = make_broker(tmp_path)
    with pytest.raises(ValueError, match="must be positive"):
        broker.deposit(Decimal("0"))
    with pytest.raises(ValueError, match="must be positive"):
        broker.deposit(Decimal("-100"))
    assert broker._load().balance == Decimal("10000")  # untouched


def test_deposit_rejects_over_cap(tmp_path):
    cfg = CLEAN.model_copy(update={"max_deposit_per_request": Decimal("1000")})
    broker, _, _ = make_broker(tmp_path, config=cfg)
    with pytest.raises(ValueError, match="capped at 1000"):
        broker.deposit(Decimal("1000.01"))
    assert broker.deposit(Decimal("1000")) == Decimal("11000")  # exactly at the cap is fine


# ── ADR-0023: order types, leverage/margin, resting-limit auto-fill ────────


def test_spot_rejects_leverage():
    with pytest.raises(ValueError, match="spot orders are always 1x"):
        perp_intent(market_type="spot", leverage=5)


@pytest.mark.asyncio
async def test_market_order_leverage_golden(tmp_path):
    broker, spot, _ = make_broker(tmp_path)  # price 100, fee 10bps, slip 0
    res = await broker.place_market_order(perp_intent())  # 5x perp long
    assert res["approved"] is True
    pos = res["position"]
    # live 100, slip 0 -> entry 100; stop 98 -> dist 2% -> position 50%
    # notional 5000, qty 50, margin = notional/5 = 1000, fee 5
    assert pos.entry_price == Decimal("100")
    assert pos.qty == Decimal("50")
    assert pos.notional_entry == Decimal("5000")
    assert pos.leverage == 5 and pos.market_type == "perp"
    assert pos.margin_used == Decimal("1000")
    assert broker._load().balance == Decimal("9995")


@pytest.mark.asyncio
async def test_leverage_raises_cap_but_not_qty_or_risk(tmp_path):
    """Same risk% + stop -> SAME qty at any leverage (loss-at-stop is
    leverage-independent); only the margin locked differs. This is why the
    'no liquidation' scope is safe (ADR-0023 §3)."""
    broker, _, _ = make_broker(tmp_path)
    r5 = await broker.place_market_order(perp_intent(leverage=5))
    qty5, margin5 = r5["position"].qty, r5["position"].margin_used
    broker.reset()
    r1 = await broker.place_market_order(perp_intent(leverage=1, market_type="perp"))
    qty1, margin1 = r1["position"].qty, r1["position"].margin_used
    assert qty5 == qty1 == Decimal("50")           # leverage never changes size
    assert margin1 == Decimal("5000")              # 1x locks the full notional
    assert margin5 == Decimal("1000")              # 5x locks a fifth


@pytest.mark.asyncio
async def test_leverage_lets_tight_stop_exceed_1x_cap(tmp_path):
    """risk 1% / stop 0.5% wants 200% notional. At 1x it's capped to 100%; at
    3x the cap (300%) lets the full 200% through — margin still <= balance."""
    broker, _, _ = make_broker(tmp_path)
    capped = await broker.place_market_order(
        perp_intent(stop=Decimal("99.5"), leverage=1, market_type="perp")
    )
    assert capped["position"].position_pct == Decimal("100.00")
    assert capped["position"].notional_entry == Decimal("10000")
    broker.reset()
    freed = await broker.place_market_order(perp_intent(stop=Decimal("99.5"), leverage=3))
    assert freed["position"].position_pct == Decimal("200.00")
    assert freed["position"].notional_entry == Decimal("20000")
    assert freed["position"].margin_used == Decimal("6666.66666667")  # 20000/3, <= balance


@pytest.mark.asyncio
async def test_market_refused_when_live_beyond_stop(tmp_path):
    broker, _, _ = make_broker(tmp_path, price="97")  # below the 98 stop
    res = await broker.place_market_order(perp_intent(leverage=1, market_type="perp"))
    assert res["approved"] is False and "dead trade" in res["reason"]
    assert not broker.positions("open")


@pytest.mark.asyncio
async def test_limit_auto_fills_on_touch_long(tmp_path):
    broker, spot, _ = make_broker(tmp_path, price="101")  # above the 100 limit
    broker.propose(limit_intent(), source="ui")
    assert await broker.monitor_tick() == 0        # 101 > 100 — not touched
    assert not broker.positions("open")
    spot.price = Decimal("100")                     # price falls to the limit
    assert await broker.monitor_tick() == 1        # auto-filled
    pos = broker.positions("open")[0]
    assert pos.entry_price == Decimal("100")        # filled AT the limit, no slippage
    assert broker.list_proposals("filled")


@pytest.mark.asyncio
async def test_limit_auto_fills_on_touch_short(tmp_path):
    broker, spot, _ = make_broker(tmp_path, price="99")  # below the 100 limit
    broker.propose(
        limit_intent(direction="short", stop=Decimal("102"), targets=[Decimal("97")]),
        source="ui",
    )
    assert await broker.monitor_tick() == 0        # 99 < 100 — not touched
    spot.price = Decimal("100")
    assert await broker.monitor_tick() == 1
    assert broker.positions("open")[0].entry_price == Decimal("100")


@pytest.mark.asyncio
async def test_ai_proposed_limit_never_auto_fills(tmp_path):
    """THE gate (ADR-0021 §1 preserved by ADR-0023 §2): an AI-placed limit,
    even sitting exactly at a touched price, NEVER auto-fills — only the human
    approval click can fill it."""
    broker, spot, _ = make_broker(tmp_path, price="100")  # exactly at the limit
    broker.propose(limit_intent(), source="mcp")           # AI-placed
    assert await broker.monitor_tick() == 0                # source=mcp -> no auto-fill
    assert not broker.positions("open")
    assert broker.list_proposals("pending")                # still awaiting a human


@pytest.mark.asyncio
async def test_limit_expires_if_tick_finds_price_through_stop(tmp_path):
    """Discrete-tick monitoring: if a tick observes price already past the
    stop, the resting order expires rather than fill into a dead plan."""
    broker, spot, _ = make_broker(tmp_path, price="101")
    broker.propose(limit_intent(), source="ui")            # long limit 100, stop 98
    spot.price = Decimal("97")                              # gapped through the stop
    assert await broker.monitor_tick() == 1                # a change: expiry
    assert not broker.positions("open")
    assert broker.list_proposals("expired")


# ── routes: the gate's home ────────────────────────────────────────────────


def test_broker_routes_flow(tmp_path):
    app = create_app()
    with TestClient(app) as client:
        broker, spot, grading = make_broker(tmp_path)
        app.state.broker = broker

        body = {
            "symbol": "BTCUSDT", "direction": "long",
            "entry_low": "99", "entry_high": "100.5",
            "stop": "98", "targets": ["103"], "thesis": "route test",
        }
        r = client.post("/broker/propose", json=body)
        assert r.status_code == 201
        pid = r.json()["id"]

        assert client.post("/broker/propose", json={**body, "symbol": "EURUSD"}).status_code == 400
        assert client.post("/broker/propose", json={**body, "stop": "101"}).status_code == 422

        assert len(client.get("/broker/proposals?status=pending").json()) == 1

        r = client.post(f"/broker/approve/{pid}")
        assert r.status_code == 200 and r.json()["approved"] is True
        pos_id = r.json()["position"]["id"]
        assert client.post(f"/broker/approve/{pid}").status_code == 409  # already filled
        assert client.post("/broker/approve/nope").status_code == 404

        open_pos = client.get("/broker/positions?status=open").json()[0]
        assert open_pos["id"] == pos_id
        # live enrichment on the route (spot fixture price 100 = entry -> 0R flat)
        assert open_pos["mark_price"] == "100"
        assert open_pos["unrealized_pnl"] == "0.00000000"
        acct = client.get("/broker/account").json()
        assert acct["balance"] == "9995.00"

        assert client.post(f"/broker/close/{pos_id}").status_code == 200
        assert client.post(f"/broker/close/{pos_id}").status_code == 409
        # closed positions never carry the live fields
        closed_pos = client.get("/broker/positions?status=closed").json()[0]
        assert closed_pos["mark_price"] is None

        # balance after entry fee (9995) and the manual close's exit fee (-5) = 9990
        dep = client.post("/broker/deposit", json={"amount": "500"})
        assert dep.status_code == 200 and dep.json()["balance"] == "10490.00"
        # amount<=0 fails DepositIn's own validator -> 422, same as ProposalIn's
        # geometry check above; 400 is reserved for the cap check in the route.
        assert client.post("/broker/deposit", json={"amount": "0"}).status_code == 422

        assert client.post("/broker/reset").json()["ok"] is True
        assert client.get("/broker/account").json()["balance"] == "10000.00"


# ── THE GATE (ADR-0021 §1) — the most important test in this file ──────────


def test_mcp_surface_has_no_approval_capability():
    """An AI drives the MCP server. If approve/close/reset ever appear there,
    the approval gate is theater. This test failing means a live-money design
    rule was broken — fix the surface, never this test."""
    import app.mcp.server as srv

    tools = {t.name for t in srv.mcp._tool_manager.list_tools()}
    assert "propose_order" in tools
    assert "list_proposals" in tools
    assert "get_paper_account" in tools
    forbidden = [t for t in tools if any(w in t for w in ("approve", "reject", "close", "reset", "fill"))]
    assert not forbidden, f"gate violation — approval-adjacent tools on the AI surface: {forbidden}"

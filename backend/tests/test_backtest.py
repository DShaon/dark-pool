"""Backtest engine tests (P5 · ADR-0020) — golden fixtures.

Every expected number is HAND-COMPUTED in a comment. The conservative rules
(worse-edge fill, fill-bar no-TP, both-touch = stop) and the cost constants
ARE the simulation contract: if a change breaks one, that is a money-risk
change and needs a new ADR, not a test edit.

Cost model used throughout: PERP per-side = (5 + 2) bps = 0.0007.
"""

from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient

from app.desk.setups import build_variants
from app.main import create_app
from app.models.backtest import BacktestAssumptions, BacktestReport, BacktestTrade
from app.models.brief import MarketBrief
from app.models.market import Candle
from app.models.setups import SetupVariant, VariantTarget
from app.quant.backtest import (
    GRADEABLE_KEYS,
    MonteCarloConfig,
    WARMUP_BARS,
    BacktestConfig,
    _monte_carlo,
    _VariantSim,
    _variant_result,
    _visible,
    run_backtest,
)
from app.quant.backtest_service import (
    _MAX_STORED_SYMBOLS,
    BacktestBusy,
    BacktestStore,
)
from app.quant.brief import ALIGNMENT_TIMEFRAMES, analyze_timeframe, compute_alignment

T0 = datetime(2026, 1, 1, tzinfo=timezone.utc)
_15M = timedelta(minutes=15)

PERP_FRAC = Decimal("0.0007")  # (5 fee + 2 slip) bps per side


def _frac(_venue: str) -> Decimal:
    return PERP_FRAC


def bar(i: int, o: str, h: str, l: str, c: str, start: datetime = T0) -> Candle:
    t = start + i * _15M
    return Candle(
        open_time=t, open=Decimal(o), high=Decimal(h), low=Decimal(l),
        close=Decimal(c), volume=Decimal(1), close_time=t + _15M,
    )


def intraday_long() -> SetupVariant:
    """The ADR-0019 golden intraday variant: close=100, ATR(1h)=2 →
    entry 99.50–100.00, stop 97.75, tp1 102.75."""
    return SetupVariant(
        key="intraday", venue="PERP", style="3x intraday", leverage=3,
        anchor_tf="1h", direction="long", tradeable=True, gradeable=True,
        entry_low=Decimal("99.50"), entry_high=Decimal("100.00"),
        stop=Decimal("97.75"),
        targets=[VariantTarget(price=Decimal("102.75"), rr=1.5),
                 VariantTarget(price=Decimal("104.75"), rr=2.5)],
        edge="", edge_bn="",
    )


def intraday_short() -> SetupVariant:
    """Mirrored short: close=100, ATR=2 → entry 100.00–100.50, stop 102.25,
    tp1 97.25."""
    return SetupVariant(
        key="intraday", venue="PERP", style="3x intraday", leverage=3,
        anchor_tf="1h", direction="short", tradeable=True, gradeable=True,
        entry_low=Decimal("100.00"), entry_high=Decimal("100.50"),
        stop=Decimal("102.25"),
        targets=[VariantTarget(price=Decimal("97.25"), rr=1.5)],
        edge="", edge_bn="",
    )


# ── the order/position state machine ───────────────────────────────────────


def test_fill_at_worse_edge_then_tp_golden_net_r():
    sim = _VariantSim(key="intraday", per_side_frac=_frac)
    sim.on_decision(intraday_long(), T0)
    assert sim.pending is not None and sim.pending.limit == Decimal("100.00")

    sim.on_bar(bar(0, "101", "101.5", "100.5", "101"), 0)   # never dips to 100 — no fill
    assert sim.position is None
    sim.on_bar(bar(1, "100.5", "100.6", "99.80", "100"), 1)  # low 99.80 ≤ 100 → fill AT 100
    assert sim.position is not None and sim.position.entry == Decimal("100.00")
    sim.on_bar(bar(2, "100", "103.0", "99.90", "102.8"), 2)  # high ≥ 102.75 → tp

    assert len(sim.trades) == 1
    t = sim.trades[0]
    # risk = 100 − 97.75 = 2.25 (filled at the WORSE edge, so realized R < the
    # published 1.5 which measures from the band mid — by design)
    # gross = 2.75 / 2.25 = 1.2222
    # cost  = (100 + 102.75) × 0.0007 / 2.25 = 0.141925 / 2.25 = 0.0631
    # net   = 1.2222222 − 0.0630778 = 1.1591444 → 1.1591
    assert t.outcome == "tp"
    assert t.exit_price == Decimal("102.75")
    assert t.gross_r == 1.2222
    assert t.cost_r == 0.0631
    assert t.net_r == 1.1591
    assert t.bars_held == 2  # filled on bar 1, exited on bar 2 — inclusive


def test_fill_bar_may_stop_out_golden():
    sim = _VariantSim(key="intraday", per_side_frac=_frac)
    sim.on_decision(intraday_long(), T0)
    # One bar sweeps through the limit AND the stop (and even the target):
    # worst case honored, best case not provable → stop.
    sim.on_bar(bar(0, "100.5", "103.0", "97.00", "98"), 0)
    assert sim.position is None and len(sim.trades) == 1
    t = sim.trades[0]
    # gross = (97.75 − 100) / 2.25 = −1 exactly
    # cost  = (100 + 97.75) × 0.0007 / 2.25 = 0.138425 / 2.25 = 0.0615
    # net   = −1 − 0.0615222 = −1.0615
    assert t.outcome == "sl"
    assert t.gross_r == -1.0
    assert t.cost_r == 0.0615
    assert t.net_r == -1.0615


def test_fill_bar_cannot_take_profit():
    sim = _VariantSim(key="intraday", per_side_frac=_frac)
    sim.on_decision(intraday_long(), T0)
    # Fill bar reaches the target but NOT the stop: TP is not credited —
    # the position simply stays open.
    sim.on_bar(bar(0, "100.2", "103.0", "99.90", "102.9"), 0)
    assert sim.position is not None
    assert len(sim.trades) == 0


def test_exit_bar_touching_both_is_a_stop():
    sim = _VariantSim(key="intraday", per_side_frac=_frac)
    sim.on_decision(intraday_long(), T0)
    sim.on_bar(bar(0, "100.1", "100.2", "99.95", "100"), 0)  # clean fill, nothing else
    assert sim.position is not None
    sim.on_bar(bar(1, "100", "103.0", "97.00", "99"), 1)  # both levels inside → stop
    assert sim.trades[0].outcome == "sl"


def test_short_direction_mirrored_golden():
    sim = _VariantSim(key="intraday", per_side_frac=_frac)
    sim.on_decision(intraday_short(), T0)
    assert sim.pending is not None and sim.pending.limit == Decimal("100.00")
    sim.on_bar(bar(0, "99.5", "100.1", "99.4", "99.8"), 0)   # high ≥ 100 → fill at 100
    sim.on_bar(bar(1, "99.8", "99.9", "97.0", "97.3"), 1)    # low ≤ 97.25 → tp
    t = sim.trades[0]
    # risk = 102.25 − 100 = 2.25; gross = (100 − 97.25)/2.25 = 1.2222
    # cost = (100 + 97.25) × 0.0007 / 2.25 = 0.138075 / 2.25 = 0.0614
    # net  = 1.2222222 − 0.0613667 = 1.1608556 → 1.1609
    assert t.outcome == "tp" and t.direction == "short"
    assert t.gross_r == 1.2222
    assert t.cost_r == 0.0614
    assert t.net_r == 1.1609


def test_decision_replaces_pending_and_respects_open_position():
    sim = _VariantSim(key="intraday", per_side_frac=_frac)
    sim.on_decision(intraday_long(), T0)
    first_limit = sim.pending.limit
    # Shelf refreshes with a new (higher) band: old order cancelled, new placed.
    v2 = intraday_long().model_copy(update={
        "entry_high": Decimal("101.00"), "entry_low": Decimal("100.50"),
        "stop": Decimal("98.75"),
    })
    sim.on_decision(v2, T0 + _15M)
    assert sim.pending.limit == Decimal("101.00") != first_limit
    # Now fill it; a further decision must NOT stack a second order.
    sim.on_bar(bar(2, "101.2", "101.3", "100.9", "101"), 2)
    assert sim.position is not None
    sim.on_decision(intraday_long(), T0 + 2 * _15M)
    assert sim.pending is None  # one position per variant, no pyramiding


def test_untradeable_or_neutral_variant_places_no_order():
    sim = _VariantSim(key="intraday", per_side_frac=_frac)
    v = intraday_long().model_copy(update={"tradeable": False, "reason": "mixed"})
    sim.on_decision(v, T0)
    assert sim.pending is None
    sim.on_decision(None, T0)
    assert sim.pending is None


# ── statistics ─────────────────────────────────────────────────────────────


def _trade(net_r: float, outcome: str) -> BacktestTrade:
    return BacktestTrade(
        variant="intraday", direction="long", placed_at=T0, filled_at=T0,
        exit_at=T0, entry=Decimal("100"), stop=Decimal("97.75"),
        target=Decimal("102.75"),
        exit_price=Decimal("102.75") if outcome == "tp" else Decimal("97.75"),
        outcome=outcome, gross_r=net_r, cost_r=0.0, net_r=net_r, bars_held=1,
    )


def test_stats_golden():
    trades = [
        _trade(1.2, "tp"), _trade(-1.05, "sl"), _trade(1.2, "tp"),
        _trade(-1.05, "sl"), _trade(-1.05, "sl"),
    ]
    r = _variant_result("intraday", trades, 0, MonteCarloConfig())
    assert r.n_trades == 5 and r.n_wins == 2 and r.n_losses == 3
    assert r.win_rate == 0.4
    # total = 2×1.2 − 3×1.05 = 2.4 − 3.15 = −0.75; avg = −0.15
    assert r.total_r == -0.75 and r.avg_r == -0.15
    # PF = 2.4 / 3.15 = 0.7619
    assert r.profit_factor == 0.7619
    # equity [1.2, 0.15, 1.35, 0.3, −0.75]; peak 1.35 → trough −0.75 → dd 2.1
    assert r.equity_r == [1.2, 0.15, 1.35, 0.3, -0.75]
    assert r.max_drawdown_r == 2.1
    assert r.max_consecutive_losses == 2
    # 5 trades < 10 → MC honestly skipped with a reason
    assert r.monte_carlo is None and "skipped" in (r.mc_note or "")


def test_stats_empty_and_open_excluded():
    r = _variant_result("scalp", [], 1, MonteCarloConfig())
    assert r.n_trades == 0 and r.n_open_excluded == 1
    assert r.win_rate is None and r.avg_r is None and r.total_r == 0.0


# ── Monte Carlo (seeded — these numbers are the reproducibility contract) ──


def test_monte_carlo_seeded_golden():
    # 10 trades alternating +1.5 / −1.0 (true total +2.5), seed 7, 2000 iters.
    mc = _monte_carlo([1.5, -1.0] * 5, MonteCarloConfig())
    assert mc.total_r_p5 == -5.0
    assert mc.total_r_p25 == 0.0
    assert mc.total_r_p50 == 2.5
    assert mc.total_r_p75 == 5.0
    assert mc.total_r_p95 == 7.5
    assert mc.max_dd_p50 == 3.0
    assert mc.max_dd_p95 == 6.0
    # THE honest headline: a +2.5R history still ends ≤ 0 in 39.4% of resamples.
    assert mc.prob_loss == 0.394


def test_monte_carlo_deterministic_across_runs():
    a = _monte_carlo([0.8, -1.1, 1.4, -0.9, 1.2] * 3, MonteCarloConfig())
    b = _monte_carlo([0.8, -1.1, 1.4, -0.9, 1.2] * 3, MonteCarloConfig())
    assert a == b


# ── no lookahead ───────────────────────────────────────────────────────────


def test_visible_excludes_unclosed_and_caps_window():
    candles = [bar(i, "100", "101", "99", "100") for i in range(250)]
    close_times = [c.close_time for c in candles]
    at = candles[229].close_time
    window = _visible(candles, close_times, at)
    assert len(window) == WARMUP_BARS == 200
    assert window[-1] is candles[229]          # the bar closing AT the decision: visible
    assert window[0] is candles[30]
    # one tick earlier excludes that bar — the boundary is close_time ≤ at
    window2 = _visible(candles, close_times, at - timedelta(seconds=1))
    assert window2[-1] is candles[228]


# ── lean brief ≡ full brief for the directional variants ───────────────────


def _zigzag(n: int, start: datetime, step: timedelta) -> list[Candle]:
    """Rising zigzag: 3 up, 1 down, net higher — produces real swings."""
    out = []
    px = Decimal("100")
    for i in range(n):
        d = Decimal("0.8") if i % 4 != 3 else Decimal("-0.6")
        o = px
        c = px + d
        hi = max(o, c) + Decimal("0.3")
        lo = min(o, c) - Decimal("0.3")
        t = start + i * step
        out.append(Candle(open_time=t, open=o, high=hi, low=lo, close=c,
                          volume=Decimal(1), close_time=t + step))
        px = c
    return out


def test_lean_brief_parity_with_full_brief():
    """Omitting 5m/1d/derivatives/sentiment/daily-levels must not change the
    four gradeable variants (ADR-0020 §2) — they read only the three
    alignment TFs' ATR + close + the alignment bias."""
    series = {tf: _zigzag(220, T0, _15M) for tf in ("5m", "15m", "1h", "4h", "1d")}
    analyses = {tf: analyze_timeframe(tf, c) for tf, c in series.items()}
    align = compute_alignment({tf: analyses[tf] for tf in ALIGNMENT_TIMEFRAMES})

    full = MarketBrief(
        symbol="TESTUSDT", generated_at=T0, timeframes=analyses,
        daily_levels=[], derivatives=None, sentiment=None, alignment=align,
    )
    lean = MarketBrief(
        symbol="TESTUSDT", generated_at=T0,
        timeframes={tf: analyses[tf] for tf in ALIGNMENT_TIMEFRAMES},
        daily_levels=[], derivatives=None, sentiment=None, alignment=align,
    )
    full_dir = [v for v in build_variants(full) if v.key in GRADEABLE_KEYS]
    lean_dir = [v for v in build_variants(lean) if v.key in GRADEABLE_KEYS]
    assert full_dir == lean_dir


# ── the walk-forward loop end to end (synthetic, offline) ──────────────────


def _grid_series(tf_delta: timedelta, n: int, end: datetime) -> list[Candle]:
    start = end - n * tf_delta
    return _zigzag(n, start, tf_delta)


def test_run_backtest_synthetic_end_to_end():
    window_end = datetime(2026, 1, 30, tzinfo=timezone.utc)
    days = 2
    window_start = window_end - timedelta(days=days)
    candles_by_tf = {
        "15m": _grid_series(_15M, 200 + 192, window_end),
        "1h": _grid_series(timedelta(hours=1), 200 + 48, window_end),
        "4h": _grid_series(timedelta(hours=4), 200 + 12, window_end),
    }
    seen: list[tuple[int, int]] = []
    report = run_backtest(
        "TESTUSDT", candles_by_tf, window_start, window_end,
        BacktestConfig(), days, progress=lambda d, t: seen.append((d, t)),
    )
    assert report.n_decisions == 48  # one per closed 1h bar over 2 days
    assert [v.key for v in report.variants] == list(GRADEABLE_KEYS)
    for v in report.variants:
        assert v.n_trades == len(v.trades) == len(v.equity_r)
        assert v.n_wins + v.n_losses == v.n_trades
    assert report.assumptions.mc_seed == 7
    assert seen and seen[-1][0] == seen[-1][1] == 48  # progress reached the end


def test_run_backtest_insufficient_history_raises():
    window_end = datetime(2026, 1, 30, tzinfo=timezone.utc)
    window_start = window_end - timedelta(days=2)
    candles_by_tf = {
        "15m": _grid_series(_15M, 392, window_end),
        "1h": _grid_series(timedelta(hours=1), 248, window_end),
        "4h": _grid_series(timedelta(hours=4), 50, window_end),  # 50 < 200 warmup
    }
    with pytest.raises(ValueError, match="not enough 4h history"):
        run_backtest("TESTUSDT", candles_by_tf, window_start, window_end,
                     BacktestConfig(), 2)


# ── store ──────────────────────────────────────────────────────────────────


def _report(symbol: str, at: datetime) -> BacktestReport:
    cfg = BacktestConfig()
    return BacktestReport(
        symbol=symbol, requested_days=30, window_start=at - timedelta(days=30),
        window_end=at, generated_at=at, n_decisions=0, variants=[],
        assumptions=BacktestAssumptions(
            decision_interval="1h", exit_interval="15m", warmup_bars=200,
            fill_model="", fill_bar_rule="", both_touch_rule="", gap_rule="",
            funding_note="", fees_bps_per_side=cfg.fees_bps_per_side,
            slippage_bps_per_side=cfg.slippage_bps_per_side,
            mc_iterations=2000, mc_seed=7, mc_min_trades=10,
        ),
    )


def test_store_roundtrip_and_eviction(tmp_path):
    store = BacktestStore(tmp_path / "backtests.json")
    assert store.get("BTCUSDT") is None
    store.put(_report("BTCUSDT", T0))
    got = store.get("BTCUSDT")
    assert got is not None and got.symbol == "BTCUSDT"
    # overwrite is per-symbol
    store.put(_report("BTCUSDT", T0 + timedelta(days=1)))
    assert store.get("BTCUSDT").generated_at == T0 + timedelta(days=1)
    # eviction: 12 fresher symbols push BTC (generated_at T0+1d, the oldest) out
    for i in range(_MAX_STORED_SYMBOLS):
        store.put(_report(f"SYM{i}USDT", T0 + timedelta(hours=i + 100)))
    assert store.get("BTCUSDT") is None
    assert store.get(f"SYM{_MAX_STORED_SYMBOLS - 1}USDT") is not None


# ── routes ─────────────────────────────────────────────────────────────────


class _StubRunner:
    def __init__(self, busy: bool = False):
        self.busy = busy
        self.started: tuple[str, int] | None = None

    @property
    def config(self) -> BacktestConfig:
        return BacktestConfig()

    def status(self):
        from app.models.backtest import BacktestJobStatus
        return BacktestJobStatus(state="idle")

    def start(self, symbol: str, days: int) -> None:
        if self.busy:
            raise BacktestBusy()
        self.started = (symbol, days)


def test_backtest_routes(tmp_path):
    app = create_app()
    with TestClient(app) as client:
        app.state.backtest = _StubRunner()
        app.state.backtest_store = BacktestStore(tmp_path / "b.json")

        # forex refused honestly
        r = client.post("/backtest/EURUSD")
        assert r.status_code == 400 and "crypto-only" in r.json()["detail"]

        # default days from config
        r = client.post("/backtest/BTCUSDT")
        assert r.status_code == 202 and r.json()["days"] == 30
        assert app.state.backtest.started == ("BTCUSDT", 30)

        # cap enforced
        assert client.post("/backtest/BTCUSDT?days=120").status_code == 400

        # busy → 409
        app.state.backtest = _StubRunner(busy=True)
        assert client.post("/backtest/BTCUSDT?days=30").status_code == 409

        # status route (declared before the {symbol} route — must not shadow)
        assert client.get("/backtest/status").json()["state"] == "idle"

        # report: 404 before, 200 after
        assert client.get("/backtest/BTCUSDT").status_code == 404
        app.state.backtest_store.put(_report("BTCUSDT", T0))
        body = client.get("/backtest/BTCUSDT").json()
        assert body["symbol"] == "BTCUSDT" and body["assumptions"]["mc_seed"] == 7

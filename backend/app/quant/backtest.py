"""Walk-forward backtest engine (P5 · ADR-0020) — pure, deterministic, no I/O.

Replays the PRODUCTION setup pipeline over historical candles: the same
`analyze_timeframe` → `compute_alignment` → `build_variants` calls the live
shelf makes, then a conservative order/exit simulation. No vectorbt — a
vectorized reimplementation of the strategy would drift from the strategy
(ADR-0020 §1); this engine tests the code that actually runs.

Conservative rules (each stated in the report's assumptions block):
  * decisions only on CLOSED 1h bars; a decision at T sees candles with
    close_time <= T, sliced to the live composer's 200-bar window (no lookahead)
  * limit entry at the WORSE band edge; fills at the limit exactly, never better
  * the bar that fills an entry may stop the trade out, but may not take profit
    (OHLC cannot prove the favorable ordering)
  * an exit bar touching both stop and target counts as a stop (grading.py's
    documented fallback — the live grader drills to 1m; a 90-day replay cannot)
  * every reported R is NET of per-side fees + slippage (config/backtest.yaml)

Monte Carlo bootstrap (seeded, reproducible): resamples each variant's net-R
sequence to put confidence intervals on total R and max drawdown, plus
`prob_loss` — the share of resampled histories ending <= 0. Skipped with a
stated reason below `min_trades` (ADR-0018's freeze-below-N honesty).
"""

import random
from bisect import bisect_right
from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal
from pathlib import Path
from typing import Callable, Literal

import yaml
from pydantic import BaseModel, Field

from app.desk.setups import build_variants
from app.models.backtest import (
    BacktestAssumptions,
    BacktestReport,
    BacktestTrade,
    MonteCarloOut,
    VariantResult,
)
from app.models.brief import MarketBrief
from app.models.market import Candle
from app.models.setups import SetupVariant
from app.quant.brief import (
    ALIGNMENT_TIMEFRAMES,
    KLINE_LIMIT,
    analyze_timeframe,
    compute_alignment,
)

DECISION_TF = "1h"
EXIT_TF = "15m"
# Alignment's three TFs are exactly the gradeable variants' anchor TFs — the
# lean brief needs nothing else (parity-tested in tests/test_backtest.py).
ANALYSIS_TFS: tuple[str, ...] = ALIGNMENT_TIMEFRAMES
WARMUP_BARS = KLINE_LIMIT  # the same 200-bar window the live composer analyzes
GRADEABLE_KEYS: tuple[str, ...] = ("scalp", "intraday", "swing", "spot")

_BPS = Decimal(10_000)
_R_Q = Decimal("0.0001")


# ── config (config/backtest.yaml — invariant 6; values pinned by golden tests) ──

class MonteCarloConfig(BaseModel):
    iterations: int = 2000
    seed: int = 7
    min_trades: int = 10


class BacktestConfig(BaseModel):
    window_days_default: int = 30
    window_days_max: int = 90
    fees_bps_per_side: dict[str, float] = Field(
        default_factory=lambda: {"PERP": 5.0, "MARGIN": 10.0, "SPOT": 10.0}
    )
    slippage_bps_per_side: float = 2.0
    monte_carlo: MonteCarloConfig = Field(default_factory=MonteCarloConfig)


def load_backtest_config(path: str | Path) -> BacktestConfig:
    p = Path(path)
    if not p.exists():
        return BacktestConfig()
    data = yaml.safe_load(p.read_text(encoding="utf-8")) or {}
    return BacktestConfig(**data)


# ── per-variant order/position state machine ──

@dataclass
class _Pending:
    direction: Literal["long", "short"]
    limit: Decimal
    stop: Decimal
    target: Decimal
    venue: str
    placed_at: datetime


@dataclass
class _Position:
    direction: Literal["long", "short"]
    entry: Decimal
    stop: Decimal
    target: Decimal
    venue: str
    placed_at: datetime
    filled_at: datetime
    fill_bar: int


@dataclass
class _VariantSim:
    key: str
    per_side_frac: Callable[[str], Decimal]
    pending: _Pending | None = None
    position: _Position | None = None
    trades: list[BacktestTrade] = field(default_factory=list)

    def on_bar(self, bar: Candle, idx: int) -> None:
        if self.position is not None:
            self._check_exit(bar, idx)
        elif self.pending is not None:
            self._check_fill(bar, idx)

    def on_decision(self, variant: SetupVariant | None, at: datetime) -> None:
        # The shelf refreshed: any unfilled order is stale — cancel it. An OPEN
        # position rides to its own stop/target (a taken trade grades at its
        # saved levels, same as the live journal).
        self.pending = None
        if self.position is not None or variant is None:
            return
        if not (variant.tradeable and variant.gradeable):
            return
        if variant.direction not in ("long", "short") or not variant.targets:
            return
        assert variant.entry_low is not None and variant.entry_high is not None
        assert variant.stop is not None
        limit = variant.entry_high if variant.direction == "long" else variant.entry_low
        self.pending = _Pending(
            direction=variant.direction,
            limit=limit,
            stop=variant.stop,
            target=variant.targets[0].price,  # graded to TP1, like the live journal
            venue=variant.venue,
            placed_at=at,
        )

    def _check_fill(self, bar: Candle, idx: int) -> None:
        p = self.pending
        assert p is not None
        touched = bar.low <= p.limit if p.direction == "long" else bar.high >= p.limit
        if not touched:
            return
        self.pending = None
        self.position = _Position(
            direction=p.direction, entry=p.limit, stop=p.stop, target=p.target,
            venue=p.venue, placed_at=p.placed_at, filled_at=bar.open_time,
            fill_bar=idx,
        )
        # Fill-bar rule: the worst case (stop also inside this bar) is honored;
        # the best case (target inside this bar) cannot be proven from OHLC and
        # is NOT credited.
        hit_stop = (
            bar.low <= p.stop if p.direction == "long" else bar.high >= p.stop
        )
        if hit_stop:
            self._close(bar, idx, outcome="sl")

    def _check_exit(self, bar: Candle, idx: int) -> None:
        pos = self.position
        assert pos is not None
        if pos.direction == "long":
            hit_stop, hit_tp = bar.low <= pos.stop, bar.high >= pos.target
        else:
            hit_stop, hit_tp = bar.high >= pos.stop, bar.low <= pos.target
        if hit_stop:  # both-touch resolves to the stop — conservative by rule
            self._close(bar, idx, outcome="sl")
        elif hit_tp:
            self._close(bar, idx, outcome="tp")

    def _close(self, bar: Candle, idx: int, outcome: Literal["tp", "sl"]) -> None:
        pos = self.position
        assert pos is not None
        self.position = None
        exit_price = pos.stop if outcome == "sl" else pos.target
        risk = abs(pos.entry - pos.stop)
        if risk == 0:  # cannot happen by construction (stop sits a multiple of ATR away)
            return
        moved = exit_price - pos.entry if pos.direction == "long" else pos.entry - exit_price
        gross_r = moved / risk
        frac = self.per_side_frac(pos.venue)
        cost_r = (pos.entry + exit_price) * frac / risk
        net_r = (gross_r - cost_r).quantize(_R_Q)
        self.trades.append(BacktestTrade(
            variant=self.key,  # type: ignore[arg-type]
            direction=pos.direction,
            placed_at=pos.placed_at,
            filled_at=pos.filled_at,
            exit_at=bar.open_time,
            entry=pos.entry, stop=pos.stop, target=pos.target, exit_price=exit_price,
            outcome=outcome,
            gross_r=float(gross_r.quantize(_R_Q)),
            cost_r=float(cost_r.quantize(_R_Q)),
            net_r=float(net_r),
            bars_held=idx - pos.fill_bar + 1,
        ))


# ── statistics + Monte Carlo ──

def _max_drawdown(equity: list[float]) -> float:
    """Peak-to-trough on the cumulative net-R curve; the starting flat account
    (0 R) counts as a peak, so a losing-from-the-start run still reports its
    full drawdown."""
    peak, dd = 0.0, 0.0
    for e in equity:
        peak = max(peak, e)
        dd = max(dd, peak - e)
    return round(dd, 4)


def _variant_result(
    key: str, trades: list[BacktestTrade], open_excluded: int, mc_cfg: MonteCarloConfig
) -> VariantResult:
    n = len(trades)
    wins = sum(1 for t in trades if t.outcome == "tp")
    losses = n - wins
    equity: list[float] = []
    cum = 0.0
    for t in trades:
        cum += t.net_r
        equity.append(round(cum, 4))
    pos_sum = sum(t.net_r for t in trades if t.net_r > 0)
    neg_sum = sum(t.net_r for t in trades if t.net_r < 0)
    consec = worst_consec = 0
    for t in trades:
        consec = consec + 1 if t.outcome == "sl" else 0
        worst_consec = max(worst_consec, consec)

    mc: MonteCarloOut | None = None
    mc_note: str | None = None
    if n >= mc_cfg.min_trades:
        mc = _monte_carlo([t.net_r for t in trades], mc_cfg)
    else:
        mc_note = (
            f"Monte Carlo skipped: {n} closed trades < {mc_cfg.min_trades} minimum — "
            "an interval over this few trades would be false precision"
        )

    return VariantResult(
        key=key,  # type: ignore[arg-type]
        n_trades=n,
        n_wins=wins,
        n_losses=losses,
        n_open_excluded=open_excluded,
        win_rate=round(wins / n, 4) if n else None,
        avg_r=round(sum(t.net_r for t in trades) / n, 4) if n else None,
        total_r=round(cum, 4),
        profit_factor=round(pos_sum / abs(neg_sum), 4) if neg_sum < 0 else None,
        max_drawdown_r=_max_drawdown(equity),
        max_consecutive_losses=worst_consec,
        equity_r=equity,
        monte_carlo=mc,
        mc_note=mc_note,
        trades=trades,
    )


def _percentile(sorted_vals: list[float], q: float) -> float:
    """Linear-interpolated percentile over a pre-sorted list (the standard
    'linear' method). Hand-rolled: this backend is deliberately pure Python
    (§F6 — no compiled deps), and 7 lines beat a numpy install."""
    n = len(sorted_vals)
    if n == 1:
        return sorted_vals[0]
    pos = q / 100 * (n - 1)
    lo = int(pos)
    hi = min(lo + 1, n - 1)
    frac = pos - lo
    return sorted_vals[lo] * (1 - frac) + sorted_vals[hi] * frac


def _monte_carlo(net_rs: list[float], cfg: MonteCarloConfig) -> MonteCarloOut:
    """Bootstrap-resample the trade sequence. Resampling with replacement asks:
    'if trades like these kept arriving in random order, what histories could
    this variant have lived?' Seeded `random.Random` — Python guarantees the
    same seed gives the same sequence on every platform, so goldens can pin
    the outputs exactly (and §F6 parity holds with zero new dependencies)."""
    rng = random.Random(cfg.seed)
    n = len(net_rs)
    totals: list[float] = []
    dds: list[float] = []
    n_loss = 0
    for _ in range(cfg.iterations):
        sample = rng.choices(net_rs, k=n)
        cum = peak = dd = 0.0
        for r in sample:
            cum += r
            if cum > peak:
                peak = cum
            elif peak - cum > dd:
                dd = peak - cum
        totals.append(cum)
        dds.append(dd)
        if cum <= 0.0:
            n_loss += 1
    totals.sort()
    dds.sort()
    return MonteCarloOut(
        iterations=cfg.iterations,
        seed=cfg.seed,
        total_r_p5=round(_percentile(totals, 5), 3),
        total_r_p25=round(_percentile(totals, 25), 3),
        total_r_p50=round(_percentile(totals, 50), 3),
        total_r_p75=round(_percentile(totals, 75), 3),
        total_r_p95=round(_percentile(totals, 95), 3),
        max_dd_p50=round(_percentile(dds, 50), 3),
        max_dd_p95=round(_percentile(dds, 95), 3),
        prob_loss=round(n_loss / cfg.iterations, 4),
    )


# ── the walk-forward loop ──

ProgressCb = Callable[[int, int], None]


def _visible(candles: list[Candle], close_times: list[datetime], at: datetime) -> list[Candle]:
    """Candles closed at-or-before `at`, capped to the live composer's window.
    Strictly closed data — the live shelf additionally sees a forming bar, so
    the backtest sits on the conservative side of live."""
    idx = bisect_right(close_times, at)
    return candles[max(0, idx - WARMUP_BARS):idx]


def _lean_brief(
    symbol: str,
    at: datetime,
    candles_by_tf: dict[str, list[Candle]],
    close_times_by_tf: dict[str, list[datetime]],
    cache: dict[str, tuple[datetime, object]],
) -> MarketBrief:
    timeframes = {}
    for tf in ANALYSIS_TFS:
        window = _visible(candles_by_tf[tf], close_times_by_tf[tf], at)
        last_close_time = window[-1].close_time
        cached = cache.get(tf)
        if cached is not None and cached[0] == last_close_time:
            timeframes[tf] = cached[1]
        else:
            analysis = analyze_timeframe(tf, window)
            cache[tf] = (last_close_time, analysis)
            timeframes[tf] = analysis
    return MarketBrief(
        symbol=symbol,
        generated_at=at,
        timeframes=timeframes,  # type: ignore[arg-type]
        daily_levels=[],
        derivatives=None,
        sentiment=None,
        alignment=compute_alignment(timeframes),  # type: ignore[arg-type]
        gaps=[
            "backtest lean brief: 5m/1d, derivatives, sentiment, daily levels "
            "omitted — no gradeable variant reads them (ADR-0020 §2)"
        ],
    )


def run_backtest(
    symbol: str,
    candles_by_tf: dict[str, list[Candle]],
    window_start: datetime,
    window_end: datetime,
    config: BacktestConfig,
    requested_days: int,
    progress: ProgressCb | None = None,
) -> BacktestReport:
    """Pure CPU walk-forward over pre-fetched candles. Raises ValueError on
    insufficient history (the honest failure — a silently short warmup would
    quietly change what the structure engine sees)."""
    for tf in ANALYSIS_TFS:
        series = candles_by_tf.get(tf) or []
        n_before = sum(1 for c in series if c.close_time <= window_start)
        if n_before < WARMUP_BARS:
            raise ValueError(
                f"not enough {tf} history: {n_before} closed bars before the window, "
                f"{WARMUP_BARS} needed for the analysis warmup"
            )

    close_times_by_tf = {
        tf: [c.close_time for c in candles_by_tf[tf]] for tf in ANALYSIS_TFS
    }
    fees = {k: Decimal(str(v)) for k, v in config.fees_bps_per_side.items()}
    slip = Decimal(str(config.slippage_bps_per_side))
    worst_fee = max(fees.values()) if fees else Decimal(0)

    def per_side_frac(venue: str) -> Decimal:
        # Unknown venue charges the worst configured fee — conservative default.
        return (fees.get(venue, worst_fee) + slip) / _BPS

    sims = {k: _VariantSim(key=k, per_side_frac=per_side_frac) for k in GRADEABLE_KEYS}
    exit_bars = [
        c for c in candles_by_tf[EXIT_TF]
        if window_start < c.close_time <= window_end
    ]
    # A 15m bar opening at :45 is the last of its hour — its close IS the 1h close.
    decision_flags = [
        b.open_time.minute == 45 and b.open_time.second == 0 for b in exit_bars
    ]
    total_decisions = sum(decision_flags)
    tf_cache: dict[str, tuple[datetime, object]] = {}

    done = 0
    for idx, bar in enumerate(exit_bars):
        for sim in sims.values():
            sim.on_bar(bar, idx)
        if decision_flags[idx]:
            brief = _lean_brief(
                symbol, bar.close_time, candles_by_tf, close_times_by_tf, tf_cache
            )
            by_key = {v.key: v for v in build_variants(brief)}
            for key, sim in sims.items():
                sim.on_decision(by_key.get(key), bar.close_time)
            done += 1
            if progress is not None and (done % 24 == 0 or done == total_decisions):
                progress(done, total_decisions)

    mc_cfg = config.monte_carlo
    variants = [
        _variant_result(k, sim.trades, 1 if sim.position is not None else 0, mc_cfg)
        for k, sim in sims.items()
    ]
    return BacktestReport(
        symbol=symbol,
        requested_days=requested_days,
        window_start=window_start,
        window_end=window_end,
        generated_at=window_end,
        n_decisions=total_decisions,
        variants=variants,
        assumptions=BacktestAssumptions(
            decision_interval=DECISION_TF,
            exit_interval=EXIT_TF,
            warmup_bars=WARMUP_BARS,
            fill_model=(
                "limit at the worse band edge (long: entry_high, short: entry_low); "
                "fills at the limit exactly, never better; unfilled orders are "
                "cancelled at the next hourly decision"
            ),
            fill_bar_rule=(
                "the bar that fills the entry may stop the trade out, but may not "
                "take profit — OHLC cannot prove the favorable ordering"
            ),
            both_touch_rule=(
                "an exit bar touching both stop and target counts as a stop "
                "(grading.py's documented conservative fallback)"
            ),
            gap_rule="exits fill at the level exactly; gaps are not modeled beyond slippage bps",
            funding_note=(
                "PERP funding costs are not modeled separately in v1 — the flat "
                "slippage line absorbs them approximately"
            ),
            fees_bps_per_side=config.fees_bps_per_side,
            slippage_bps_per_side=config.slippage_bps_per_side,
            mc_iterations=mc_cfg.iterations,
            mc_seed=mc_cfg.seed,
            mc_min_trades=mc_cfg.min_trades,
        ),
        notes=[
            f"Results describe the last {requested_days} days' regime; they do not "
            "promise the next.",
            "grid/options variants are not gradeable (ADR-0019) and sit out of the backtest.",
            "Every R is NET of fees + slippage; graded to TP1, like the live journal.",
        ],
    )


__all__ = [
    "BacktestConfig",
    "MonteCarloConfig",
    "load_backtest_config",
    "run_backtest",
    "ANALYSIS_TFS",
    "WARMUP_BARS",
    "EXIT_TF",
    "GRADEABLE_KEYS",
]

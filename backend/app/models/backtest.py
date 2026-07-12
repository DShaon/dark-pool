"""Backtest report contracts (P5 · ADR-0020).

Every report embeds its `assumptions` block — a simulation's numbers are only
as honest as its stated rules (NFR-7 applies to simulations too). Price fields
are Decimal serialized as strings (invariant 3); R multiples and statistics
are ratios, not money, and travel as floats.
"""

from datetime import datetime
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, Field, field_serializer

from app.models.setups import VariantKey


class BacktestTrade(BaseModel):
    variant: VariantKey
    direction: Literal["long", "short"]
    placed_at: datetime
    filled_at: datetime
    exit_at: datetime
    entry: Decimal
    stop: Decimal
    target: Decimal
    exit_price: Decimal
    outcome: Literal["tp", "sl"]
    gross_r: float
    cost_r: float
    net_r: float
    bars_held: int  # 15m exit-walk bars from fill to exit, inclusive

    @field_serializer("entry", "stop", "target", "exit_price")
    def _ser(self, v: Decimal) -> str:
        return format(v, "f")


class MonteCarloOut(BaseModel):
    iterations: int
    seed: int
    total_r_p5: float
    total_r_p25: float
    total_r_p50: float
    total_r_p75: float
    total_r_p95: float
    max_dd_p50: float
    max_dd_p95: float
    prob_loss: float  # share of resampled histories ending with total R <= 0


class VariantResult(BaseModel):
    key: VariantKey
    n_trades: int
    n_wins: int
    n_losses: int
    n_open_excluded: int  # still open when data ended — excluded from stats
    win_rate: float | None = None  # None when n_trades == 0
    avg_r: float | None = None
    total_r: float = 0.0
    profit_factor: float | None = None  # None when no losing trades yet
    max_drawdown_r: float = 0.0
    max_consecutive_losses: int = 0
    equity_r: list[float] = Field(default_factory=list)  # cumulative net R per trade
    monte_carlo: MonteCarloOut | None = None
    mc_note: str | None = None  # why MC was skipped, when it was
    trades: list[BacktestTrade] = Field(default_factory=list)


class BacktestAssumptions(BaseModel):
    decision_interval: str
    exit_interval: str
    warmup_bars: int
    fill_model: str
    fill_bar_rule: str
    both_touch_rule: str
    gap_rule: str
    funding_note: str
    fees_bps_per_side: dict[str, float]
    slippage_bps_per_side: float
    mc_iterations: int
    mc_seed: int
    mc_min_trades: int


class BacktestReport(BaseModel):
    symbol: str
    requested_days: int
    window_start: datetime
    window_end: datetime
    generated_at: datetime
    n_decisions: int
    variants: list[VariantResult]
    assumptions: BacktestAssumptions
    notes: list[str] = Field(default_factory=list)


class BacktestJobStatus(BaseModel):
    state: Literal["idle", "running", "done", "error"]
    symbol: str | None = None
    days: int | None = None
    progress: float = 0.0  # 0..1, meaningful while running
    message: str | None = None  # phase while running, error detail on failure


__all__ = [
    "BacktestTrade",
    "MonteCarloOut",
    "VariantResult",
    "BacktestAssumptions",
    "BacktestReport",
    "BacktestJobStatus",
]

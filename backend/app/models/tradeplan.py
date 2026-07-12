"""TradePlan contracts — the CIO layer's output (FR-4 · §B5 · ADR-0015).

This is the desk's final word on a symbol: ONE plan, synthesized from the
analyst panel, with a divergence verdict and a calibrated confidence that
traces to ADR-0007's formula (NFR-7: every number auditable).

v1 scope (ADR-0015): a single primary intraday plan. The FR-4 setup-variant
fan (conservative/aggressive/scalp/swing/position) stays a later pass — one
correct plan beats six flaky ones.

Money fields are Decimal serialized as strings (invariant 3). The plan's
numeric levels are guard-railed IN CODE against the panel's published levels
(app/desk/cio.py) — the schema here enforces shape, the service enforces
provenance.
"""

from datetime import datetime
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, Field, field_serializer, model_validator

from app.models.analyst import Mandate
from app.models.quickread import EntryZone, Invalidation, Target

ConsensusState = Literal["aligned", "split", "contested"]
Direction = Literal["long", "short", "no_trade"]


class SeatVoteOut(BaseModel):
    """One seat's raw call — carried on the plan so graded outcomes can score
    seat reliability later (ADR-0018) and the user can audit who said what."""

    direction: Direction
    conviction: int = Field(ge=1, le=5)


class DivergenceReport(BaseModel):
    """Deterministic classification of the panel's disagreement (§B5).

    `notes` records WHY the state was assigned — the audit trail that keeps
    the classification honest and debuggable.
    """

    consensus_state: ConsensusState
    plurality_direction: Direction
    votes: dict[str, int]  # direction -> seat count
    conviction_weighted: dict[str, int]  # direction -> summed conviction
    votes_by_seat: dict[str, SeatVoteOut] = Field(default_factory=dict)
    entry_cluster: bool | None = None  # None = not enough data to judge
    stop_cluster: bool | None = None
    conviction_spread: int = 0  # max - min conviction among survivors
    notes: list[str] = Field(default_factory=list)


class ConfidenceBreakdown(BaseModel):
    """ADR-0007: confidence = 0.5 x deterministic checklist + 0.5 x agreement.

    Every component is recorded; components that could not be computed from
    the brief (missing data) appear in `excluded` and are dropped from the
    checklist average — missing data must never manufacture (or fake) signal.
    Floats: confidence is analytics, not money math.
    """

    value: float = Field(ge=0.0, le=1.0)  # the published number
    checklist: float = Field(ge=0.0, le=1.0)
    agreement: float = Field(ge=0.0, le=1.0)
    components: dict[str, float]  # name -> 0..1 (only the computed ones)
    excluded: list[str] = Field(default_factory=list)  # missing-data components
    state_base: float = Field(ge=0.0, le=1.0)  # from consensus_state
    weighted_vote_share: float = Field(ge=0.0, le=1.0)
    # Recalibration (ADR-0018). Defaults = the uncalibrated formula, so plans
    # published before any outcomes exist are unchanged and say so honestly.
    calibrated: bool = False
    blend_w: float = 0.5  # weight on the checklist half actually used
    seat_weights: dict[str, float] = Field(default_factory=dict)  # applied multipliers


class SizingOut(BaseModel):
    """Risk-based position sizing (advisory %; no execution — invariant 5)."""

    risk_pct: float  # % of account risked if the stop is hit
    stop_distance_pct: float  # entry->stop distance as % of entry
    position_pct: float  # % of account notional to deploy
    capped: bool = False  # True if max_position_pct clamped the raw size
    implied_leverage: float  # position_pct / 100 (1.0 = unlevered full account)


class TradePlan(BaseModel):
    """The desk's one call. Directional plans carry full levels; a no_trade
    plan is a first-class STAND ASIDE with the same reasoning discipline."""

    symbol: str
    direction: Direction
    consensus_state: ConsensusState
    confidence: ConfidenceBreakdown
    divergence: DivergenceReport
    entry_zone: EntryZone | None = None
    confirmation: list[str] = Field(default_factory=list, max_length=3)
    stop_loss: Decimal | None = None
    targets: list[Target] = Field(default_factory=list, max_length=3)
    invalidation: Invalidation | None = None
    sizing: SizingOut | None = None
    thesis: str = Field(min_length=20, max_length=900)
    failure_mode: str = Field(min_length=10, max_length=400)
    alternative_scenario: str = Field(min_length=10, max_length=400)
    thesis_bn: str | None = Field(default=None, max_length=1400)
    failure_mode_bn: str | None = Field(default=None, max_length=700)
    evidence: list[str] = Field(min_length=1, max_length=12)
    # Which mandates' published levels this plan was built from (provenance).
    built_from: list[Mandate] = Field(default_factory=list)
    synthesizer: str  # "provider/model" or "deterministic_fallback"

    @model_validator(mode="after")
    def _trade_needs_levels(self) -> "TradePlan":
        if self.direction != "no_trade":
            missing = [
                name
                for name, v in (
                    ("entry_zone", self.entry_zone),
                    ("stop_loss", self.stop_loss),
                    ("invalidation", self.invalidation),
                )
                if v is None
            ]
            if not self.targets:
                missing.append("targets")
            if missing:
                raise ValueError(
                    f"direction={self.direction} requires: {', '.join(missing)}"
                )
        return self

    @field_serializer("stop_loss")
    def _ser_stop(self, v: Decimal | None) -> str | None:
        return None if v is None else str(v)


class TradePlanResponse(BaseModel):
    """API envelope. Degrades (plan=None + reason) — never a 500 (NFR-3)."""

    symbol: str
    generated_at: datetime
    brief_generated_at: datetime
    status: Literal["ok", "degraded"]
    reason: str | None = None
    plan: TradePlan | None = None


__all__ = [
    "ConsensusState",
    "Direction",
    "DivergenceReport",
    "ConfidenceBreakdown",
    "SizingOut",
    "TradePlan",
    "TradePlanResponse",
]

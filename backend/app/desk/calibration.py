"""Confidence recalibration (ADR-0007 · ADR-0018) — graded outcomes feed back
into the confidence formula. THE money-risk module: a subtle error here skews
every future published confidence, quietly. Every constant is a documented
decision (ADR-0018); changing one requires a new ADR, not an edit.

What it does, from a rolling log of graded CIO-plan outcomes:

  1. **Seat reliability** — per mandate seat: a directional vote scores a hit
     when (voted with the plan AND it hit TP) or (dissented AND it hit SL).
     `no_trade` votes are never scored (an abstention has no counterfactual).
     Accuracy is decayed by outcome recency (λ = 0.977 per outcome, half-life
     ≈ 30 trades — count-based, so quiet weeks don't erase knowledge), shrunk
     toward 50% with a Beta(2,2) prior (4 pseudo-observations), and mapped to
     a weight clamped to [0.6, 1.4]: a cold seat is neutral (1.0), a bad seat
     is dampened but never silenced (mandate diversity is the design), a hot
     seat is boosted but capped.
  2. **Blend weight** — ADR-0007's 0.5/0.5 checklist/agreement blend is
     re-fit by grid-searching w ∈ [0.30, 0.70] (step 0.05) to minimize the
     recency-decayed Brier score of `w·checklist + (1−w)·agreement` against
     outcomes (TP=1, SL=0), then SHRUNK toward 0.5 by sample size
     (w ← 0.5 + (w_opt − 0.5)·n_eff/(n_eff+50)) and frozen at exactly 0.5
     below 10 effective outcomes. Overfitting a dozen trades must not move
     the desk's published numbers.
  3. **Calibration curve** — win-rate per published-confidence bucket, the
     journal's honesty view (NFR-7).

HARD RULE: these weights adjust CONFIDENCE only — never the divergence
plurality, never direction. Letting learned weights flip trade direction
would compound a lucky streak into a feedback loop.

Recalibration is a PURE function recomputed from the full outcome log on
every write — no incremental state to drift, fully auditable, fully testable.
The log is file-backed (single-user P1, same pattern as monitor/state.py).
"""

from __future__ import annotations

import contextlib
import json
import os
import tempfile
from datetime import datetime
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field

# ── the constants (ADR-0018; changing any needs a new ADR) ──
DECAY = 0.977  # per-outcome decay; 0.977^30 ≈ 0.5 → half-life ~30 trades
PRIOR_HITS = 2.0  # Beta(2,2): 4 pseudo-observations at 50%
PRIOR_MISSES = 2.0
SEAT_WEIGHT_MIN = 0.6  # a bad seat is dampened, never silenced
SEAT_WEIGHT_MAX = 1.4  # a hot seat is capped, never dominant
BLEND_GRID = [round(0.30 + 0.05 * i, 2) for i in range(9)]  # 0.30 … 0.70
BLEND_SHRINK = 50.0  # pseudo-count pulling w back toward 0.5
MIN_EFF_N_FOR_BLEND = 10.0  # below this, w stays exactly 0.5
MAX_OUTCOMES = 500  # rolling log cap (single-user file store)
MANDATES = ("trend", "contrarian", "derivatives", "risk")


class SeatVote(BaseModel):
    direction: Literal["long", "short", "no_trade"]
    conviction: int = Field(ge=1, le=5)


class OutcomeRecord(BaseModel):
    """One graded, plan-sourced trade — the unit of learning."""

    symbol: str
    direction: Literal["long", "short"]
    outcome: Literal["tp", "sl"]
    confidence: float = Field(ge=0.0, le=1.0)  # as published
    checklist: float = Field(ge=0.0, le=1.0)  # the two formula halves,
    agreement: float = Field(ge=0.0, le=1.0)  # as published
    seat_votes: dict[str, SeatVote] = Field(default_factory=dict)
    closed_at: datetime


class SeatScore(BaseModel):
    eff_n: float  # decayed count of scored (directional) votes
    eff_hits: float  # decayed hits
    accuracy: float  # shrunk posterior mean (Beta prior included)
    weight: float  # clamped multiplier applied to this seat's conviction


class CurveBucket(BaseModel):
    lo: float
    hi: float
    n: int
    wins: int
    win_rate: float | None  # None when the bucket is empty


class CalibrationState(BaseModel):
    """Everything recomputed from the log — served by GET /calibration."""

    n_outcomes: int
    eff_n: float  # decayed sample size
    blend_w: float  # weight on the checklist half (0.5 = uncalibrated)
    blend_active: bool  # False while below MIN_EFF_N_FOR_BLEND
    seats: dict[str, SeatScore]
    brier_blended: float | None  # decayed Brier of the recalibrated blend
    brier_checklist: float | None  # …of checklist alone (w=1)
    brier_agreement: float | None  # …of agreement alone (w=0)
    curve: list[CurveBucket]


class CalibrationParams(BaseModel):
    """The slice `compute_confidence` consumes (kept minimal on purpose)."""

    blend_w: float = 0.5
    seat_weights: dict[str, float] = Field(default_factory=dict)


# ── the pure formula ──────────────────────────────────────────────────────


def _seat_hit(vote: SeatVote, plan_direction: str, outcome: str) -> bool | None:
    """None = not scoreable (abstention). Hit = agreed & TP, or dissented & SL."""
    if vote.direction == "no_trade":
        return None
    agreed = vote.direction == plan_direction
    return agreed == (outcome == "tp")


def _decayed_brier(outcomes: list[OutcomeRecord], w: float) -> float:
    """Recency-weighted Brier of w·checklist + (1−w)·agreement vs outcomes.
    `outcomes` must be oldest-first; the most recent carries weight 1."""
    num = 0.0
    den = 0.0
    last = len(outcomes) - 1
    for i, o in enumerate(outcomes):
        lam = DECAY ** (last - i)
        y = 1.0 if o.outcome == "tp" else 0.0
        p = w * o.checklist + (1.0 - w) * o.agreement
        num += lam * (p - y) ** 2
        den += lam
    return num / den if den else 0.0


def recalibrate(outcomes: list[OutcomeRecord]) -> CalibrationState:
    """The formula. `outcomes` oldest-first. Deterministic; no I/O."""
    last = len(outcomes) - 1
    eff_n_total = sum(DECAY ** (last - i) for i in range(len(outcomes)))

    # ── seat reliability ──
    seats: dict[str, SeatScore] = {}
    for mandate in MANDATES:
        eff_n = 0.0
        eff_h = 0.0
        for i, o in enumerate(outcomes):
            vote = o.seat_votes.get(mandate)
            if vote is None:
                continue
            hit = _seat_hit(vote, o.direction, o.outcome)
            if hit is None:
                continue  # abstention — never scored
            lam = DECAY ** (last - i)
            eff_n += lam
            eff_h += lam * (1.0 if hit else 0.0)
        accuracy = (eff_h + PRIOR_HITS) / (eff_n + PRIOR_HITS + PRIOR_MISSES)
        weight = max(SEAT_WEIGHT_MIN, min(SEAT_WEIGHT_MAX, accuracy / 0.5))
        seats[mandate] = SeatScore(
            eff_n=round(eff_n, 4),
            eff_hits=round(eff_h, 4),
            accuracy=round(accuracy, 4),
            weight=round(weight, 4),
        )

    # ── blend weight ──
    blend_active = eff_n_total >= MIN_EFF_N_FOR_BLEND
    blend_w = 0.5
    if blend_active:
        w_opt = min(BLEND_GRID, key=lambda w: _decayed_brier(outcomes, w))
        blend_w = 0.5 + (w_opt - 0.5) * (eff_n_total / (eff_n_total + BLEND_SHRINK))
        blend_w = round(blend_w, 3)

    # ── honesty metrics ──
    brier_blended = round(_decayed_brier(outcomes, blend_w), 4) if outcomes else None
    brier_checklist = round(_decayed_brier(outcomes, 1.0), 4) if outcomes else None
    brier_agreement = round(_decayed_brier(outcomes, 0.0), 4) if outcomes else None

    # ── calibration curve (undecayed counts — it reports history, not weights) ──
    curve: list[CurveBucket] = []
    for b in range(10):
        lo, hi = b / 10, (b + 1) / 10
        inb = [o for o in outcomes if lo <= o.confidence < hi or (hi == 1.0 and o.confidence == 1.0)]
        wins = sum(1 for o in inb if o.outcome == "tp")
        curve.append(
            CurveBucket(
                lo=lo, hi=hi, n=len(inb), wins=wins,
                win_rate=round(wins / len(inb), 3) if inb else None,
            )
        )

    return CalibrationState(
        n_outcomes=len(outcomes),
        eff_n=round(eff_n_total, 4),
        blend_w=blend_w,
        blend_active=blend_active,
        seats=seats,
        brier_blended=brier_blended,
        brier_checklist=brier_checklist,
        brier_agreement=brier_agreement,
        curve=curve,
    )


def params_from_state(state: CalibrationState) -> CalibrationParams:
    return CalibrationParams(
        blend_w=state.blend_w,
        seat_weights={m: s.weight for m, s in state.seats.items()},
    )


# ── the store (file-backed, single-user P1) ───────────────────────────────


def _atomic_write_json(path: Path, data: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=str(path.parent), suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        os.replace(tmp, path)
    except BaseException:
        with contextlib.suppress(OSError):
            os.unlink(tmp)
        raise


class CalibrationStore:
    """Rolling outcome log (oldest-first) + recompute-on-read state."""

    def __init__(self, path: Path) -> None:
        self._path = Path(path)

    def _load(self) -> list[OutcomeRecord]:
        try:
            raw = json.loads(self._path.read_text(encoding="utf-8"))
        except (FileNotFoundError, json.JSONDecodeError):
            return []
        if not isinstance(raw, list):
            return []
        out: list[OutcomeRecord] = []
        for row in raw:
            with contextlib.suppress(Exception):
                out.append(OutcomeRecord.model_validate(row))
        return out

    def record(self, outcome: OutcomeRecord) -> tuple[CalibrationState, bool]:
        """Append + recalibrate. Idempotent on (symbol, closed_at): re-posting
        the same graded trade (page reloads re-grade) must not double-count
        learning. Returns (state, added)."""
        outcomes = self._load()
        for o in outcomes:
            if o.symbol == outcome.symbol and o.closed_at == outcome.closed_at:
                return recalibrate(outcomes), False
        outcomes.append(outcome)
        outcomes = outcomes[-MAX_OUTCOMES:]
        _atomic_write_json(self._path, [o.model_dump(mode="json") for o in outcomes])
        return recalibrate(outcomes), True

    def state(self) -> CalibrationState:
        return recalibrate(self._load())

    def params(self) -> CalibrationParams:
        return params_from_state(self.state())


__all__ = [
    "OutcomeRecord",
    "SeatVote",
    "CalibrationState",
    "CalibrationParams",
    "CalibrationStore",
    "recalibrate",
    "params_from_state",
    "DECAY",
]

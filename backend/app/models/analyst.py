"""Analyst panel contracts (P2 · §B5 · §F4).

Four mandate analysts see the SAME Market Brief and do four DIFFERENT jobs
(ADR-0005: mandate diversity > model diversity). Each emits the same
evidence-locked trade contract as the Quick Read, so we REUSE `QuickRead` as the
per-analyst payload and wrap it with which seat produced it and on which model.

A failing analyst is DROPPED, never blocks the run (invariant 2 / NFR-3).

Scope note: this module is plumbing + schema only. The divergence/consensus
classification, the CIO synthesis into one TradePlan, and the calibrated-
confidence formula are money-risk logic reserved for a Fable pass (§F5) and are
deliberately NOT decided here. `tally` below is a plain display count of what
each seat concluded — it is NOT a consensus verdict.
"""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel

from app.models.quickread import QuickRead

Mandate = Literal["trend", "contrarian", "derivatives", "risk"]


class AnalystThesis(BaseModel):
    """One surviving seat's read: which mandate, which model, the validated call."""

    mandate: Mandate
    model_id: str
    read: QuickRead


class DroppedAnalyst(BaseModel):
    """A seat that failed validation twice or whose provider errored."""

    mandate: Mandate
    reason: str


class DeskPanelResponse(BaseModel):
    """Full Desk envelope. Degrades (status=degraded), never 500s."""

    symbol: str
    generated_at: datetime
    brief_generated_at: datetime
    theses: list[AnalystThesis]
    dropped: list[DroppedAnalyst]
    # direction -> count over surviving theses (display only, not a verdict)
    tally: dict[str, int]
    status: Literal["ok", "degraded"]
    reason: str | None = None

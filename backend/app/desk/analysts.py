"""Analyst panel service (P2 Full Desk core plumbing).

Fans the Market Brief out to every configured mandate seat IN PARALLEL. Each
seat is a `QuickReadService` carrying its own mandate prompt + model, so every
thesis inherits the same guarantees: schema validation, the evidence lock, and
one-retry-then-drop. Survivors come back with the seats that dropped and why;
the panel never raises on a model failure (invariant 2 / NFR-3).

Reserved for Fable (§F5), NOT implemented here: divergence/consensus_state
classification, CIO synthesis into one TradePlan, calibrated confidence, sizing.
"""

import asyncio
from dataclasses import dataclass

from app.core.llm import LLMError
from app.desk.quick_read import QuickReadError, QuickReadService
from app.models.analyst import AnalystThesis, DroppedAnalyst, Mandate
from app.models.brief import MarketBrief


@dataclass(frozen=True)
class Seat:
    mandate: Mandate
    service: QuickReadService


class AnalystPanel:
    def __init__(self, seats: list[Seat], min_survivors: int = 3) -> None:
        self._seats = seats
        self._min_survivors = min_survivors

    @property
    def seat_count(self) -> int:
        return len(self._seats)

    @property
    def min_survivors(self) -> int:
        return self._min_survivors

    async def run(
        self, brief: MarketBrief
    ) -> tuple[list[AnalystThesis], list[DroppedAnalyst]]:
        """Run all seats concurrently; return (surviving theses, dropped seats).

        Order of `theses` follows the configured seat order for stable display.
        """

        async def run_seat(
            seat: Seat,
        ) -> tuple[AnalystThesis | None, DroppedAnalyst | None]:
            try:
                read = await seat.service.run(brief)
                thesis = AnalystThesis(
                    mandate=seat.mandate, model_id=seat.service.model_id, read=read
                )
                return thesis, None
            except (QuickReadError, LLMError) as exc:
                return None, DroppedAnalyst(mandate=seat.mandate, reason=str(exc)[:200])

        results = await asyncio.gather(*(run_seat(s) for s in self._seats))
        theses = [t for t, _ in results if t is not None]
        dropped = [d for _, d in results if d is not None]
        return theses, dropped


__all__ = ["AnalystPanel", "Seat"]

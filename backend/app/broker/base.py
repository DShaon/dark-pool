"""The Broker interface (ADR-0008, fulfilled by ADR-0021).

The seam the future live bot plugs into — behind the SAME approval gate,
via a new implementation and its own ADR, never edits to analysis code.
v1 ships exactly one implementation: `PaperBroker`.

The gate itself is not on this interface: approve/reject are invoked only by
the authenticated UI routes. The MCP (AI-facing) surface can propose and
read — it has no handle to anything that fills.
"""

from abc import ABC, abstractmethod

from app.models.broker import (
    Actor,
    OrderProposal,
    PaperAccountView,
    PaperPosition,
    ProposalIn,
)


class Broker(ABC):
    kind: str

    @abstractmethod
    def propose(self, intent: ProposalIn, source: Actor) -> OrderProposal: ...

    @abstractmethod
    def list_proposals(self, status: str | None = None) -> list[OrderProposal]: ...

    @abstractmethod
    async def approve(self, proposal_id: str) -> dict: ...

    @abstractmethod
    def reject(self, proposal_id: str) -> OrderProposal: ...

    @abstractmethod
    def positions(self, status: str | None = None) -> list[PaperPosition]: ...

    @abstractmethod
    async def close_position(self, position_id: str) -> PaperPosition: ...

    @abstractmethod
    async def account(self) -> PaperAccountView: ...

    @abstractmethod
    async def monitor_tick(self) -> int: ...


__all__ = ["Broker"]

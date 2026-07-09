"""Quick Read contract — the first LLM boundary (FR-3 tier 1, §F4).

Every field is schema-enforced; `evidence` is the anti-hallucination lock:
each entry must be a dot-path that RESOLVES inside the Market Brief the model
was shown (e.g. ``timeframes.1h.structure.trend``,
``timeframes.15m.order_blocks[0].bottom``). Citing a field that does not
exist fails validation in code — the model gets one retry, then the read is
dropped (CLAUDE.md invariant 2). Money fields are Decimal, serialized as
strings (invariant 3).
"""

import re
from datetime import datetime
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, Field, field_serializer, model_validator

# Segments are dict keys, not Python identifiers — timeframe keys like "1h"
# and "15m" begin with digits and must resolve.
_SEGMENT = re.compile(r"^([A-Za-z0-9_]+)(?:\[(\d+)\])?$")


class EvidenceError(ValueError):
    """One or more evidence paths do not resolve inside the brief."""


def resolve_path(data: object, path: str) -> object:
    """Resolve ``a.b[2].c`` inside nested dicts/lists; raise KeyError if absent."""
    node = data
    for raw in path.split("."):
        m = _SEGMENT.match(raw)
        if not m:
            raise KeyError(f"malformed segment {raw!r}")
        name, idx = m.group(1), m.group(2)
        if not isinstance(node, dict) or name not in node:
            raise KeyError(name)
        node = node[name]
        if idx is not None:
            if not isinstance(node, list) or int(idx) >= len(node):
                raise KeyError(f"{name}[{idx}]")
            node = node[int(idx)]
    return node


def check_evidence(paths: list[str], brief_data: dict) -> None:
    """Raise EvidenceError listing every path that fails to resolve."""
    bad: list[str] = []
    for p in paths:
        try:
            resolve_path(brief_data, p)
        except KeyError:
            bad.append(p)
    if bad:
        raise EvidenceError(
            f"evidence paths not found in brief: {', '.join(bad)} — "
            "cite only fields that exist in the provided JSON"
        )


class EntryZone(BaseModel):
    low: Decimal
    high: Decimal

    @field_serializer("low", "high")
    def _ser(self, v: Decimal) -> str:
        return str(v)


class Target(BaseModel):
    price: Decimal
    rr: float = Field(ge=0)

    @field_serializer("price")
    def _ser(self, v: Decimal) -> str:
        return str(v)


class Invalidation(BaseModel):
    price: Decimal
    condition: str = Field(min_length=3, max_length=200)

    @field_serializer("price")
    def _ser(self, v: Decimal) -> str:
        return str(v)


class QuickRead(BaseModel):
    direction: Literal["long", "short", "no_trade"]
    conviction: int = Field(ge=1, le=5)
    entry_zone: EntryZone | None = None
    stop_loss: Decimal | None = None
    targets: list[Target] = Field(default_factory=list, max_length=3)
    thesis: str = Field(min_length=20, max_length=900)
    failure_mode: str = Field(min_length=10, max_length=400)
    # Native-Bangla renderings of the two prose fields (user amendment). Optional:
    # a model that omits them degrades to English-only, never a dropped read
    # (invariant 2). They translate the thesis — they never carry new numbers.
    thesis_bn: str | None = Field(default=None, max_length=1400)
    failure_mode_bn: str | None = Field(default=None, max_length=700)
    invalidation: Invalidation | None = None
    evidence: list[str] = Field(min_length=2, max_length=12)

    @model_validator(mode="after")
    def _trade_needs_levels(self) -> "QuickRead":
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
            if missing or not self.targets:
                if not self.targets:
                    missing.append("targets")
                raise ValueError(
                    f"direction={self.direction} requires: {', '.join(missing)}"
                )
        return self

    @field_serializer("stop_loss")
    def _ser_stop(self, v: Decimal | None) -> str | None:
        return None if v is None else str(v)


class QuickReadResponse(BaseModel):
    """Envelope the API returns. A failed read degrades — never a 500."""

    symbol: str
    generated_at: datetime
    brief_generated_at: datetime
    model_id: str
    status: Literal["ok", "degraded"]
    reason: str | None = None
    read: QuickRead | None = None

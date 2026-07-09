"""File-backed store for CIO trade plans (P1 stand-in for Postgres `trade_plans`).

The interactive CIO (Claude over MCP) reads the analyst debate, synthesizes ONE
plan, and saves it here; `list` reads them back. Single-user, one JSON file,
atomic writes. Swaps for Supabase Postgres (B4) later without changing the MCP
tool surface. Money fields are stored as strings (invariant 3); timestamps UTC.
"""

from __future__ import annotations

import contextlib
import json
import os
import tempfile
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field


class Target(BaseModel):
    price: str
    rr: float | None = None


class CioPlan(BaseModel):
    """A CIO-issued plan. The synthesis judgment is the model's (Fable per §F5);
    this schema only shapes + validates what gets persisted."""

    symbol: str
    direction: Literal["long", "short", "no_trade"]
    conviction: int = Field(ge=1, le=5)
    entry_low: str | None = None
    entry_high: str | None = None
    stop: str | None = None
    targets: list[Target] = Field(default_factory=list)
    thesis: str = Field(min_length=10, max_length=2000)
    notes: str | None = Field(default=None, max_length=2000)
    source: str = "cio_mcp"


class PlanStore:
    def __init__(self, path: Path) -> None:
        self._path = Path(path)

    def _load(self) -> list[dict]:
        try:
            data = json.loads(self._path.read_text(encoding="utf-8"))
            return data if isinstance(data, list) else []
        except (FileNotFoundError, json.JSONDecodeError):
            return []

    def _atomic_write(self, records: list[dict]) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        fd, tmp = tempfile.mkstemp(dir=str(self._path.parent), suffix=".tmp")
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                json.dump(records, f, ensure_ascii=False, indent=2)
            os.replace(tmp, self._path)  # atomic on the same filesystem
        except BaseException:
            with contextlib.suppress(OSError):
                os.unlink(tmp)
            raise

    def add(self, plan: CioPlan) -> dict:
        record = {
            "id": "plan_" + uuid.uuid4().hex[:12],
            "saved_at": datetime.now(timezone.utc).isoformat(),
            **plan.model_dump(),
        }
        records = self._load()
        records.insert(0, record)  # newest first
        self._atomic_write(records)
        return record

    def list(self, symbol: str | None = None, limit: int = 20) -> list[dict]:
        records = self._load()
        if symbol:
            s = symbol.upper()
            records = [r for r in records if str(r.get("symbol", "")).upper() == s]
        return records[: max(0, limit)]
